import runpod
import os
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

import requests
import boto3
from botocore.client import Config

TMP_DIR = Path("/tmp")

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
        headers={"User-Agent": "runpod-upscaler/1.0"}
    )
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
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

    fmt = probe.get("format", {})
    duration = float(fmt.get("duration") or 0.0)

    return {
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "duration_seconds": round(duration, 3),
        "codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
    }

def _upload_to_r2(file_path: Path, object_name: str) -> str:
    # 🔍 DEBUG — PROVE ENV INJECTION
    account_id = os.environ.get("R2_ACCOUNT_ID", "MISSING")
    access_key = os.environ.get("R2_ACCESS_KEY_ID", "MISSING")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY", "MISSING")
    bucket = os.environ.get("R2_BUCKET_NAME", "MISSING")

    print("DEBUG R2_ACCOUNT_ID =", account_id)
    print("DEBUG R2_BUCKET_NAME =", bucket)
    print("DEBUG ALL ENV KEYS =", sorted(os.environ.keys()))

    if "MISSING" in (account_id, access_key, secret_key, bucket):
        raise RuntimeError("One or more required R2 environment variables are missing")

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

    public_url = f"https://pub-{account_id}.r2.dev/{bucket}/{object_name}"
    return public_url

def handler(job):
    job_input = job.get("input", {}) or {}

    video_url = job_input.get("video_url")
    scale_factor = job_input.get("scale_factor", 2)

    if not video_url or not isinstance(video_url, str):
        return {
            "status": "error",
            "error": "Missing required field: input.video_url"
        }

    if scale_factor not in (2, 3):
        return {
            "status": "error",
            "error": "scale_factor must be 2 or 3"
        }

    input_filename = _safe_filename_from_url(video_url)
    input_path = TMP_DIR / input_filename

    _download(video_url, input_path)

    probe = _ffprobe(input_path)
    meta = _extract_video_metadata(probe)

    out_width = meta["width"] * scale_factor
    out_height = meta["height"] * scale_factor
    output_filename = f"upscaled_{out_width}x{out_height}.mp4"
    output_path = TMP_DIR / output_filename

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vf", f"scale=iw*{scale_factor}:ih*{scale_factor}:flags=lanczos",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    subprocess.run(ffmpeg_cmd, check=True)

    public_url = _upload_to_r2(
        file_path=output_path,
        object_name=output_filename
    )

    return {
        "status": "ok",
        "message": "Video processed and uploaded successfully",
        "input_metadata": meta,
        "output": {
            "filename": output_filename,
            "public_url": public_url
        }
    }

runpod.serverless.start({"handler": handler})
