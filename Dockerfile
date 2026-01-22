FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# -------------------------
# System dependencies
# -------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools wheel

# -------------------------
# PyTorch (PINNED, CUDA 11.8)
# -------------------------
RUN pip3 install --no-cache-dir \
    torch==2.0.1 \
    torchvision==0.15.2 \
    torchaudio==2.0.2 \
    --index-url https://download.pytorch.org/whl/cu118

# -------------------------
# Runtime deps (PINNED)
# -------------------------
RUN pip3 install --no-cache-dir \
    runpod \
    boto3 \
    botocore \
    requests \
    numpy \
    opencv-python \
    pillow \
    tqdm \
    basicsr==1.4.2 \
    facexlib==0.3.0 \
    gfpgan==1.3.8

# -------------------------
# Real-ESRGAN (install as package, no dependency override)
# -------------------------
RUN git clone --depth 1 https://github.com/xinntao/Real-ESRGAN.git /app/Real-ESRGAN
WORKDIR /app/Real-ESRGAN

# IMPORTANT:
# - install Real-ESRGAN *without* letting it change your pinned deps
RUN pip3 install --no-cache-dir -e . --no-deps

# -------------------------
# Model weights
# -------------------------
RUN mkdir -p weights && \
    curl -L -o weights/RealESRGAN_x2plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.pth

# -------------------------
# App
# -------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
