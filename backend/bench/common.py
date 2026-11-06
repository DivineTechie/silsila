"""Shared helpers for the benchmark scripts: output paths, process pool,
provenance, JSON/CSV writers."""

from __future__ import annotations

import csv
import json
import math
import os
import platform
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

REPO = Path(__file__).resolve().parents[2]
EVIDENCE = REPO / "docs" / "evidence"
LOGS = EVIDENCE / "logs"


def workers() -> int:
    env = os.environ.get("SILSILA_BENCH_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(8, (os.cpu_count() or 2) - 1))


_POOL: ProcessPoolExecutor | None = None


def pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=workers())
    return _POOL


def mapper(fn: Callable, jobs: list) -> list:
    """Order-preserving parallel map. Results do not depend on scheduling:
    every job carries its own seed."""
    if workers() == 1 or len(jobs) < 4:
        return [fn(j) for j in jobs]
    chunk = max(1, len(jobs) // (workers() * 8))
    return list(pool().map(fn, jobs, chunksize=chunk))


def shutdown() -> None:
    global _POOL
    if _POOL is not None:
        _POOL.shutdown()
        _POOL = None


def _clean(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating,)):
        x = float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def provenance(quick: bool, seed: int) -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True, timeout=5).stdout.strip())
    except Exception:  # pragma: no cover
        commit, dirty = "unknown", True
    import scipy

    return {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": commit, "working_tree_dirty": dirty,
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "platform": platform.platform(), "workers": workers(), "quick": quick, "seed": seed,
        "data_note": "SYNTHETIC: all families are simulated; no real person's data is used.",
    }


def write_json(name: str, obj: Any) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    p = EVIDENCE / name
    p.write_text(json.dumps(_clean(obj), indent=2, sort_keys=False) + "\n")
    return p


def write_csv(name: str, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    p = LOGS / name
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _fmt(r.get(k)) for k in fields})
    return p


def _fmt(v: Any) -> Any:
    if isinstance(v, float):
        return f"{v:.12g}"
    if isinstance(v, (list, tuple)):
        return ";".join(_fmt(x) if not isinstance(x, str) else x for x in v)
    return v


class Timer:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()

    def __call__(self) -> float:
        return round(time.perf_counter() - self.t0, 2)
