FROM nvidia/cuda:12.2.0-base-ubuntu22.04   # أو runtime، كلاهما يحتاج Python

# Python + ffmpeg + certs + خطوط أساسية
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        ffmpeg ca-certificates fonts-dejavu-core && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    ln -s /usr/bin/pip3 /usr/bin/pip && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ السورس والخط
COPY handler.py .
COPY arial.ttf /app/arial.ttf

# تجهيز مجلد الخطوط لفلتر ASS
RUN mkdir -p /app/fonts && cp /app/arial.ttf /app/fonts/arial.ttf

ENV PYTHONUNBUFFERED=1

CMD ["python", "handler.py"]
