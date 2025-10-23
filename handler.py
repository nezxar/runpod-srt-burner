import os, uuid, time, subprocess, requests, tempfile, shutil, re, boto3, json
from botocore.client import Config
import runpod

WORKDIR = "/workspace"
os.makedirs(WORKDIR, exist_ok=True)

# ---------- R2 CONFIG ----------
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")

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
    filename = key.split("/")[-1]
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": R2_BUCKET, "Key": key, "ResponseContentDisposition": f'attachment; filename="{filename}"'},
        ExpiresIn=ttl
    )

def upload_to_r2(local_path: str, key: str):
    assert s3 is not None, "R2 not configured"
    with open(local_path, "rb") as f:
        s3.put_object(Bucket=R2_BUCKET, Key=key, Body=f, ContentType="video/mp4")
    return key

def http_download(url, path):
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk: f.write(chunk)

# ---------- TEXT WRAPPING ----------
def intelligently_wrap_text(text, max_length=45, spacer_size=12, original_font_size=42):
    if len(text) <= max_length:
        return text
    words = text.split(' ')
    if not words or len(words) == 1:
        return text
    mid_point = len(text) // 2
    best_split_index = -1
    min_distance_from_mid = float('inf')
    current_pos = 0
    for i, word in enumerate(words):
        if i < len(words) - 1:
            split_candidate_pos = current_pos + len(word)
            distance = abs(split_candidate_pos - mid_point)
            if distance < min_distance_from_mid:
                min_distance_from_mid = distance
                best_split_index = i + 1
        current_pos += len(word) + 1
    if best_split_index != -1:
        line1 = ' '.join(words[:best_split_index])
        line2 = ' '.join(words[best_split_index:])
        return f"{line1}\\N{{\\fs{spacer_size}}}\\N{{\\fs{original_font_size}}}{line2}"
    return text

# ---------- PROBE VIDEO SIZE ----------
def probe_wh(path):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height", "-of", "json", path]
    info = subprocess.check_output(cmd)
    data = json.loads(info)
    w = data["streams"][0]["width"]
    h = data["streams"][0]["height"]
    return w, h

# ---------- SRT -> ASS CONVERSION ----------
def convert_srt_to_ass(srt_content, font_name="Arial", font_size=42, playres_w=1280, playres_h=720):
    style_header = f"""[Script Info]
Title: Translated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {playres_w}
PlayResY: {playres_h}
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,10,10,{int(playres_h*0.05)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    srt_blocks = srt_content.strip().replace('\r', '').split('\n\n')
    for block in srt_blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        time_line = lines[1]
        try:
            start_str, end_str = time_line.split(' --> ')
            start_h, start_m, start_s_ms = start_str.split(':')
            start_s, start_ms = start_s_ms.split(',')
            start_ass = f"{int(start_h)}:{start_m}:{start_s}.{int(start_ms)//10:02d}"
            end_h, end_m, end_s_ms = end_str.split(':')
            end_s, end_ms = end_s_ms.split(',')
            end_ass = f"{int(end_h)}:{end_m}:{end_s}.{int(end_ms)//10:02d}"
            raw_text = ' '.join(lines[2:])
            text = intelligently_wrap_text(raw_text, spacer_size=12, original_font_size=font_size)
            # ملاحظة: ممكن إضافة \blur0.6 داخل النص عند الحاجة
            ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")
        except ValueError:
            continue
    return style_header + "\n".join(ass_lines)

# ---------- GPU HARDSUB ----------
def burn_with_ass(input_path, srt_path, output_path):
    # احصل على أبعاد الفيديو الفعلية واضبط PlayRes وحجم الخط تبعاً لها
    w, h = probe_wh(input_path)

    local_ass = os.path.splitext(srt_path)[0] + ".ass"
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    # حجم خط نسبي لارتفاع الفيديو (لا يقل عن 28)
    font_size = max(28, int(h * 0.055))

    ass_content = convert_srt_to_ass(
        srt_content,
        font_name="Arial",
        font_size=font_size,
        playres_w=w,
        playres_h=h
    )
    with open(local_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)

    fonts_dir = "/app/fonts"
    os.makedirs(fonts_dir, exist_ok=True)
    shutil.copy("/app/arial.ttf", os.path.join(fonts_dir, "arial.ttf"))

    vf = f"ass='{local_ass}':fontsdir='{fonts_dir}'"
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "h264_nvenc",
        "-preset", "p4",          # توازن أفضل من p3
        "-rc", "vbr",             # معدل متغير
        "-cq", "19",              # جودة مستهدفة (أقرب لـ CRF)
        "-b:v", "0",              # دع المُرَمِّز يحدد البتريت المناسب
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        output_path
    ]
    subprocess.check_call(cmd)

# ---------- HANDLER ----------
def handler(event):
    t0 = time.time()
    inp = event.get("input", {}) or {}
    video_url = inp.get("video_url")
    srt_url = inp.get("srt_url")
    out_prefix = inp.get("out_prefix", "outputs")

    if not video_url or not srt_url:
        raise ValueError("Missing video_url or srt_url")

    job = uuid.uuid4().hex
    in_path = os.path.join(WORKDIR, f"in_{job}.mp4")
    sub_path = os.path.join(WORKDIR, f"sub_{job}.srt")
    out_path = os.path.join(WORKDIR, f"out_{job}.mp4")

    # تنزيل الملفات
    http_download(video_url, in_path)
    http_download(srt_url, sub_path)

    # حرق الترجمة
    burn_with_ass(in_path, sub_path, out_path)

    # منطق الرفع الجديد
    output_put_url = inp.get("output_put_url")
    expected_output_key = inp.get("expected_output_key") # اختياري

    if output_put_url:
        # ارفع الناتج للـ PUT URL (لا يحتاج مفاتيح R2 داخل العامل)
        with open(out_path, "rb") as f:
            requests.put(output_put_url, data=f, headers={"Content-Type": "video/mp4"}, timeout=600)
        return {
            "ok": True,
            "output_key": expected_output_key,
            "download_url": None, # السيرفر يقدر يولّد رابط القراءة لاحقاً
            "exec_seconds": round(time.time() - t0, 2)
        }
    else:
        # المسار القديم المعتمد على R2 داخل العامل
        assert s3 is not None, "R2 not configured"
        output_key = f"{out_prefix}/{int(time.time())}-{job}.mp4"
        upload_to_r2(out_path, output_key)
        download_url = presigned_get_url(output_key, ttl=3600)
        return {
            "ok": True,
            "output_key": output_key,
            "download_url": download_url,
            "exec_seconds": round(time.time() - t0, 2)
        }

runpod.serverless.start({"handler": handler})
