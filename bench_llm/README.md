# Silsila-Bench

Where can language models be trusted in genetic counselling for cousin-marriage families? Silsila-Bench
asks models carrier and child-risk questions about family trees told as stories in English, Modern
Standard Arabic, Gulf Arabic and Arabizi, and scores them against the exact Silsila engine.

* Contract: [`PREREGISTRATION.md`](PREREGISTRATION.md). Every deviation or clarification:
  [`AMENDMENTS.md`](AMENDMENTS.md).
* Families are synthetic and every person is fictional. The item set must not be published before the
  challenge is judged: `data/`, `runs/` and `../docs/evidence/logs/bench/` hold item text.
* This is not a leaderboard. Results say which jobs a model may do inside Silsila.

## Layout

| File | What it does |
|---|---|
| `src/silsila_bench/items.py` | 150 families from `silsila.sim.kindred` with fixed seeds (50 no loop, 50 one first-cousin marriage, 50 multiple incl. double first cousins), loci HBB/CYP21A2/SMN1, questions (a) carrier and (b) child affected, gold from the exact engine; `python -m silsila_bench.items` writes `data/families.jsonl` with full gold trees |
| `render.py` | Story templates in 4 registers, kinship told relationally (ابن عمي, بنت خالي, ibn 3ammi, "my father's brother's son"); Arabic templates are not native-reviewed |
| `prompts.py` | Fixed system prompt, T1/T2/T3/T5 prompts, prompted-tool text |
| `tools.py` | `compute_family_risk` (T2) and `submit_family_tree` / incremental tools (T3) on the exact engine; tree comparison |
| `parse.py` | Probability parser (%, decimals, 1 in N, N in M, Arabic-Indic digits, Arabic/Arabizi number and fraction words) |
| `score.py` | Bands, T2/T3/T4/T5 metrics, family bootstrap CIs, splits, PubMed (NCBI E-utilities) checks with cache |
| `models.py` | Model registry (endpoints, tool mode, token limits, GPUs) |
| `clients.py` | One OpenAI-compatible async client: mlx_lm.server, vLLM on Modal, Fireworks, Azure; retries, rate limit, text tool-call parsing |
| `runner.py`, `run.py` | Resumable runs, JSONL per model and track in `runs/<model>/<track>.jsonl` |
| `modal_vllm.py` | Modal app serving one model with vLLM (OpenAI API, tool parser per model) |
| `report.py` | Writes `../docs/evidence/silsila_bench.json`, `silsila_bench.md` and per-prompt CSV logs |
| `estimate.py` | Token, GPU-hour and cost estimates from the real prompts |

## Setup

```bash
cd bench_llm
uv sync
cp .env.example .env      # FIREWORKS_API_KEY, HF_TOKEN, SILSILA_VLLM_API_KEY, MODAL_WORKSPACE
uv run pytest -q          # all tests use mocks; no network, no paid calls
uv run python -m silsila_bench.items      # optional: write data/families.jsonl (gold trees)
uv run python -m silsila_bench.run --model jais-3-7b --track T1 --limit 2 --dry-run   # see a prompt
```

Tracks: T1 1,200 prompts, T2 600, T3 300, T5 50 per model; T4 is computed from T1.

## Run locally (Apple silicon, mlx_lm.server)

Smoke tests only (the scored Jais 3 7B run uses vLLM). 16 GB is enough for the 8-bit model (peak ~10 GB).

```bash
HF_HUB_OFFLINE=1 uv run mlx_lm.server --model IFM/Jais-3-7B-MLX-8bit --trust-remote-code --port 8080 \
    --prompt-cache-size 1 --prompt-cache-bytes 536870912 --kv-bits 8
uv run python -m silsila_bench.run --model jais-3-7b-mlx --track T1 --limit 4 --max-tokens 6000 \
    --runs-dir /tmp/silsila-smoke
```

On a 16 GB Mac the default server settings ran out of GPU memory on the second turn of a T2 tool
conversation (`kIOGPUCommandBufferCallbackErrorOutOfMemory`, after which the server answers 404); the
small prompt cache and 8-bit KV cache above avoid holding several long prompts. Local decoding was about
11 tokens/s, so a high-effort Jais 3 answer (several thousand thinking tokens) takes about 10 minutes:
use the local path for checking prompts and parsing only.

`mlx_lm.server` returns Jais 3 thinking inside `content` and does not parse its tool calls; the client
strips `<ifm|think>` and reads `<ifm|tool_call>` blocks itself.

## Run on Modal (vLLM)

One app per model, chosen at deploy time. The server is protected by `SILSILA_VLLM_API_KEY` and scales
to zero after 15 minutes idle.

```bash
set -a; source .env; set +a
SILSILA_BENCH_MODEL=jais-3-7b       uv run modal deploy src/silsila_bench/modal_vllm.py
SILSILA_BENCH_MODEL=jais-3-32b      uv run modal deploy src/silsila_bench/modal_vllm.py
SILSILA_BENCH_MODEL=k2-think-v2     uv run modal deploy src/silsila_bench/modal_vllm.py
SILSILA_BENCH_MODEL=bimedix2-8b     uv run modal deploy src/silsila_bench/modal_vllm.py
SILSILA_BENCH_MODEL=llama3-med42-8b uv run modal deploy src/silsila_bench/modal_vllm.py
```

