FROM python:3.10-slim

# تثبيت FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# تثبيت المتطلبات
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY handler.py .

CMD ["python", "handler.py"]
