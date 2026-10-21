# LTX-2.5 image-to-video worker for RunPod Serverless.
#
# Built on RunPod's ComfyUI worker. Its handler, start script and network
# volume support are used unchanged; only ComfyUI itself is replaced, because
# the base image ships a ComfyUI that predates the native LTX-2.5 nodes.
#
# The model weights are NOT in this image. They live on the network volume,
# mounted at /runpod-volume, under models/ (see extra_model_paths.yaml).
FROM runpod/worker-comfyui:5.10.0-base

ARG COMFYUI_VERSION=v0.42.3

# Replace ComfyUI with a release that has the LTX-2.5 nodes
# (LTXVDualCFGGuider, LTXVImgToVideoInplace, LTXVEmptyLatentAudio, ...) and
# loads the comfy-int8-convrot checkpoints natively. The base image's custom
# nodes (ComfyUI-Manager) are carried over.
RUN set -eux; \
    git clone --depth 1 --branch "${COMFYUI_VERSION}" \
      https://github.com/comfyanonymous/ComfyUI.git /tmp/comfyui; \
    cp -a /comfyui/custom_nodes/. /tmp/comfyui/custom_nodes/; \
    rm -rf /comfyui; \
    mv /tmp/comfyui /comfyui

# The worker launches ComfyUI with /opt/venv's python, so ComfyUI's
# dependencies go there. Same pins as the base image: torch on cu128 builds
# (runs on every RunPod driver >= 570), transformers < 5, huggingface-hub < 1.
RUN uv pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 \
      --index-url https://download.pytorch.org/whl/cu128 \
    && uv pip install -r /comfyui/requirements.txt \
    && for r in /comfyui/custom_nodes/*/requirements.txt; do \
         [ -f "$r" ] && uv pip install -r "$r" || true; \
       done \
    && uv pip install "transformers>=4.50.3,<5" "huggingface-hub<1.0"

# Fail the build, not a live worker, if ComfyUI cannot start.
RUN cd /comfyui && timeout 300 python main.py --quick-test-for-ci --cpu

COPY extra_model_paths.yaml /comfyui/extra_model_paths.yaml

# Our handler.py starts the base image's handler, which is moved aside first.
RUN mv /handler.py /worker_comfyui_handler.py
COPY handler.py /handler.py
COPY workflows/ /workflows/

# The base image's start script: starts ComfyUI, then runs /handler.py.
CMD ["/start.sh"]
