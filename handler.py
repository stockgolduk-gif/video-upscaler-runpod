import runpod
import os
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

TMP_DIR = Path("/tmp")

def _safe_filename_from_url(url: str) -> str:
    # best-effort filename; fallback to a safe default
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path) or "input.mp4"
    # strip weird characters
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", " "))
    if not name.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
        name += ".mp4"
    return name

def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Simple, dependency-free download
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "runpod-upscaler/1.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())

def _ffprobe(path: Path) -> dict:
    # Get stream + format info as JSON
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

    # r_frame_rate like "60/1"
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

def handler(job):
    job_input = job.get("input", {}) or {}

    video_url = job_input.get("video_url")
    scale_factor = job_input.get("scale_factor")

    if not video_url or not isinstance(video_url, str):
        return {
            "status": "error",
            "error": "Missing required field: input.video_url (string)."
        }

    # We won't enforce scale_factor yet, but we validate it's present if provided
    if scale_factor is not None and scale_factor not in (2, 3):
        return {
            "status": "error",
            "error": "If provided, input.scale_factor must be 2 or 3."
        }

    filename = _safe_filename_from_url(video_url)
    local_path = TMP_DIR / filename

    # Download
    _download(video_url, local_path)

    # Probe
    probe = _ffprobe(local_path)
    meta = _extract_video_metadata(probe)

    # Basic safety checks (non-blocking for now — just return info)
    return {
        "status": "ok",
        "message": "Downloaded and probed video successfully",
        "received_input": {
            "video_url": video_url,
            "scale_factor": scale_factor
        },
        "local_path": str(local_path),
        "metadata": meta
    }

runpod.serverless.start({"handler": handler})
