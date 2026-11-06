"""B5 - One-at-a-time sensitivity of B3 and B4 headlines to every assumption
in src/silsila/sim/assumptions.yaml that has a range or alternatives.

For each assumption, the low and high end of its range (or each alternative)
replaces the default while everything else stays at default. Only the
benchmark(s) listed in the assumption's `used_in` are re-run. Assumptions of
kind 'generator' or 'display' have no range and are listed as not varied.

Headlines checked:
  B3: carriers among tested relatives (published 31%), at-risk couples
      identified (published 8%), theta needed to reproduce 31%.
  B4 (HBB): at-risk couples per 1,000 tests, ranked vs unranked at 5 tests per
      family, all relatives invited, and random-couple testing.
Conclusions are judged robust when they hold at every setting.
"""

from __future__ import annotations

import argparse
from typing import Any

from silsila.sim.sources import assumption_values, assumptions_doc

from . import b3_nejm, b4_uae
from .common import Timer, provenance, write_csv, write_json


def variations() -> list[tuple[str, str, Any, list[str]]]:
    out = []
    for aid, spec in assumptions_doc().items():
        used = spec.get("used_in", [])
        if "range" in spec:
            for lab, v in zip(("low", "high"), spec["range"]):
                if v != spec["value"]:
                    out.append((aid, lab, v, used))
        for i, alt in enumerate(spec.get("alternatives", []) or []):
            if alt != spec["value"]:
                out.append((aid, f"alt{i+1}", alt, used))
    # the engine's own assumption (no tribe structure) as an extra UAE setting
    out.append(("theta_uae", "zero", 0.0, ["uae"]))
    return out


def run(quick: bool = False, seed: int = 5_000_000) -> dict:
    tm = Timer()
    base3 = b3_nejm.headline(quick, seed, {})
    base4 = b4_uae.headline(quick, seed + 1, {})
    rows, results = [], []
    for aid, lab, val, used in variations():
        ov = {aid: val}
        tv = Timer()
        r: dict[str, Any] = {"assumption": aid, "setting": lab, "value": val}
        if "nejm" in used:
            r["b3"] = b3_nejm.headline(quick, seed, ov)
        if "uae" in used:
            factor = 1.0
            if aid in ("uae_drawn_tree_scope", "n_generations"):
                factor = 0.4
                r["b4_note"] = "larger trees make the engine slower; run on 40% of the usual number of family structures"
            r["b4"] = b4_uae.headline(quick, seed + 1, ov, size_factor=factor)
        r["seconds"] = tv()
        print(f"[b5] {aid}={val}: {r['seconds']} s", flush=True)
        results.append(r)
        flat = {"assumption": aid, "setting": lab, "value": str(val)}
        if "b3" in r:
            flat.update(b3_carriers=r["b3"]["carriers_among_tested"]["estimate"], b3_carriers_ci=r["b3"]["carriers_among_tested"]["ci95"],
                        b3_atrisk=r["b3"]["atrisk_couples_identified"]["estimate"], b3_theta_needed=r["b3"]["theta_needed_for_31pct"],
                        b3_living=r["b3"]["living_per_family"])
        if "b4" in r:
            b = r["b4"]
            flat.update(b4_ranked5=b["ranked_per_1000_at_5"]["estimate"], b4_unranked5=b["unranked_per_1000_at_5"]["estimate"],
                        b4_ratio5=b["ranked_over_unranked_at_5"]["estimate"], b4_ratio5_ci=b["ranked_over_unranked_at_5"]["ci95"],
                        b4_all=b["ranked_per_1000_at_all"]["estimate"], b4_random=b["random_couples_per_1000"],
                        b4_cascade_over_random=b["cascade_all_over_random"], b4_families=b["n_families"])
        rows.append(flat)
    write_csv("b5_sensitivity.csv", rows, ["assumption", "setting", "value", "b3_carriers", "b3_carriers_ci", "b3_atrisk", "b3_theta_needed",
                                           "b3_living", "b4_ranked5", "b4_unranked5", "b4_ratio5", "b4_ratio5_ci", "b4_all", "b4_random",
                                           "b4_cascade_over_random", "b4_families"])
    b4s = [r["b4"] for r in results if "b4" in r] + [base4]
    b3s = [r["b3"] for r in results if "b3" in r] + [base3]
    ratios = [b["ranked_over_unranked_at_5"]["estimate"] for b in b4s if b["ranked_over_unranked_at_5"]["estimate"]]
    lows = [b["ranked_over_unranked_at_5"]["ci95"][0] for b in b4s if b["ranked_over_unranked_at_5"]["ci95"]]
    cvr = [b["cascade_all_over_random"] for b in b4s]
    car = [b["carriers_among_tested"]["estimate"] for b in b3s]
    thetas = [b["theta_needed_for_31pct"] for b in b3s]
    out = {
        "benchmark": "B5 sensitivity (one assumption at a time)",
        "provenance": provenance(quick, seed),
        "baseline": {"b3": base3, "b4_hbb": base4},
        "variations": results,
        "not_varied": {aid: spec["kind"] for aid, spec in assumptions_doc().items() if "range" not in spec and "alternatives" not in spec},
        "robustness": {
            "b4_ranked_over_unranked_at_5_tests_range": [min(ratios), max(ratios)],
            "b4_settings_where_ratio_ci_excludes_1": sum(1 for x in lows if x > 1), "b4_settings": len(b4s),
            "b4_cascade_all_over_random_couples_range": [min(cvr), max(cvr)],
            "b3_carriers_among_tested_range": [min(car), max(car)],
            "b3_theta_needed_for_31pct_range": [min(t for t in thetas if t is not None) if any(t is not None for t in thetas) else None,
                                                max(t for t in thetas if t is not None) if any(t is not None for t in thetas) else None],
            "b3_settings_theta_not_found_in_grid": sum(1 for t in thetas if t is None),
        },
        "log": "docs/evidence/logs/b5_sensitivity.csv",
        "runtime_seconds": tm(),
    }
    write_json("b5_sensitivity.json", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    import json
    print(json.dumps(r["robustness"], indent=1), r["runtime_seconds"])
