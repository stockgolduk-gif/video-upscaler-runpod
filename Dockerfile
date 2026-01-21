FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

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

# -------------------------
# Python base
# -------------------------
RUN pip3 install --upgrade pip

# -------------------------
# PyTorch (PINNED — IMPORTANT)
# -------------------------
RUN pip3 install \
    torch==2.0.1 \
    torchvision==0.15.2 \
    torchaudio==2.0.2 \
    --index-url https://download.pytorch.org/whl/cu121

# -------------------------
# Runtime deps
# -------------------------
RUN pip3 install \
    runpod \
    boto3 \
    requests \
    numpy \
    opencv-python \
    pillow \
    tqdm \
    basicsr \
    facexlib \
    gfpgan

# -------------------------
# Real-ESRGAN
# -------------------------
RUN git clone https://github.com/xinntao/Real-ESRGAN.git

WORKDIR /app/Real-ESRGAN
RUN pip3 install -r requirements.txt
RUN pip3 install -e .

# -------------------------
# Model weights (curl, not wget)
# -------------------------
RUN mkdir -p weights && \
    curl -L \
    -o weights/RealESRGAN_x2plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.pth

# -------------------------
# App
# -------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
