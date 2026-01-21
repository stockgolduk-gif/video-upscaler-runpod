import runpod
import os
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
import shutil

import boto3
from botocore.client import Config

TMP_DIR = Path("/tmp")
REALESRGAN_DIR = Path("/app/Real-ESRGAN")
WEIGHTS_PATH = REALESRGAN_DIR / "weights" / "RealESRGAN_x2plus.pth"

# -------------------------
# Utilities
# -------------------------

def _safe_filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path) or "input.mp4"
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", " "))
    if not name.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        name += ".mp4"
    return name

def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "runpod-upscaler/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())

def _ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:500])
    return json.loads(p.stdout)

def _extract_video_metadata(probe: dict) -> dict:
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": round(fps, 3),
        "duration_seconds": float(probe["format"].get("duration", 0)),
        "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
    }

# -------------------------
# R2 Upload
# -------------------------

def _upload_to_r2(file_path: Path) -> str:
    account_id = os.environ["R2_ACCOUNT_ID"]
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET_NAME"]
    s3.upload_file(str(file_path), bucket, file_path.name,
                   ExtraArgs={"ContentType": "video/mp4"})
    return f"https://pub-{account_id}.r2.dev/{bucket}/{file_path.name}"

# -------------------------
# AI Upscaling
# -------------------------

def _ai_upscale_video(input_video: Path, meta: dict) -> Path:
    frames = TMP_DIR / "frames"
    upscaled = TMP_DIR / "frames_upscaled"

    shutil.rmtree(frames, ignore_errors=True)
    shutil.rmtree(upscaled, ignore_errors=True)
    frames.mkdir()
    upscaled.mkdir()

    # Extract frames
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_video),
        "-vsync", "0",
        str(frames / "frame_%06d.png")
    ], check=True)

    if meta["height"] < 720:
        raise RuntimeError("Resolution too low for stock-safe AI upscaling")

    scale = 2

    # Real-ESRGAN (explicit weights + PYTHONPATH)
    subprocess.run(
        [
            "python3",
            "inference_realesrgan.py",
            "-i", str(frames),
            "-o", str(upscaled),
            "-n", "RealESRGAN_x2plus",
            "-s", str(scale),
            "-w", str(WEIGHTS_PATH),
        ],
        cwd=str(REALESRGAN_DIR),
        env={**os.environ, "PYTHONPATH": str(REALESRGAN_DIR)},
        check=True
    )

    output = TMP_DIR / f"upscaled_{meta['width']*scale}x{meta['height']*scale}.mp4"

    subprocess.run([
        "ffmpeg", "-y",
        "-framerate", str(meta["fps"]),
        "-i", str(upscaled / "frame_%06d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "slow",
        str(output)
    ], check=True)

    return output

# -------------------------
# Handler
# -------------------------

def handler(job):
    video_url = job.get("input", {}).get("video_url")
    if not video_url:
        return {"status": "error", "error": "Missing input.video_url"}

    input_path = TMP_DIR / _safe_filename_from_url(video_url)
    _download(video_url, input_path)

    meta = _extract_video_metadata(_ffprobe(input_path))
    output_path = _ai_upscale_video(input_path, meta)
    public_url = _upload_to_r2(output_path)

    return {
        "status": "ok",
        "message": "AI upscaled video processed and uploaded successfully",
        "input_metadata": meta,
        "output": {
            "filename": output_path.name,
            "public_url": public_url
        }
    }

runpod.serverless.start({"handler": handler})
