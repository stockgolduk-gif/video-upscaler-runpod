FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# -------------------------
# System deps
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

RUN python3 -m pip install --upgrade pip

# -------------------------
# PyTorch (known stable on RunPod)
# -------------------------
RUN pip install \
    torch==2.0.1 \
    torchvision==0.15.2 \
    torchaudio==2.0.2 \
    --index-url https://download.pytorch.org/whl/cu118

# -------------------------
# Python deps (NUMPY PIN FIX)
# -------------------------
RUN pip install \
    numpy==1.26.4 \
    runpod \
    opencv-python \
    pillow \
    tqdm \
    requests \
    boto3 \
    basicsr==1.4.2 \
    facexlib==0.3.0 \
    gfpgan==1.3.8

# -------------------------
# Real-ESRGAN (simple, compatible install)
# -------------------------
RUN git clone https://github.com/xinntao/Real-ESRGAN.git
WORKDIR /app/Real-ESRGAN
RUN pip install -r requirements.txt
RUN python3 setup.py develop

# -------------------------
# Model weights
# -------------------------
RUN mkdir -p weights && \
    curl -L \
    -o weights/RealESRGAN_x2plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.pth

# -------------------------
# App
# -------------------------
WORKDIR /app
COPY handler.py .

CMD ["python3", "handler.py"]
