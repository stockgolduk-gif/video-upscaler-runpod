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

# -------------------------
# Utility helpers
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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "runpod-video-upscaler/1.0"}
    )
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())

def _ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {p.stderr.strip()[:500]}")
    return json.loads(p.stdout)

def _extract_video_metadata(probe: dict) -> dict:
    streams = probe.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise RuntimeError("No video stream found.")

    width = int(v.get("width") or 0)
    height = int(v.get("height") or 0)

    rfr = v.get("r_frame_rate") or "0/1"
    try:
        num, den = rfr.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 0.0
    except Exception:
        fps = 0.0

    duration = float(probe.get("format", {}).get("duration") or 0.0)

    return {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "duration_seconds": round(duration, 3),
        "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
    }

# -------------------------
# R2 upload
# -------------------------

def _upload_to_r2(file_path: Path, object_name: str) -> str:
    account_id = os.environ["R2_ACCOUNT_ID"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    bucket = os.environ["R2_BUCKET_NAME"]

    endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    s3.upload_file(
        Filename=str(file_path),
        Bucket=bucket,
        Key=object_name,
        ExtraArgs={"ContentType": "video/mp4"}
    )

    return f"https://pub-{account_id}.r2.dev/{bucket}/{object_name}"

# -------------------------
# AI Upscaling (Real-ESRGAN)
# -------------------------

def _ai_upscale_video(input_video: Path, meta: dict) -> Path:
    """
    Full AI pipeline:
    - Extract frames
    - Upscale frames with Real-ESRGAN
    - Reassemble video
    """

    frames_dir = TMP_DIR / "frames"
    upscaled_dir = TMP_DIR / "frames_upscaled"

    shutil.rmtree(frames_dir, ignore_errors=True)
    shutil.rmtree(upscaled_dir, ignore_errors=True)

    frames_dir.mkdir(parents=True, exist_ok=True)
    upscaled_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract frames (lossless)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", str(input_video),
            "-vsync", "0",
            str(frames_dir / "frame_%06d.png"),
        ],
        check=True
    )

    # 2. Decide scale (stock-safe rules)
    input_height = meta["height"]

    if input_height >= 1080:
        scale = 2
    elif input_height == 720:
        scale = 2
    else:
        raise RuntimeError("Input resolution too low for stock-safe AI upscaling")

    # 3. Run Real-ESRGAN (GPU required – will activate once Docker + A10 are added)
    subprocess.run(
        [
            "python3",
            "inference_realesrgan.py",
            "-n", "RealESRGAN_x2plus",
            "-s", str(scale),
            "-i", str(frames_dir),
            "-o", str(upscaled_dir),
            "--fp32",
        ],
        check=True
    )

    # 4. Reassemble video
    output_width = meta["width"] * scale
    output_height = meta["height"] * scale
    output_path = TMP_DIR / f"upscaled_{output_width}x{output_height}.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate", str(meta["fps"]),
            "-i", str(upscaled_dir / "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "slow",
            str(output_path),
        ],
        check=True
    )

    return output_path

# -------------------------
# Main handler
# -------------------------

def handler(job):
    job_input = job.get("input", {}) or {}

    video_url = job_input.get("video_url")
    upscale_method = job_input.get("upscale_method", "ai")

    if not video_url or not isinstance(video_url, str):
        return {
            "status": "error",
            "error": "Missing required field: input.video_url"
        }

    input_filename = _safe_filename_from_url(video_url)
    input_path = TMP_DIR / input_filename

    _download(video_url, input_path)

    probe = _ffprobe(input_path)
    meta = _extract_video_metadata(probe)

    try:
        if upscale_method == "ai":
            output_path = _ai_upscale_video(input_path, meta)
        else:
            raise RuntimeError("FFmpeg-only upscale path is disabled for stock quality")

    except Exception:
        raise  # fail hard – no silent downgrades for stock

    public_url = _upload_to_r2(
        file_path=output_path,
        object_name=output_path.name
    )

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
