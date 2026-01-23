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
    unzip \
    libvulkan1 \
    vulkan-tools \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip
RUN pip install runpod boto3 requests

# --------------------------------------------------
# Download Real-ESRGAN NCNN Vulkan (includes models)
# --------------------------------------------------
RUN mkdir -p /app/realesrgan && cd /app/realesrgan && \
    wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip && \
    unzip realesrgan-ncnn-vulkan-20220424-ubuntu.zip && \
    chmod +x realesrgan-ncnn-vulkan

# --------------------------------------------------
# App
# --------------------------------------------------
WORKDIR /app
COPY handler.py /app/handler.py

CMD ["python3", "handler.py"]
