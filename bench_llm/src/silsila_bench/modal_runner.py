"""Run Silsila-Bench clients on Modal, so the benchmark keeps going with the laptop switched off.

The vLLM servers (modal_vllm.py) only answer requests; this app sends them. It runs the same
`silsila_bench.run` command as on a laptop, inside a small CPU container, and keeps the per-prompt logs
on a Modal Volume. The runner skips items already answered, so a run can be stopped and restarted.
A scheduled spend guard stops every Silsila GPU app once spend reaches the limit.

    cd bench_llm
    set -a; . ./.env; set +a
    uv run modal deploy src/silsila_bench/modal_runner.py
    uv run modal volume put silsila-bench-runs runs/<model> /<model>     # seed earlier results
    uv run python -m silsila_bench.modal_runner start jais-3-7b          # spawn a detached run
    uv run modal volume get silsila-bench-runs /<model> runs/            # fetch results

The repository layout is mirrored under /repo so that the packages find their data as they do locally.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import modal

# Local paths matter only on the laptop, where the image is built; in the container this file is /root/.
HERE = Path(__file__).resolve()
BENCH = HERE.parents[2] if modal.is_local() else Path("/nonexistent")   # bench_llm/
ROOT = BENCH.parent                                                      # repository root
REPO = "/repo"
RUNS = f"{REPO}/bench_llm/runs"
SPEND_LIMIT = float(os.environ.get("SILSILA_SPEND_LIMIT", "120"))
SPEND_START = os.environ.get("SILSILA_SPEND_START", "2026-11-14")
GPU_APPS = ("jais-3-7b", "jais-3-32b", "k2-think-v2", "bimedix2-8b", "llama3-med42-8b")
HOUR = 3600

image = modal.Image.debian_slim(python_version="3.12")
image = (
    image
    .uv_pip_install("httpx", "openai", "pyyaml", "numpy", "scikit-learn", "joblib", "pydantic", "fastapi",
                    "pyjwt", "fhir-resources", f"modal=={modal.__version__}")
    .env({"PYTHONPATH": f"{REPO}/backend/src:{REPO}/bench_llm/src", "PYTHONUNBUFFERED": "1"})
    .add_local_dir(ROOT / "backend" / "src", f"{REPO}/backend/src", ignore=["**/__pycache__"])
    .add_local_dir(BENCH / "src", f"{REPO}/bench_llm/src", ignore=["**/__pycache__"])
    .add_local_dir(BENCH / "data", f"{REPO}/bench_llm/data")
    .add_local_dir(ROOT / "data" / "params", f"{REPO}/data/params")
    .add_local_dir(ROOT / "data" / "content", f"{REPO}/data/content")
)
runs_vol = modal.Volume.from_name("silsila-bench-runs", create_if_missing=True)

_keys = ("SILSILA_VLLM_API_KEY", "FIREWORKS_API_KEY", "MODAL_WORKSPACE")
_secret_env = {k: os.environ[k] for k in _keys if os.environ.get(k)}
secrets = [modal.Secret.from_dict(_secret_env)] if _secret_env else []

app = modal.App("silsila-bench-runner")


@app.function(image=image, volumes={RUNS: runs_vol}, secrets=secrets, timeout=24 * HOUR, cpu=1.0, memory=2048)
def run_model(model: str, track: str = "all", extra: list[str] | None = None) -> int:
    """Run one model's tracks; commit the logs to the volume every two minutes and at the end."""
    stop = threading.Event()

    def commit_loop() -> None:
        while not stop.wait(120):
            try:
                runs_vol.commit()
            except Exception as e:  # keep running; the final commit will retry
                print("volume commit failed:", e, flush=True)

    threading.Thread(target=commit_loop, daemon=True).start()
    cmd = [sys.executable, "-m", "silsila_bench.run", "--model", model, "--track", track,
           "--ready-timeout", "2400", *(extra or [])]
    print("running:", " ".join(cmd), flush=True)
    try:
        code = subprocess.run(cmd, cwd=f"{REPO}/bench_llm").returncode
    finally:
        stop.set()
        runs_vol.commit()
    print("exit", code, flush=True)
    return code


def silsila_gpu_spend() -> float:
    """Dollars spent by the Silsila vLLM apps since SPEND_START: complete days plus today's complete hours."""
    import datetime as dt

    ws = modal.Workspace.from_context()
    start = dt.datetime.fromisoformat(SPEND_START).replace(tzinfo=dt.timezone.utc)
    now = dt.datetime.now(dt.timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = list(ws.billing.report(start=start, end=today)) if today > start else []
    rows += list(ws.billing.report(start=today, end=now, resolution="h"))
    return round(float(sum(r.cost for r in rows if r.description.startswith("silsila-vllm"))), 2)


@app.function(image=image, schedule=modal.Period(minutes=20), timeout=600)
def spend_guard() -> dict:
    """Stop every Silsila GPU app (which also ends the runs) once spend reaches the limit."""
    spent = silsila_gpu_spend()
    print(f"spend={spent} limit={SPEND_LIMIT}", flush=True)
    if spent < SPEND_LIMIT:
        return {"spent": spent, "stopped": False}
    for name in GPU_APPS:
        try:
            modal.App.lookup(f"silsila-vllm-{name}").stop()
            print("stopped", name, flush=True)
        except Exception as e:  # app not deployed, or already stopped
            print("not stopped", name, type(e).__name__, flush=True)
    return {"spent": spent, "stopped": True}


def _start(model: str, track: str = "all", extra: list[str] | None = None) -> None:
    fn = modal.Function.from_name("silsila-bench-runner", "run_model")
    call = fn.spawn(model, track, extra or [])
    print(f"spawned {model} {track} {' '.join(extra or [])}: {call.object_id}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "start":
        # start <model> [track] [extra run.py args...], e.g. start jais-3-32b all --subset t5-sample
        _start(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "all", sys.argv[4:])
    elif len(sys.argv) == 2 and sys.argv[1] == "spend":
        print(modal.Function.from_name("silsila-bench-runner", "spend_guard").remote())
    else:
        print(__doc__)
