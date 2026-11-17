"""Serve one benchmark model with vLLM on a Hugging Face Inference Endpoint (an alternative to Modal).

    set -a; source .env; set +a                      # HF_TOKEN with endpoint rights
    uv run --with huggingface_hub python scripts/hf_endpoint.py create k2-think-v2
    uv run --with huggingface_hub python scripts/hf_endpoint.py status k2-think-v2   # prints the URL when running
    uv run --with huggingface_hub python scripts/hf_endpoint.py delete k2-think-v2   # stops the billing

The endpoint is private (it needs the Hugging Face token as the bearer key). Run the benchmark against it with
    SILSILA_VLLM_API_KEY="$HF_TOKEN" uv run python -m silsila_bench.run --model k2-think-v2 --track all \
        --subset t5-sample --base-url <URL>/v1
Billing runs from creation to deletion: delete the endpoint as soon as the run is done.
"""

from __future__ import annotations

import os
import sys

from huggingface_hub import HfApi

VLLM_IMAGE = "vllm/vllm-openai:v0.33.0"  # the same vLLM version as modal_vllm.py

# The serving flags are the ones in modal_vllm.py; only the hardware differs (see AMENDMENTS.md, A12).
ENDPOINTS = {
    "k2-think-v2": {
        "name": "silsila-k2-think-v2",
        "repo": "IFM/K2-Think-V2",
        "vendor": "aws", "region": "us-west-2", "instance_type": "nvidia-h200", "instance_size": "x2",
        "args": ["--tensor-parallel-size", "2", "--quantization", "fp8", "--reasoning-parser", "deepseek_r1",
                 "--enable-auto-tool-choice", "--tool-call-parser", "hermes", "--max-model-len", "49152",
                 "--gpu-memory-utilization", "0.92"],
    },
}


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("create", "status", "delete") or sys.argv[2] not in ENDPOINTS:
        raise SystemExit(__doc__)
    action, cfg = sys.argv[1], ENDPOINTS[sys.argv[2]]
    api = HfApi(token=os.environ["HF_TOKEN"])
    if action == "create":
        ep = api.create_inference_endpoint(
            cfg["name"], repository=cfg["repo"], framework="pytorch", task="text-generation", accelerator="gpu",
            vendor=cfg["vendor"], region=cfg["region"], instance_type=cfg["instance_type"], instance_size=cfg["instance_size"],
            type="authenticated", min_replica=1, max_replica=1,
            # a plain custom container: with the managed "vLLM" image type the platform adds its own --model flag,
            # which clashes with the command below
            custom_image={"url": VLLM_IMAGE, "port": 8000, "healthRoute": "/health"},
            container_command=["vllm", "serve", "/repository", "--served-model-name", cfg["repo"], "--host", "0.0.0.0",
                               "--port", "8000", "--generation-config", "vllm", *cfg["args"]],
            env={"VLLM_USE_FLASHINFER_SAMPLER": "0"},
        )
        print(ep.name, ep.status)
    elif action == "status":
        ep = api.get_inference_endpoint(cfg["name"])
        print(ep.status, ep.url or "")
    else:
        api.delete_inference_endpoint(cfg["name"])
        print("deleted", cfg["name"])


if __name__ == "__main__":
    main()
