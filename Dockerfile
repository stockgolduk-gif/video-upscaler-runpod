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
# Python
# -------------------------
RUN pip3 install --upgrade pip

# PyTorch CUDA 12.1 (L4 compatible)
RUN pip3 install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# Runtime deps
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

# -------------------------
# Download model weights (STABLE METHOD)
# -------------------------
RUN mkdir -p weights && \
    curl -L --retry 5 --retry-delay 5 \
    -o weights/RealESRGAN_x2plus.pth \
    https://raw.githubusercontent.com/xinntao/Real-ESRGAN/master/weights/RealESRGAN_x2plus.pth

# -------------------------
# App
# -------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
