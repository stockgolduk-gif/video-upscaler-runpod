import runpod
import os
import subprocess
import urllib.request
from pathlib import Path
import traceback
import boto3
from botocore.client import Config

print("NCNN VULKAN HANDLER STARTED", flush=True)

TMP = Path("/tmp")
BIN = "/app/realesrgan/realesrgan-ncnn-vulkan"
MODEL_DIR = "/app/realesrgan"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def download(url: str, dest: Path):
    print(f"Downloading: {url}", flush=True)
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
    s3.upload_file(
        str(path),
        bucket,
        path.name,
        ExtraArgs={"ContentType": "video/mp4"},
    )

    url = f"https://pub-{os.environ['R2_ACCOUNT_ID']}.r2.dev/{bucket}/{path.name}"
    print(f"Uploaded to: {url}", flush=True)
    return url

# --------------------------------------------------
# Handler
# --------------------------------------------------

def handler(job):
    print("JOB RECEIVED:", job, flush=True)

    try:
        video_url = job.get("input", {}).get("video_url")
        if not video_url:
            raise RuntimeError("Missing input.video_url")

        input_video = TMP / "input.mp4"
        upscaled_2x = TMP / "upscaled_2x.mp4"
        final_4k = TMP / "final_4k.mp4"

        # 1. Download
        download(video_url, input_video)

        # 2. Real-ESRGAN NCNN (2×)
        print("Running Real-ESRGAN NCNN (2x)...", flush=True)
        subprocess.run(
            [
                BIN,
                "-i", str(input_video),
                "-o", str(upscaled_2x),
                "-n", "RealESRGAN_x2plus",
                "-s", "2",
                "-m", MODEL_DIR,
            ],
            check=True,
        )

        # 3. Final scale to true 4K
        print("Scaling to 4K (2160p)...", flush=True)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(upscaled_2x),
                "-vf", "scale=-2:2160",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "slow",
                str(final_4k),
            ],
            check=True,
        )

        # 4. Upload
        url = upload_to_r2(final_4k)

        return {
            "status": "ok",
            "output": {
                "public_url": url,
            },
        }

    except Exception as e:
        print("HANDLER ERROR", flush=True)
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
        }

runpod.serverless.start({"handler": handler})
