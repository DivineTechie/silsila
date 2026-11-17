"""Load test for the hosted Silsila demo.

What it does
    Runs fixed-duration scenarios against the hosted API and web app at several concurrency levels and
    records, for each one: requests completed, errors (non-2xx or exceptions) with a count per status
    code, requests per second, and latency median / p95 / p99 / max in milliseconds.

Scenarios
    light_reads         GET /api/guide, POST /api/guide/ask, GET web home page (rotated by each client)
    relative_opens_link GET /api/r/{code} for a demo relative's invitation link (code from POST /api/demo/relative)
    exact_recalculation POST /api/twin/what-if with {"results": {}} (concurrency 1, 2, 4, 8 only)

Notes
    - Latency is measured on the client machine, which is outside the UAE; it includes the internet round trip.
    - A scenario level stops early if the error rate passes 20% after at least 20 requests; this is recorded.
    - All data in the hosted demo is fictional. The relative scenario writes audit entries; reset the demo
      afterwards (POST /api/demo/reset with a counsellor demo token).

Run (from the backend directory)
    uv run --with httpx python scripts/load_test.py
    uv run --with httpx python scripts/load_test.py --duration 30 --api URL --web URL --out PATH
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

API_DEFAULT = "https://silsila-api.lemonisland-568f9acd.uaenorth.azurecontainerapps.io"
WEB_DEFAULT = "https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io"
OUT_DEFAULT = str(Path(__file__).resolve().parents[2] / "docs" / "evidence" / "load_hosted.json")
ERROR_LIMIT = 0.20
MIN_FOR_ABORT = 20


def pct(sorted_ms: list[float], q: float) -> float:
    if not sorted_ms:
        return 0.0
    return sorted_ms[min(len(sorted_ms) - 1, max(0, round(q * len(sorted_ms) + 0.5) - 1))]


async def run_level(make_ops, concurrency: int, duration: float, timeout: float = 30.0) -> dict:
    lat: list[float] = []
    statuses: Counter = Counter()
    state = {"done": 0, "err": 0, "stop": False, "aborted": False}
    limits = httpx.Limits(max_connections=concurrency + 2, max_keepalive_connections=concurrency + 2)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as client:
        async def worker(idx: int) -> None:
            ops = make_ops(idx)
            n = 0
            while not state["stop"]:
                op = ops[n % len(ops)]
                n += 1
                t0 = time.perf_counter()
                try:
                    r = await op(client)
                    code = str(r.status_code)
                    ok = 200 <= r.status_code < 300
                except Exception as e:  # noqa: BLE001
                    code, ok = type(e).__name__, False
                lat.append((time.perf_counter() - t0) * 1000)
                state["done"] += 1
                if not ok:
                    state["err"] += 1
                    statuses[code] += 1
                if state["done"] >= MIN_FOR_ABORT and state["err"] / state["done"] > ERROR_LIMIT:
                    state["aborted"] = True
                    state["stop"] = True
        start = time.perf_counter()
        tasks = [asyncio.create_task(worker(i)) for i in range(concurrency)]
        while time.perf_counter() - start < duration and not state["stop"]:
            await asyncio.sleep(0.1)
        state["stop"] = True
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start
    s = sorted(lat)
    return {
        "concurrency": concurrency, "duration_s": round(elapsed, 1), "requests": state["done"],
        "errors": state["err"], "error_rate": round(state["err"] / state["done"], 4) if state["done"] else None,
        "error_status_counts": dict(statuses), "requests_per_s": round(state["done"] / elapsed, 2) if elapsed else None,
        "latency_ms": {"median": round(statistics.median(s), 1) if s else None, "p95": round(pct(s, 0.95), 1),
                       "p99": round(pct(s, 0.99), 1), "max": round(s[-1], 1) if s else None},
        "stopped_early_error_rate_over_20pct": state["aborted"],
    }


def reading(scenarios: dict) -> list[str]:
    out = []
    for name, levels in scenarios.items():
        for lv in levels:
            c = lv["concurrency"]
            out.append(f"{name}, {c} client(s): {lv['requests']} requests, {lv['requests_per_s']}/s, median "
                       f"{lv['latency_ms']['median']} ms, p95 {lv['latency_ms']['p95']} ms, "
                       f"p99 {lv['latency_ms']['p99']} ms, {lv['errors']} errors"
                       f"{' (stopped early: error rate over 20%)' if lv['stopped_early_error_rate_over_20pct'] else ''}.")
        base = levels[0]
        worse = [lv for lv in levels[1:] if lv["errors"] or lv["latency_ms"]["median"] > 2 * base["latency_ms"]["median"]]
        if worse:
            w = worse[0]
            out.append(f"{name}: first level where errors appear or median is over twice the 1-client median: "
                       f"{w['concurrency']} clients (median {w['latency_ms']['median']} ms against "
                       f"{base['latency_ms']['median']} ms; {w['errors']} errors).")
        else:
            out.append(f"{name}: no errors, and median stayed within twice the 1-client median at every level tested.")
        best = max(levels, key=lambda lv: lv["requests_per_s"] or 0)
        out.append(f"{name}: highest throughput measured was {best['requests_per_s']}/s at {best['concurrency']} clients.")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=API_DEFAULT)
    ap.add_argument("--web", default=WEB_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--duration", type=float, default=30.0, help="seconds per scenario level")
    ap.add_argument("--pause", type=float, default=5.0, help="seconds between levels")
    a = ap.parse_args()
    api, web = a.api.rstrip("/"), a.web.rstrip("/")
    started = datetime.now(timezone.utc)

    notes = []
    async with httpx.AsyncClient(timeout=30) as c:
        h = await c.get(f"{api}/api/health")
        notes.append(f"health check: HTTP {h.status_code}")
        code = None
        try:
            r = await c.post(f"{api}/api/demo/relative")
            r.raise_for_status()
            code = r.json()["code"]
        except Exception as e:  # noqa: BLE001
            notes.append(f"relative scenario skipped: could not obtain a demo relative code ({type(e).__name__})")

    def light(_i):
        return [lambda c: c.get(f"{api}/api/guide"),
                lambda c: c.post(f"{api}/api/guide/ask", json={"text": "how is the chance calculated", "lang": "en"}),
                lambda c: c.get(f"{web}/")]

    plans = [("light_reads", "guide topics, guide ask, web home page, rotated", light, [1, 5, 10, 25])]
    if code:
        plans.append(("relative_opens_link", "GET /api/r/{code}",
                      lambda _i: [lambda c: c.get(f"{api}/api/r/{code}")], [1, 5, 10, 25]))
    plans.append(("exact_recalculation", "POST /api/twin/what-if with empty results",
                  lambda _i: [lambda c: c.post(f"{api}/api/twin/what-if", json={"results": {}})], [1, 2, 4, 8]))

    scenarios: dict = {}
    descr: dict = {}
    for name, d, mk, levels in plans:
        descr[name] = d
        scenarios[name] = []
        for n in levels:
            print(f"{name} @ {n} clients ...", flush=True)
            res = await run_level(mk, n, a.duration)
            print(f"  {res['requests']} req, {res['requests_per_s']}/s, median {res['latency_ms']['median']} ms, "
                  f"p95 {res['latency_ms']['p95']} ms, errors {res['errors']} {res['error_status_counts']}", flush=True)
            scenarios[name].append(res)
            if res["stopped_early_error_rate_over_20pct"]:
                break
            await asyncio.sleep(a.pause)

    doc = {
        "run_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "targets": {"api": api, "web": web},
        "client_location": "client outside the UAE; latency includes the internet round trip",
        "deployment": "API 2 vCPU / 4 GiB, one replica, SQLite; fictional demo data",
        "method": {"seconds_per_level": a.duration, "abort_if_error_rate_over": ERROR_LIMIT,
                   "latency_measured": "client-side, per request, in milliseconds"},
        "notes": notes,
        "scenario_descriptions": descr,
        "scenarios": scenarios,
        "reading": reading(scenarios),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
