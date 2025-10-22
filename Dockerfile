FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Install ffmpeg + deps
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates fonts-dejavu-core && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY handler.py .
COPY arial.ttf ./arial.ttf

# Create fonts directory for ffmpeg
RUN mkdir -p /app/fonts && cp /app/arial.ttf /app/fonts/arial.ttf

ENV PYTHONUNBUFFERED=1

CMD ["python", "handler.py"]