The client finds the URL from `MODAL_URL_<MODEL>` (e.g. `MODAL_URL_JAIS_3_7B`) or from `MODAL_WORKSPACE`
(`https://<workspace>--silsila-vllm-<model>-serve.modal.run/v1`). The first request waits for the
container to download weights and start (up to ~10-20 minutes for the large models; weights are cached
in the `silsila-hf-cache` volume). Then:

```bash
uv run python -m silsila_bench.run --model jais-3-7b --track T1 --limit 20    # check a few first
uv run python -m silsila_bench.run --model jais-3-7b --track all
uv run python -m silsila_bench.run --model gpt-oss-120b --track all          # Fireworks, no Modal
uv run python -m silsila_bench.report                                         # score + evidence files
uv run modal app stop silsila-vllm-jais-3-7b                                  # stop paying
```

Runs are resumable: rerunning skips finished items and retries failed ones. Use `--concurrency` to
lower the load and `--base-url` to point at any other OpenAI-compatible endpoint.

| Model | Served as | GPU | Tool calls |
|---|---|---|---|
| Jais 3 7B | `inception42/Jais-3-7B` BF16 | 1 × H100 | native, vLLM `k2_horizon` parser |
| Jais 3 32B | `IFM/Jais-3-32B-FP8` | 1 × H100 | native, `k2_horizon` |
| K2-Think-V2 | `IFM/K2-Think-V2`, FP8 on load | 2 × H100 | native, `hermes` |
| BiMediX2 8B | `MBZUAI/BiMediX2-8B-hf` (text only) | 1 × H100 | native, `llama3_json` |
| Llama3-Med42 8B | `m42-health/Llama3-Med42-8B` | 1 × H100 | prompted (template has no tools) |
| gpt-oss-120b | Fireworks API | – | native |

## Cost estimates (full pre-registered run, per model)

From `uv run python -m silsila_bench.estimate` (prompt tokens measured from the real prompts; mean
prompt ~680 tokens for T1, ~1,400 for T2; ~2,870 requests per model). Output tokens per request and
vLLM throughput are assumptions: reasoning models (Jais 3, K2-Think-V2) think at high effort by default
and could use 2-3x the assumed tokens, so the upper figure is the planning number. Modal H100 at
$3.95/GPU-hour (check the current price); Fireworks gpt-oss-120b at $0.15/$0.60 per million tokens.

| Model | GPU | Output tokens (assumed) | GPU-hours | Cost (USD) |
|---|---|---|---|---|
| Jais 3 7B | H100 | 12.8 M (4k/request) | 1.8 (up to ~5) | 7 (up to ~20) |
| Jais 3 32B FP8 | H100 | 12.8 M | 4.0 (up to ~12) | 16 (up to ~45) |
| K2-Think-V2 FP8 | 2 × H100 | 18.6 M (6k/request) | 15.5 (up to ~45) | 61 (up to ~180) |
| BiMediX2 8B | H100 | 2.8 M | 0.7 | 3 |
| Llama3-Med42 8B | H100 | 2.8 M | 0.7 | 3 |
| gpt-oss-120b | Fireworks | 5.7 M | – | ~4 (up to ~10) |

Each GPU figure includes ~0.4 h of start-up and idle time. Check real token counts and wall time on
the first 20-50 items (`runs/<model>/<track>.jsonl` records usage per turn) before launching the rest.

## Outputs

* `../docs/evidence/silsila_bench.json`: all metrics, overall and by register and family type, each
  with a 95% bootstrap interval over families; status and reason for every model (including not run).
* `../docs/evidence/silsila_bench.md`: tables for the Markdown evidence section (models in a fixed
  order, no ranking).
* `../docs/evidence/logs/bench/<model>_<track>.csv`: prompt, raw answer, parsed value, gold and band
  for every prompt (T3: tree comparison and engine answers; T5: every PMID with title and review flag).

## Limitations

* Synthetic families with fictional people; real family stories are messier (half-siblings, unknown
  parents, remarriage and uncertain diagnoses are not included).
* The MSA, Gulf Arabic and Arabizi templates were written by the team without native-speaker review;
  register differences may partly reflect template quality.
* One sample per prompt at temperature 0 (pre-registered); reasoning models are recommended to be
  sampled and may loop or run out of tokens at temperature 0 (counted as "no number").
* The prompts give the population numbers the engine uses (AMENDMENTS A1); real users would not.
* Models without native tool support get tools described in the prompt (A3), which may disadvantage them.
* K2-Think-V2 runs in FP8 on 2 GPUs rather than BF16 on 8 (A7).
* PMID relatedness is a keyword check; every flagged citation needs review by the team.
* The probability parser takes the answer line or first number; unusual phrasings may be missed and are
  visible in the CSV logs.
