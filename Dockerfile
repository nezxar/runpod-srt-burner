FROM python:3.10-slim

# SSL + FFmpeg + FontConfig (لإدارة الخطوط)
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates fontconfig && \ 
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==== !!! إضافة الخط (الطريقة الصحيحة) !!! ====
# 1. أنشئ مجلد الخطوط (fontconfig يبحث هنا)
RUN mkdir -p /usr/share/fonts/truetype/custom
# 2. انسخ ملف الخط
COPY arial.ttf /usr/share/fonts/truetype/custom/
# 3. أعد بناء كاش الخطوط (مهم جداً لـ ffmpeg)
RUN fc-cache -f -v

COPY handler.py .

CMD ["python", "handler.py"]
