FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# --------------------------------------------------
# System dependencies
# --------------------------------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    ffmpeg \
    wget \
    ca-certificates \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------
# Python runtime (NO torch, NO numpy heavy deps)
# --------------------------------------------------
RUN python3 -m pip install --upgrade pip
RUN pip install \
    runpod \
    boto3 \
    requests \
    onnxruntime-gpu

# --------------------------------------------------
# Download CUDA upscaler (ESRGAN / SwinIR ONNX)
# --------------------------------------------------
RUN mkdir -p /app/models && cd /app/models && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/RealESRGAN_x2plus.onnx

# --------------------------------------------------
# App
# --------------------------------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
