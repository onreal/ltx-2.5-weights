# LTX-2.5 serverless worker

Image-to-video with Lightricks LTX-2.5 (distilled, INT8) on RunPod Serverless, for PipeHub clips.

- Image: built by RunPod from this repo's `Dockerfile`: `runpod/worker-comfyui:5.10.0-base`
  with ComfyUI replaced by `v0.42.3` (the base ships a ComfyUI without the LTX-2.5 nodes).
- Weights: not in the image. They live on two identical network volumes, `ltx-2.5-eu-ro-1`
  (EU-RO-1) and `ltx-2.5-eu-cz-1` (EU-CZ-1), under `models/`, read through
  `extra_model_paths.yaml`. Both are attached to the endpoint, so it can run in either
  datacenter. EU datacenters only.
- Workflow: `workflows/ltx25_i2v_api.json`, ComfyUI API format, the official
  `video_ltx2_5_i2v` template flattened with the prompt enhancer removed. Validated against
  ComfyUI v0.42.3.

## Volume layout

```
/runpod-volume/models/
  diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors   21.5 GB
  text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors           15.4 GB
  vae/ltx-2.5-video-vae-bf16.safetensors                                               1.5 GB
  vae/ltx-2.5-audio-vae-bf16.safetensors                                               0.4 GB
  latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors        1.0 GB
```

## Endpoint settings

| Setting | Value |
|---|---|
| Source | GitHub: this repo, branch `main`, Dockerfile `Dockerfile` |
| GPU | RTX PRO 6000 (96 GB), RTX PRO 6000 WK (96 GB), A100 SXM (80 GB) |
| Network volumes | `ltx-2.5-eu-ro-1` + `ltx-2.5-eu-cz-1`, which limits the endpoint to EU-RO-1 / EU-CZ-1 |
| Active workers | 0 |
| Max workers | 2 |
| Idle timeout | 60 s |
| Execution timeout | 600 s |
| FlashBoot | on |
| Scaling | Queue delay |
| Container disk | 20 GB |
| Env | `COMFY_LOG_LEVEL=INFO` |

## Request

`POST https://api.runpod.ai/v2/{endpoint_id}/run`, then poll `GET /status/{job_id}`.

### Clip request (what PipeHub sends)

```json
{ "input": { "prompt": "…", "image": "<base64 PNG/JPEG>", "seconds": 7.3 } }
```

| Field | Required | Meaning |
|---|---|---|
| `prompt` | yes | what happens in the clip |
| `image` | yes | the starting frame, base64 (a data URI prefix is allowed) |
| `seconds` | no (5) | rounded up to the next 8n + 1 frame count, at most 481 frames (20 s at 24 fps) |
| `audio` | no (false) | keep LTX's own soundtrack; PipeHub mixes its own, so it is off by default |
| `long_edge`, `fps`, `seed`, `negative_prompt` | no | default: env `LTX_LONG_EDGE` (1152), `LTX_FPS` (24), random seed, the template's negative prompt |

`handler.py` builds `workflows/ltx25_i2v_api.json` from it: the output keeps the image's aspect ratio
with its longer edge at `long_edge` (multiples of 64; stage 1 renders at half size and the latent
upsampler doubles it).

The result is the worker-comfyui output plus what was rendered:

```json
{ "images": [{ "filename": "clip_00001_.mp4", "type": "base64", "data": "…" }],
  "pipehub": { "width": 1152, "height": 768, "frames": 177, "fps": 24, "seconds": 7.3333, "audio": false } }
```

### Raw ComfyUI job

`{ "input": { "workflow": { … }, "images": [{ "name": "input.png", "image": "<base64>" }] } }` is
passed unchanged to the base worker-comfyui handler.

### Cost

`delayTime` (queue plus cold start) and `executionTime` (generation) in the status response are
what each clip is billed for, plus the endpoint's idle timeout. First measurement (2026-10-22, RTX
PRO 6000, 10 s at 1152×768 with audio): 216 s execution, about $0.21.
