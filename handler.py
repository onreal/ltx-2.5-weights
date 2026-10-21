"""Serverless entry point.

The job handling is the base image's worker-comfyui handler, unchanged: the
Dockerfile moves it to /worker_comfyui_handler.py and this file takes its place
as /handler.py, which the base image's start.sh runs.
"""

import runpod

from worker_comfyui_handler import handler

runpod.serverless.start({"handler": handler})
