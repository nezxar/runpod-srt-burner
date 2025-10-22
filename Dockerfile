FROM python:3.10-slim

# SSL + FFmpeg
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==== !!! إضافة جديدة (معدلة) !!! ====
# 1. أنشئ مجلد الخطوط داخل الحاوية
RUN mkdir -p /app/fonts
# 2. انسخ ملف الخط من المجلد الرئيسي إلى مجلد الخطوط داخل الحاوية
COPY arial.ttf /app/fonts/
# =================================

COPY handler.py .

CMD ["python", "handler.py"]
