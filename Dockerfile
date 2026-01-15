FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    git \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install required Python dependencies
RUN pip3 install --no-cache-dir \
    runpod \
    requests \
    boto3

WORKDIR /app

COPY . /app

CMD ["python3", "handler.py"]
