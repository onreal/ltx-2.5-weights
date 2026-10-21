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

`POST https://api.runpod.ai/v2/{endpoint_id}/run`

```json
{
  "input": {
    "workflow": { "...": "workflows/ltx25_i2v_api.json, with the values below filled in" },
    "images": [{ "name": "input.png", "image": "<base64 PNG/JPEG>" }]
  }
}
```

Values to set per clip:

| Node | Input | Meaning |
|---|---|---|
| `20` | `text` | the prompt |
| `30` | `width`, `height` | **half** the output size. Stage 1 renders at half size and the latent upsampler doubles it. Use multiples of 32, so the output is a multiple of 64. |
| `30`, `32` | `length`, `frames_number` | frame count, `8n + 1` (121 = 5 s at 24 fps) |
| `22`, `32`, `72` | `frame_rate`, `frame_rate`, `fps` | frames per second (24) |
| `40`, `60` | `noise_seed` | seeds for stage 1 and stage 2 |

Then poll `GET /status/{job_id}`. The MP4 comes back in `output.images[0].data` as base64, or
as a URL when the S3 upload variables are set. The clip carries LTX's own audio track: discard
it, since PipeHub mixes its own narration, songs and effects.

`delayTime` (queue plus cold start) and `executionTime` (generation) in the status response
are what each clip is billed for, together with the 60 s idle timeout.
