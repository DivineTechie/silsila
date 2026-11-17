#!/usr/bin/env bash
# Wait for a Hugging Face endpoint made by hf_endpoint.py to be running, then print its URL.
# If it fails or does not come up in MAX_MIN minutes it is deleted, so that it stops costing money.
# Usage (from bench_llm/, with .env loaded):  bash scripts/hf_wait.sh k2-think-v2
MODEL="${1:?model name}"; MAX_MIN="${MAX_MIN:-100}"
cd "$(dirname "$0")/.." || exit 1
for i in $(seq 1 "$MAX_MIN"); do
  out=$(uv run -q --with huggingface_hub python scripts/hf_endpoint.py status "$MODEL" 2>&1 | tail -1)
  state=${out%% *}
  echo "$(date +%H:%M) $state"
  case "$state" in
    running) echo "URL ${out#* }"; exit 0 ;;
    failed) uv run -q --with huggingface_hub python - "$MODEL" <<'PY'
import os, sys
sys.path.insert(0, "scripts")
from hf_endpoint import ENDPOINTS
from huggingface_hub import HfApi
ep = HfApi(token=os.environ["HF_TOKEN"]).get_inference_endpoint(ENDPOINTS[sys.argv[1]]["name"])
print((ep.raw.get("status", {}).get("errorMessage") or "")[-1500:])
PY
      uv run -q --with huggingface_hub python scripts/hf_endpoint.py delete "$MODEL"; exit 1 ;;
  esac
  sleep 60
done
echo "not running after $MAX_MIN minutes; deleting"
uv run -q --with huggingface_hub python scripts/hf_endpoint.py delete "$MODEL"; exit 2
