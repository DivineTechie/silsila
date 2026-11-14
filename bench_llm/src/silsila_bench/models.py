"""Model registry for Silsila-Bench (pre-registered list, PREREGISTRATION.md "Models").

Serving facts were read from the model cards on the Hugging Face Hub (November 2026):
  * Jais 3 (inception42/Jais-3-7B, IFM/Jais-3-32B-FP8): vLLM >= 0.30 with `--reasoning-parser k2_horizon
    --enable-auto-tool-choice --tool-call-parser k2_horizon --trust-remote-code`. Native tool format is
    <ifm|tool_calls><ifm|tool_call>...</ifm|tool_call></ifm|tool_calls> (xml by default, json/xml_typed via
    chat_template_kwargs.tool_call_format). Thinking is inside <ifm|think>...</ifm|think>.
  * K2-Think-V2 (IFM/K2-Think-V2): Llama architecture, 72.5B parameters, Qwen/Hermes style <tool_call>
    JSON and <think> tags; the card serves it with TP=8 in BF16. Here: FP8 weights quantised on load on
    2 x H100 80GB.
  * BiMediX2-8B (MBZUAI/BiMediX2-8B-hf): LLaVA (Llama 3.1 8B) with the Llama 3.1 chat template; text-only
    prompts here. CC-BY-NC-SA 4.0: evaluation only.
  * Llama3-Med42-8B (m42-health/Llama3-Med42-8B): Llama 3 template without tool support, so tools are
    described in the prompt ("prompted" tool mode, AMENDMENTS.md A3).
  * Frontier reference: gpt-oss-120b on Fireworks (Azure GPT quota was not requested).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str                      # mlx | vllm | fireworks | azure
    model_id: str                      # model name sent in requests (HF repo for vLLM)
    label: str
    base_url: str | None = None
    api_key_env: str | None = None
    tool_mode: str = "native"          # native | prompted
    tool_args_as_dict: bool = False    # send earlier tool-call arguments back as objects (Jais template needs it)
    max_tokens: int = 4096
    temperature: float = 0.0
    extra_body: dict[str, Any] = field(default_factory=dict)
    concurrency: int = 32
    rpm: int | None = None
    timeout_s: float = 1800.0
    reasoning: bool = False
    licence: str = ""
    not_run_reason: str | None = None  # default reason shown in the report while no results exist
    # serving on Modal (see modal_vllm.py)
    gpu: str | None = None
    est_output_tokens: int = 800       # mean output tokens per request, for cost estimates only

    def resolved_base_url(self) -> str:
        if self.provider == "vllm":
            env = "MODAL_URL_" + self.name.upper().replace("-", "_").replace(".", "_")
            if os.environ.get(env):
                return os.environ[env].rstrip("/") + ("" if os.environ[env].rstrip("/").endswith("/v1") else "/v1")
            ws = os.environ.get("MODAL_WORKSPACE")
            if not ws:
                raise RuntimeError(f"Set {env} (the Modal URL printed by `modal deploy`) or MODAL_WORKSPACE")
            return f"https://{ws}--silsila-vllm-{self.name}-serve.modal.run/v1"
        if self.provider == "azure":
            return os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        assert self.base_url
        return self.base_url

    def api_key(self) -> str:
        if self.api_key_env:
            v = os.environ.get(self.api_key_env)
            if not v:
                raise RuntimeError(f"{self.api_key_env} is not set (bench_llm/.env)")
            return v
        return "not-needed"


MODELS: dict[str, ModelSpec] = {m.name: m for m in [
    ModelSpec(
        name="jais-3-7b-mlx", provider="mlx", model_id="IFM/Jais-3-7B-MLX-8bit", label="Jais 3 7B (MLX 8-bit, local)",
        base_url="http://127.0.0.1:8080/v1", tool_args_as_dict=True, max_tokens=16384, concurrency=1,
        reasoning=True, licence="Apache-2.0", est_output_tokens=4000,
        not_run_reason="local smoke test only; the scored run uses vLLM on Modal",
    ),
    ModelSpec(
        name="jais-3-7b", provider="vllm", model_id="inception42/Jais-3-7B", label="Jais 3 7B",
        api_key_env="SILSILA_VLLM_API_KEY", tool_args_as_dict=True, max_tokens=32768, concurrency=64,
        reasoning=True, licence="Apache-2.0", gpu="H100", est_output_tokens=4000,
    ),
    ModelSpec(
        name="jais-3-32b", provider="vllm", model_id="IFM/Jais-3-32B-FP8", label="Jais 3 32B (FP8)",
        api_key_env="SILSILA_VLLM_API_KEY", tool_args_as_dict=True, max_tokens=32768, concurrency=48,
        reasoning=True, licence="Apache-2.0", gpu="H100", est_output_tokens=4000,
    ),
    ModelSpec(
        name="k2-think-v2", provider="vllm", model_id="IFM/K2-Think-V2", label="K2-Think-V2 (72B, FP8 on load)",
        api_key_env="SILSILA_VLLM_API_KEY", max_tokens=32768, concurrency=32, reasoning=True,
        licence="Apache-2.0", gpu="H100:2", est_output_tokens=6000,
    ),
    ModelSpec(
        name="bimedix2-8b", provider="vllm", model_id="MBZUAI/BiMediX2-8B-hf", label="BiMediX2 8B",
        api_key_env="SILSILA_VLLM_API_KEY", max_tokens=4096, concurrency=64,
        licence="CC-BY-NC-SA-4.0 (evaluation only)", gpu="H100", est_output_tokens=500,
    ),
    ModelSpec(
        name="llama3-med42-8b", provider="vllm", model_id="m42-health/Llama3-Med42-8B", label="Llama3-Med42 8B",
        api_key_env="SILSILA_VLLM_API_KEY", tool_mode="prompted", max_tokens=4096, concurrency=64,
        licence="Llama 3 Community Licence", gpu="H100", est_output_tokens=500,
    ),
    ModelSpec(
        name="gpt-oss-120b", provider="fireworks", model_id="accounts/fireworks/models/gpt-oss-120b",
        label="gpt-oss-120b (Fireworks, frontier reference)", base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY", max_tokens=16384, concurrency=16, rpm=300, reasoning=True,
        licence="Apache-2.0", est_output_tokens=1500,
    ),
    ModelSpec(
        name="azure-gpt", provider="azure", model_id=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt"),
        label="GPT-class model on Azure OpenAI", api_key_env="AZURE_OPENAI_API_KEY", max_tokens=16384,
        concurrency=8, rpm=60, reasoning=True, est_output_tokens=1500,
        not_run_reason="Azure GPT quota not requested; gpt-oss-120b on Fireworks is the frontier reference",
    ),
]}

# Models in the pre-registered list (the MLX entry is a local smoke-test path for Jais 3 7B).
PREREGISTERED = ("jais-3-7b", "jais-3-32b", "k2-think-v2", "bimedix2-8b", "llama3-med42-8b", "gpt-oss-120b")


def get(name: str) -> ModelSpec:
    try:
        return MODELS[name]
    except KeyError:
        raise SystemExit(f"Unknown model '{name}'. Known: {', '.join(MODELS)}")
