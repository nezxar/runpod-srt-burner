import os, uuid, time, subprocess, requests, runpod
import boto3
from botocore.client import Config

WORKDIR = "/workspace"
os.makedirs(WORKDIR, exist_ok=True)

# -------- R2 CONFIG (ضعها كـ Secrets/Env في Runpod) --------
R2_ACCOUNT_ID      = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID   = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET          = os.getenv("R2_BUCKET")

s3 = None
if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET:
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )

def presigned_get_url(key: str, ttl: int = 3600):
    assert s3 is not None, "R2 not configured"
    filename = key.split("/")[-1]
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": R2_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"'
        },
        ExpiresIn=ttl
    )

def upload_to_r2(local_path: str, key: str):
    assert s3 is not None, "R2 not configured"
    content_type = "video/mp4"
    with open(local_path, "rb") as f:
        s3.put_object(Bucket=R2_BUCKET, Key=key, Body=f, ContentType=content_type)
    return key

def http_download(url, path):
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)

def ffmpeg_has_nvenc():
    try:
        out = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"], text=True, stderr=subprocess.STDOUT)
        return ("h264_nvenc" in out) or ("hevc_nvenc" in out)
    except Exception:
        return False

def burn_subs(input_path, srt_path, output_path, use_nvenc=True, bitrate="8M"):
    vf = f"subtitles={srt_path}:force_style='FontName=Arial,Outline=2,Shadow=0'"
    if use_nvenc and ffmpeg_has_nvenc():
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
            "-rc", "cbr", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "2M",
            "-c:a", "copy", output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "copy", output_path
        ]
    subprocess.check_call(cmd)

def handler(event):
    t0 = time.time()
    inp = event.get("input", {}) or {}

    video_url = inp.get("video_url")
    srt_url   = inp.get("srt_url")
    video_key = inp.get("video_key")
    srt_key   = inp.get("srt_key")
    out_prefix= inp.get("out_prefix", "outputs")
    bitrate   = inp.get("bitrate", "8M")

    if (not video_url or not srt_url) and (not (video_key and srt_key)):
        raise ValueError("Pass either (video_url & srt_url) OR (video_key & srt_key).")

    # لو وصلتنا مفاتيح R2 فقط، نولّد روابط قراءة مؤقتة
    if (not video_url or not srt_url) and (video_key and srt_key):
        assert s3 is not None, "R2 not configured to presign URLs."
        video_url = presigned_get_url(video_key, ttl=3600)
        srt_url   = presigned_get_url(srt_key,   ttl=3600)

    job = uuid.uuid4().hex
    in_path  = os.path.join(WORKDIR, f"in_{job}.mp4")
    sub_path = os.path.join(WORKDIR, f"sub_{job}.srt")
    out_path = os.path.join(WORKDIR, f"out_{job}.mp4")

    # تنزيل الملفات
    http_download(video_url, in_path)
    http_download(srt_url,   sub_path)

    # الحرق
    try:
        burn_subs(in_path, sub_path, out_path, use_nvenc=True, bitrate=bitrate)
    except subprocess.CalledProcessError:
        burn_subs(in_path, sub_path, out_path, use_nvenc=False, bitrate=bitrate)

    # رفع الناتج إلى R2 (إذا الإعداد موجود)
    output_key = None
    download_url = None
    if s3 is not None:
        output_key = f"{out_prefix}/{int(time.time())}-{job}.mp4"
        upload_to_r2(out_path, output_key)
        download_url = presigned_get_url(output_key, ttl=3600)

    return {
        "ok": True,
        "output_key": output_key,
        "download_url": download_url,  # URL مؤقت ساعة
        "exec_seconds": round(time.time() - t0, 2)
    }

runpod.serverless.start({"handler": handler})
