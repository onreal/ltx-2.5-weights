"""Serverless entry point.

Two kinds of job:

- `{"workflow": ..., "images": [...]}`: a raw ComfyUI job, passed unchanged to the base image's
  worker-comfyui handler (moved to /worker_comfyui_handler.py by the Dockerfile).
- `{"prompt": ..., "image": ..., "seconds": ...}`: a PipeHub clip request. It is turned into the
  LTX-2.5 image-to-video workflow here, so PipeHub needs to know nothing about the model: frame
  counts, sizes and node ids stay next to the model they belong to.

A clip request returns the base handler's output plus `pipehub`, describing what was rendered:
`{width, height, frames, fps, seconds}`.
"""

import base64
import copy
import io
import json
import math
import os
import random

import runpod
from PIL import Image

from worker_comfyui_handler import handler as comfyui_handler

WORKFLOW_PATH = os.environ.get("LTX_WORKFLOW_PATH", "/workflows/ltx25_i2v_api.json")

# Output size: the image's aspect ratio, its longer edge scaled to LONG_EDGE. Stage 1 renders at
# half size and the latent upsampler doubles it, so both sides are multiples of SIZE_MULTIPLE.
LONG_EDGE = int(os.environ.get("LTX_LONG_EDGE", "1152"))
SIZE_MULTIPLE = 64
FPS = int(os.environ.get("LTX_FPS", "24"))
# LTX-2.5 takes 8n + 1 frames, at most 481 (20 s at 24 fps).
MAX_FRAMES = int(os.environ.get("LTX_MAX_FRAMES", "481"))
DEFAULT_SECONDS = 5.0

NEGATIVE_PROMPT = "pc game, console game, video game, cartoon, childish, ugly"


def _strip_data_uri(data):
    return data.split(",", 1)[1] if data.startswith("data:") else data


def _output_size(image_bytes, long_edge):
    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
    scale = long_edge / max(width, height)

    def fit(side):
        return max(SIZE_MULTIPLE, int(round(side * scale / SIZE_MULTIPLE)) * SIZE_MULTIPLE)

    return fit(width), fit(height)


def _frame_count(seconds, fps):
    """The smallest 8n + 1 frame count that lasts at least `seconds`, capped at MAX_FRAMES."""
    frames = int(math.ceil(seconds * fps / 8.0)) * 8 + 1
    return max(9, min(frames, MAX_FRAMES))


def build_clip_job(job_input):
    """Turn a PipeHub clip request into a worker-comfyui job and a description of what it renders."""
    prompt = str(job_input.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    image_b64 = _strip_data_uri(str(job_input.get("image") or ""))
    if not image_b64:
        raise ValueError("image is required: this endpoint animates a starting frame")
    image_bytes = base64.b64decode(image_b64)

    seconds = float(job_input.get("seconds") or DEFAULT_SECONDS)
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    fps = int(job_input.get("fps") or FPS)
    width, height = _output_size(image_bytes, int(job_input.get("long_edge") or LONG_EDGE))
    frames = _frame_count(seconds, fps)
    seed = int(job_input.get("seed") or random.randint(1, 2**48))

    with open(WORKFLOW_PATH) as handle:
        workflow = copy.deepcopy(json.load(handle))

    workflow["1"]["inputs"]["image"] = "input.png"
    workflow["20"]["inputs"]["text"] = prompt
    workflow["21"]["inputs"]["text"] = str(job_input.get("negative_prompt") or NEGATIVE_PROMPT)
    workflow["22"]["inputs"]["frame_rate"] = fps
    workflow["30"]["inputs"].update(width=width // 2, height=height // 2, length=frames)
    workflow["32"]["inputs"].update(frames_number=frames, frame_rate=fps)
    workflow["40"]["inputs"]["noise_seed"] = seed
    workflow["72"]["inputs"]["fps"] = fps
    # PipeHub mixes its own narration, songs and effects: by default the clip carries no sound.
    if not job_input.get("audio"):
        workflow["72"]["inputs"].pop("audio", None)

    described = {
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "seconds": round((frames - 1) / fps, 4),
        "audio": bool(job_input.get("audio")),
    }
    return {"workflow": workflow, "images": [{"name": "input.png", "image": image_b64}]}, described


def handler(job):
    job_input = job.get("input") or {}
    if "workflow" in job_input:
        return comfyui_handler(job)

    try:
        comfy_input, described = build_clip_job(job_input)
    except (ValueError, OSError) as error:
        return {"error": f"Invalid clip request: {error}"}

    result = comfyui_handler({**job, "input": comfy_input})
    if isinstance(result, dict) and "error" not in result:
        result["pipehub"] = described
    return result


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
