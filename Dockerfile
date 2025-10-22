FROM nvidia/cuda:12.2.0-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        ffmpeg ca-certificates fonts-dejavu-core && \
    ln -sf /usr/bin/python3 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py .
COPY arial.ttf /app/arial.ttf
RUN mkdir -p /app/fonts && cp /app/arial.ttf /app/fonts/arial.ttf

CMD ["python", "handler.py"]
