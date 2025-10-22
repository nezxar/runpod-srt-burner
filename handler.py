import os, uuid, time, subprocess, requests, runpod
import boto3
from botocore.client import Config
import re

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

# ==================== دوال جديدة مأخوذة من server.py ====================

[server.py] def intelligently_wrap_text(text, max_length=45, spacer_size=12, original_font_size=36):
[server.py]     if len(text) <= max_length:
[server.py]         return text
[server.py]     words = text.split(' ')
[server.py]     if not words or len(words) == 1:
[server.py]         return text
[server.py]     mid_point = len(text) // 2
[server.py]     best_split_index = -1
[server.py]     min_distance_from_mid = float('inf')
[server.py]     current_pos = 0
[server.py]     for i, word in enumerate(words):
[server.py]         if i < len(words) - 1:
[server.py]             split_candidate_pos = current_pos + len(word)
[server.py]             distance = abs(split_candidate_pos - mid_point)
[server.py]             if distance < min_distance_from_mid:
[server.py]                 min_distance_from_mid = distance
[server.py]                 best_split_index = i + 1
[server.py]         current_pos += len(word) + 1 
[server.py]     if best_split_index != -1:
[server.py]         line1 = ' '.join(words[:best_split_index])
[server.py]         line2 = ' '.join(words[best_split_index:])
[server.py]         return f"{line1}\\N{{\\fs{spacer_size}}} \\N{{\\fs{original_font_size}}}{line2}"
    else:
[server.py]         return text

[server.py] def convert_srt_to_ass(srt_content, font_name="Arial", font_size=42):
[server.py]     style_header = f"""[Script Info]
Title: Translated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1280
PlayResY: 720
YCbCr Matrix: None
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
[server.py] Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,10,10,35,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
[server.py]     ass_lines = []
[server.py]     srt_blocks = srt_content.strip().replace('\r', '').split('\n\n')
[server.py]     for block in srt_blocks:
[server.py]         lines = block.strip().split('\n')
[server.py]         if len(lines) < 3:
[server.py]             continue
[server.py]         time_line = lines[1]
        try:
[server.py]             start_str, end_str = time_line.split(' --> ')
[server.py]             start_h, start_m, start_s_ms = start_str.split(':')
[server.py]             start_s, start_ms = start_s_ms.split(',')
[server.py]             start_ass = f"{int(start_h)}:{start_m}:{start_s}.{int(start_ms) // 10:02d}"
[server.py]             end_h, end_m, end_s_ms = end_str.split(':')
[server.py]             end_s, end_ms = end_s_ms.split(',')
[server.py]             end_ass = f"{int(end_h)}:{end_m}:{end_s}.{int(end_ms) // 10:02d}"
[server.py]             raw_text = ' '.join(lines[2:])
[server.py]             text = intelligently_wrap_text(raw_text, max_length=45, spacer_size=12, original_font_size=font_size)
[server.py]             ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")
[server.py]         except ValueError:
[server.py]             print(f"Skipping malformed SRT block: {block}")
[server.py]             continue
[server.py]     return style_header + "\n".join(ass_lines)

# ==================== دالة الحرق المعدلة (بنسخة جديدة) ====================

def burn_subs(input_path, srt_path, output_path, use_nvenc=True, bitrate="8M"):
    
    print(f"--- [LOG] Starting burn_subs for: {input_path}")
    ass_path = os.path.splitext(srt_path)[0] + ".ass"
    
    # --- الخطوة 1: تحويل SRT إلى ASS ---
    try:
        print(f"--- [LOG] Attempting to convert SRT to ASS (Font: 'Arial', Size: 42)")
        with open(srt_path, 'r', encoding='utf-8') as f:
            srt_content = f.read()
        
        ass_content = convert_srt_to_ass(srt_content, font_name="Arial", font_size=42)
        
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        print(f"--- [LOG] ASS file created successfully at: {ass_path}")

    except Exception as e:
        print(f"--- [LOG] !!! FAILED to convert SRT to ASS: {e} !!!")
        # لا يوجد احتياطي، أفشل المهمة لكي نرى الخطأ
        raise Exception(f"Failed to convert SRT to ASS: {e}")

    # --- الخطوة 2: بناء أمر FFmpeg ---
    # بما أننا قمنا بتثبيت الخط في النظام، لم نعد بحاجة إلى 'fontsdir'
    # سيجد libass خط "Arial" تلقائياً
    vf_command = f"ass='{ass_path}'"
    print(f"--- [LOG] Using ASS video filter: {vf_command}")

    if use_nvenc and ffmpeg_has_nvenc():
        print(f"--- [LOG] Using NVENC (GPU) encoder.")
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf_command,
            "-c:v", "h264_nvenc", "-preset", "p1", "-tune", "ll",
            "-rc", "cbr", "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "2M",
            "-c:a", "copy", output_path
        ]
    else:
        print(f"--- [LOG] Using libx264 (CPU) encoder.")
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf_command,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "copy", output_path
        ]
    
    # --- الخطوة 3: تنفيذ الأمر ---
    print(f"--- [LOG] Executing FFmpeg command: {' '.join(cmd)}")
    try:
        # استخدام Popen للتأكد من طباعة مخرجات الخطأ
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        
        # طباعة مخرجات ffmpeg مباشرة
        for line in process.stdout:
            print(f"[ffmpeg]: {line.strip()}")
            
        process.wait() # انتظر انتهاء العملية
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)

        print("--- [LOG] FFmpeg command finished successfully.")
        
    except subprocess.CalledProcessError as e:
        print(f"--- [LOG] !!! FFmpeg command failed with return code {e.returncode} !!!")
        # Re-raise the error to fail the handler
        raise e

# ==================== دالة المعالج (لم تتغير) ====================

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

    # الحرق (سيستخدم الآن الدالة المعدلة)
    try:
        burn_subs(in_path, sub_path, out_path, use_nvenc=True, bitrate=bitrate)
    except subprocess.CalledProcessError:
        # في حال فشل المعالج السريع، جرب المعالج البطيء
        print("--- [LOG] NVENC failed, falling back to libx264 (CPU).")
        burn_subs(in_path, sub_path, out_path, use_nvenc=False, bitrate=bitrate)
    except Exception as e:
        # طباعة أي خطأ آخر (مثل فشل تحويل ASS)
        print(f"--- [LOG] !!! Handler failed: {e} !!!")
        return {"ok": False, "error": str(e)}


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
