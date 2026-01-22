import sys
import traceback
import os
import json
import urllib.request
import urllib.parse
from pathlib import Path
import shutil
import subprocess

# -------------------------
# Early diagnostics (CRITICAL)
# -------------------------

try:
    import torch
    import torchvision
    print("TORCH VERSION:", torch.__version__)
    print("TORCHVISION VERSION:", torchvision.__version__)
    print("CUDA AVAILABLE:", torch.cuda.is_available())
except Exception:
    traceback.print_exc()
    sys.exit(1)

# -------------------------
# Safe imports (after torch)
# -------------------------

import runpod
import cv2
import numpy as np

from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet

import boto3
from botocore.client import Config

# -------------------------
# Paths & constants
# -------------------------

TMP_DIR = Path("/tmp")
MODEL_PATH = Path("/app/Real-ESRGAN/weights/RealESRGAN_x2plus.pth")

# -------------------------
# Utilities
# -------------------------

def _safe_filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path) or "input.mp4"
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", " "))
    if not name.lower().endswith(".mp4"):
        name += ".mp4"
    return name

def _download(url: str, dest: Path):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "runpod-upscaler/1.0"}
    )
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())

def _ffprobe(path: Path) -> dict:
    p = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return json.loads(p.stdout)

def _extract_meta(probe: dict) -> dict:
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) != 0 else 0.0
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": round(fps, 3),
    }

# -------------------------
# R2 upload
# -------------------------

def _upload_to_r2(file_path: Path) -> str:
    account_id = os.environ["R2_ACCOUNT_ID"]
    bucket = os.environ["R2_BUCKET_NAME"]

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    s3.upload_file(
        str(file_path),
        bucket,
        file_path.name,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    return f"https://pub-{account_id}.r2.dev/{bucket}/{file_path.name}"

# -------------------------
# AI Upscaling (Python API)
# -------------------------

def _ai_upscale_video(input_video: Path, meta: dict) -> Path:
    if meta["height"] < 720:
        raise RuntimeError("Resolution too low for stock-safe upscaling")

    frames_dir = TMP_DIR / "frames"
    upscaled_dir = TMP_DIR / "frames_upscaled"

    shutil.rmtree(frames_dir, ignore_errors=True)
    shutil.rmtree(upscaled_dir, ignore_errors=True)
    frames_dir.mkdir()
    upscaled_dir.mkdir()

    # 1. Extract frames
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(input_video),
            "-vsync", "0",
            str(frames_dir / "frame_%06d.png"),
        ],
        check=True,
    )

    # 2. Load model (PINNED & SAFE)
    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=2,
    )

    upsampler = RealESRGANer(
        scale=2,
        model_path=str(MODEL_PATH),
        model=model,
        tile=0,
        tile_pad=10,
        pre_pad=0,
        half=True,
        device=torch.device("cuda"),
    )

    # 3. Process frames
    for frame in sorted(frames_dir.glob("*.png")):
        img = cv2.imread(str(frame), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Failed to read frame {frame}")

        output, _ = upsampler.enhance(img, outscale=2)
        cv2.imwrite(str(upscaled_dir / frame.name), output)

    # 4. Reassemble video
    output_path = TMP_DIR / f"upscaled_{meta['width']*2}x{meta['height']*2}.mp4"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(meta["fps"]),
            "-i", str(upscaled_dir / "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "slow",
            str(output_path),
        ],
        check=True,
    )

    return output_path

# -------------------------
# RunPod handler
# -------------------------

def handler(job):
    try:
        video_url = job.get("input", {}).get("video_url")
        if not video_url:
            return {"status": "error", "error": "Missing input.video_url"}

        input_path = TMP_DIR / _safe_filename_from_url(video_url)
        _download(video_url, input_path)

        meta = _extract_meta(_ffprobe(input_path))
        output_path = _ai_upscale_video(input_path, meta)
        public_url = _upload_to_r2(output_path)

        return {
            "status": "ok",
            "message": "AI upscaled video processed and uploaded successfully",
            "output": {
                "filename": output_path.name,
                "public_url": public_url,
            },
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
        }

# -------------------------
# Start serverless worker
# -------------------------

runpod.serverless.start({"handler": handler})
