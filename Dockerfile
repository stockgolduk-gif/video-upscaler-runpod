FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# -------------------------
# System dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    git \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -------------------------
# Python dependencies
# -------------------------
RUN pip3 install --no-cache-dir \
    runpod \
    boto3 \
    numpy \
    opencv-python \
    torch \
    torchvision \
    realesrgan

# -------------------------
# Download Real-ESRGAN weights (STOCK-SAFE)
# IMPORTANT: capital -O (not zero)
# -------------------------
RUN mkdir -p weights && \
    wget -O weights/RealESRGAN_x2plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.pth

# -------------------------
# App setup
# -------------------------
WORKDIR /app
COPY . /app

# -------------------------
# Start RunPod handler
# -------------------------
CMD ["python3", "handler.py"]
