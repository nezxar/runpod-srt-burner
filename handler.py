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

# ---------- GET VIDEO RESOLUTION ----------
def get_video_resolution(video_path):
    """استخراج دقة الفيديو باستخدام ffprobe"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            video_path
        ]
        result = subprocess.check_output(cmd, text=True)
        data = json.loads(result)
        
        if "streams" in data and len(data["streams"]) > 0:
            width = int(data["streams"][0].get("width", 1280))
            height = int(data["streams"][0].get("height", 720))
            # تأكد من الأبعاد الزوجية
            width = width if width % 2 == 0 else width - 1
            height = height if height % 2 == 0 else height - 1
            return width, height
    except:
        pass
    return 1280, 720  # default fallback

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

# ---------- SRT -> ASS CONVERSION ----------
def convert_srt_to_ass(srt_content, width, height, font_name="Arial"):
    """
    تحويل SRT إلى ASS مع استخدام إعدادات 720p الثابتة لكل الفيديوهات
    هذا يضمن جودة موحدة وممتازة للترجمة في كل الفيديوهات
    """
    # إعدادات ثابتة مثل 720p لجميع الفيديوهات (الإعدادات الأمثل)
    font_size = 42      # حجم الخط الثابت (مثالي لـ 720p)
    outline = 3.5       # حدود واضحة جداً
    shadow = 1.8        # ظلال متوسطة للوضوح
    margin_v = 35       # الهامش السفلي الثابت
    spacer_size = 12    # حجم الفراغ بين السطور
    
    style_header = f"""[Script Info]
Title: Translated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,10,10,{margin_v},1

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
            text = intelligently_wrap_text(raw_text, spacer_size=spacer_size, original_font_size=font_size)
            ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{text}")
        except ValueError:
            continue
    return style_header + "\n".join(ass_lines)

# ---------- GPU HARDSUB WITH 720P UPSCALING ----------
def burn_with_ass(input_path, srt_path, output_path):
    """
    حرق الترجمة مع رفع الدقة إلى 720p للفيديوهات الأقل
    لضمان أفضل جودة وأوضح نص للترجمة
    """
    # 1. كشف دقة الفيديو الأصلي
    orig_width, orig_height = get_video_resolution(input_path)
    print(f"📹 Original resolution: {orig_width}x{orig_height}")
    
    # 2. رفع الدقة إلى 720p كحد أدنى لجودة الترجمة
    MIN_HEIGHT = 720  # رفع كل الفيديوهات الأقل من 720p إلى 720p
    
    if orig_height < MIN_HEIGHT:
        # رفع الدقة إلى 720p
        work_height = MIN_HEIGHT
        work_width = int(orig_width * (work_height / orig_height))
        # تأكد من أن الأبعاد زوجية (مطلوب لـ h264)
        work_width = work_width if work_width % 2 == 0 else work_width + 1
        work_height = work_height if work_height % 2 == 0 else work_height + 1
        print(f"⬆️ Upscaling to {work_width}x{work_height} for crystal-clear subtitles")
        upscaled = True
    else:
        work_width = orig_width
        work_height = orig_height
        upscaled = False
        print(f"✅ Resolution is {orig_width}x{orig_height}, perfect for subtitles!")
    
    # 3. تحويل SRT إلى ASS باستخدام إعدادات 720p الثابتة
    local_ass = os.path.splitext(srt_path)[0] + ".ass"
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()
    ass_content = convert_srt_to_ass(srt_content, work_width, work_height)
    with open(local_ass, "w", encoding="utf-8") as f:
        f.write(ass_content)
    
    # 4. إعداد مجلد الخطوط
    fonts_dir = "/app/fonts"
    os.makedirs(fonts_dir, exist_ok=True)
    if os.path.exists("/app/arial.ttf"):
        shutil.copy("/app/arial.ttf", os.path.join(fonts_dir, "arial.ttf"))
    
    # 5. بناء الفلتر
    filters = []
    
    # إذا كان الفيديو بحاجة إلى رفع دقة
    if upscaled:
        # رفع الدقة بـ Lanczos (أفضل جودة)
        filters.append(f"scale={work_width}:{work_height}:flags=lanczos")
        # إضافة unsharp خفيف لتحسين وضوح النص بعد الـ upscaling
        filters.append("unsharp=5:5:0.8:5:5:0.0")
    
    # إضافة الترجمة مع تحسينات جودة الرسم
    # shaping=simple: يحسن رسم الحروف العربية والإنجليزية
    filters.append(f"ass='{local_ass}':fontsdir='{fonts_dir}':shaping=simple")
    
    vf = ",".join(filters)
    
    # 6. تنفيذ FFmpeg مع أفضل إعدادات جودة
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "h264_nvenc",
        "-preset", "p4",      # p4 = جودة أعلى (أبطأ قليلاً من p2 لكن أفضل)
        "-rc", "vbr",         # Variable bitrate للجودة الأفضل
        "-cq", "19",          # CQ (Constant Quality) = 19 (جودة عالية جداً، كلما قل الرقم = جودة أعلى)
        "-b:v", "12M",        # متوسط bitrate
        "-maxrate", "18M",    # الحد الأقصى
        "-bufsize", "24M",    # حجم الـ buffer
        "-spatial-aq", "1",   # Spatial AQ لتحسين جودة التفاصيل (مثل الخط)
        "-temporal-aq", "1",  # Temporal AQ
        "-c:a", "copy",
        output_path
    ]
    
    print(f"🔥 Burning subtitles with filter: {vf}")
    subprocess.check_call(cmd)
    print(f"✅ Done! Crystal-clear subtitles ready!")

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
    print(f"⬇️ Downloading video from {video_url}")
    http_download(video_url, in_path)
    print(f"⬇️ Downloading SRT from {srt_url}")
    http_download(srt_url, sub_path)

    # حرق الترجمة
    burn_with_ass(in_path, sub_path, out_path)

    # منطق الرفع
    output_put_url = inp.get("output_put_url")
    expected_output_key = inp.get("expected_output_key")

    if output_put_url:
        # ارفع الناتج للـ PUT URL
        print(f"⬆️ Uploading to PUT URL")
        with open(out_path, "rb") as f:
            requests.put(output_put_url, data=f, headers={"Content-Type": "video/mp4"}, timeout=600)
        return {
            "ok": True,
            "output_key": expected_output_key,
            "download_url": None,
            "exec_seconds": round(time.time() - t0, 2)
        }
    else:
        # المسار القديم المعتمد على R2
        assert s3 is not None, "R2 not configured"
        output_key = f"{out_prefix}/{int(time.time())}-{job}.mp4"
        print(f"⬆️ Uploading to R2: {output_key}")
        upload_to_r2(out_path, output_key)
        download_url = presigned_get_url(output_key, ttl=3600)
        return {
            "ok": True,
            "output_key": output_key,
            "download_url": download_url,
            "exec_seconds": round(time.time() - t0, 2)
        }

runpod.serverless.start({"handler": handler})
