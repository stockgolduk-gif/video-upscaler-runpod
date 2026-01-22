import runpod
import os
import subprocess
import urllib.request
from pathlib import Path
import traceback
import boto3
from botocore.client import Config

print("NCNN HANDLER LOADED", flush=True)

TMP = Path("/tmp")
BIN = "/app/realesrgan/realesrgan-ncnn-vulkan"
MODEL_DIR = "/app/models"

# --------------------------------------------------
# Utilities
# --------------------------------------------------

def download(url: str, dest: Path):
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        f.write(r.read())

def upload_to_r2(path: Path) -> str:
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    bucket = os.environ["R2_BUCKET_NAME"]
    s3.upload_file(str(path), bucket, path.name, ExtraArgs={"ContentType": "video/mp4"})

    return f"https://pub-{os.environ['R2_ACCOUNT_ID']}.r2.dev/{bucket}/{path.name}"

# --------------------------------------------------
# Handler
# --------------------------------------------------

def handler(job):
    print("JOB RECEIVED:", job, flush=True)

    try:
        video_url = (
            job.get("input", {}).get("video_url")
            if isinstance(job, dict)
            else None
        )

        if not video_url:
            raise RuntimeError("Missing input.video_url")

        input_video = TMP / "input.mp4"
        upscaled_video = TMP / "upscaled.mp4"
        final_video = TMP / "final_4k.mp4"

        print("Downloading video...", flush=True)
        download(video_url, input_video)

        # --------------------------------------------------
        # Step 1 — 2× upscale with Real-ESRGAN NCNN
        # --------------------------------------------------
        print("Running Real-ESRGAN NCNN...", flush=True)
        subprocess.run(
            [
                BIN,
                "-i", str(input_video),
                "-o", str(upscaled_video),
                "-n", "RealESRGAN_x2plus",
                "-s", "2",
                "-m", MODEL_DIR,
            ],
            check=True,
        )

        # --------------------------------------------------
        # Step 2 — Ensure true 4K (2160p height)
        # --------------------------------------------------
        print("Final FFmpeg scale to 4K...", flush=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(upscaled_video),
                "-vf", "scale=-2:2160",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                str(final_video),
            ],
            check=True,
        )

        # --------------------------------------------------
        # Upload
        # --------------------------------------------------
        url = upload_to_r2(final_video)

        return {
            "status": "ok",
            "output": {
                "public_url": url,
            },
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
        }

runpod.serverless.start({"handler": handler})
