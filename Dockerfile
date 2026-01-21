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
# PyTorch (CUDA 12.1)
# -------------------------
RUN pip3 install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# -------------------------
# Runtime Python deps
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
# Download model weights (FIXED)
# -------------------------
RUN mkdir -p weights && \
    curl -L \
    -o weights/RealESRGAN_x2plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.pth

# -------------------------
# App code
# -------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
