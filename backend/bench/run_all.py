"""Run every Silsila simulator/engine benchmark and write docs/evidence.

    cd backend && uv run python -m bench.run_all            # full (~15 min on a 10-core laptop)
    cd backend && uv run python -m bench.run_all --quick    # smoke run (~4 min)
    cd backend && uv run python -m bench.run_all --only b1,b3

Seeds are fixed in each benchmark; results do not depend on the number of
worker processes (SILSILA_BENCH_WORKERS, default min(8, cores-1)).
"""

from __future__ import annotations

import argparse
import sys
import warnings

from . import b1_engine, b2_robustness, b3_nejm, b4_uae, b5_sensitivity, perf, report
from .common import Timer, provenance, shutdown, write_json

STEPS = {"b1": b1_engine.run, "b2": b2_robustness.run, "b3": b3_nejm.run, "b4": b4_uae.run, "b5": b5_sensitivity.run, "perf": perf.run}


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="small sample sizes (smoke test)")
    ap.add_argument("--only", default="", help="comma-separated subset of " + ",".join(STEPS))
    args = ap.parse_args(argv)
    chosen = [s for s in args.only.split(",") if s] or list(STEPS)
    total = Timer()
    times = {}
    try:
        for name in chosen:
            t = Timer()
            print(f"[run_all] {name} ...", flush=True)
            STEPS[name](args.quick)
            times[name] = t()
            print(f"[run_all] {name} done in {times[name]} s", flush=True)
    finally:
        shutdown()
    write_json("run_all.json", {"provenance": provenance(args.quick, 0), "steps_seconds": times, "total_seconds": total(),
                                "command": "cd backend && uv run python -m bench.run_all" + (" --quick" if args.quick else "")})
    report.write_readme()
    print(f"[run_all] total {total()} s; report: docs/evidence/README.md", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
