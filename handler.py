import os, subprocess, uuid, requests, runpod

WORKDIR = "/workspace"
os.makedirs(WORKDIR, exist_ok=True)

def download(url, path):
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)

def ffmpeg_has_nvenc():
    try:
        out = subprocess.check_output(["ffmpeg", "-hide_banner", "-encoders"], text=True, stderr=subprocess.STDOUT)
        return "h264_nvenc" in out or "hevc_nvenc" in out
    except Exception:
        return False

def burn_subs(input_path, srt_path, output_path, use_nvenc=True):
    vf = f"subtitles={srt_path}:force_style='FontName=Arial,Outline=2,Shadow=0'"

    if use_nvenc and ffmpeg_has_nvenc():
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
            "-rc", "cbr", "-b:v", "8M", "-maxrate", "8M", "-bufsize", "16M",
            "-c:a", "copy",
            output_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "copy",
            output_path
        ]

    subprocess.check_call(cmd)

def handler(event):
    inp = event.get("input", {})
    video_url = inp.get("video_url")
    srt_url   = inp.get("srt_url")
    assert video_url and srt_url, "video_url و srt_url مطلوبان"

    job_id = uuid.uuid4().hex
    in_path  = os.path.join(WORKDIR, f"in_{job_id}.mp4")
    srt_path = os.path.join(WORKDIR, f"sub_{job_id}.srt")
    out_path = os.path.join(WORKDIR, f"out_{job_id}.mp4")

    download(video_url, in_path)
    download(srt_url,   srt_path)

    try:
        burn_subs(in_path, srt_path, out_path, use_nvenc=True)
    except subprocess.CalledProcessError:
        burn_subs(in_path, srt_path, out_path, use_nvenc=False)

    return {"ok": True, "output_file": out_path}

runpod.serverless.start({"handler": handler})
