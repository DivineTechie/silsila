"""B4 - UAE projection: cascade testing after a newborn diagnosis (synthetic kindreds).

For each sourced locus (HBB, CYP21A2, SMN1; data/params/loci.yaml) and
synthetic Emirati kindreds with the al-Gazali 1997 marriage mix, families are
ascertained through a newborn affected child. The index's parents are tested
(obligate carriers). Relatives are then invited one at a time:

  ranked    order of the Silsila engine's family_report invitation list
            (pregnancy first, then couple child risk, then carrier probability);
  unranked  random order among the same relatives;
and after every positive relative, that relative's partner is invited.

Only living adult blood relatives in the drawn tree are eligible, for both
strategies, and the same uptake draws and test results are used for both, so
the comparison differs only in order. The yield is at-risk couples (both
partners test positive; the index's parents excluded) per 1,000 tests, at a
per-family test budget K. A third comparator tests random couples from the
population; premarital screening is reported as context (it tests couples
before marriage, so it cannot reach couples who are already married).

Truth is simulated with tribe structure (theta, calibrated to Denic 2013);
the engine does not know tribes. theta = 0 (the engine's own assumption) is
also reported.
"""

from __future__ import annotations

import argparse
from typing import Any

import numpy as np

from silsila.sim import scenarios as S
from silsila.sim.sources import CITATIONS, assumption_values, calibration, denic2013, uae_consanguinity, uae_mix
from silsila.sim.stats import exact_ci

from .common import Timer, mapper, provenance, write_csv, write_json

LOCI = ["HBB", "CYP21A2", "SMN1"]
BUDGETS = [1, 2, 3, 5, 10, 15, 20, 30, 1000]
REPLICATES = {"HBB": 6, "CYP21A2": 300, "SMN1": 120}


def at_budget(hist, k, field):
    if not hist:
        return 0, 0
    j = min(k, len(hist)) - 1
    return hist[j][field], j + 1


def yields(rows, strategy, k, field, b=1000, seed=0):
    """Pooled per-1,000-test yield at budget k with a cluster bootstrap CI;
    returns (point, lo, hi, per-structure arrays for paired comparisons)."""
    num = np.array([at_budget(r[strategy], k, field)[0] for r in rows], float)
    den = np.array([at_budget(r[strategy], k, field)[1] for r in rows], float)
    w = np.array([r["weight"] for r in rows], float)
    g = np.array([r["structure"] for r in rows])
    uniq, inv = np.unique(g, return_inverse=True)
    gn = np.bincount(inv, weights=num * w, minlength=len(uniq))
    gd = np.bincount(inv, weights=den * w, minlength=len(uniq))
    return gn, gd


def summarise(rows, seed, b=1000):
    rng = np.random.default_rng(seed)
    g = np.array([r["structure"] for r in rows])
    n_struct = len(np.unique(g))
    idx = rng.integers(0, n_struct, size=(b, n_struct))
    out = {}
    for field, name in ((0, "atrisk_couples"), (1, "atrisk_couples_reproductive"), (2, "carriers")):
        out[name] = []
        for k in BUDGETS:
            rn, rd = yields(rows, "ranked", k, field)
            un, ud = yields(rows, "unranked", k, field)
            pr, pu = 1000 * rn.sum() / rd.sum(), 1000 * un.sum() / ud.sum()
            br = 1000 * rn[idx].sum(1) / rd[idx].sum(1)
            bu = 1000 * un[idx].sum(1) / ud[idx].sum(1)
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = br / bu
            ratio = ratio[np.isfinite(ratio)]
            out[name].append({
                "budget_tests_per_family": k if k < 1000 else "all",
                "mean_tests_per_family": float(rd.sum() / sum(r["weight"] for r in rows)),
                "ranked_per_1000_tests": pr, "ranked_ci95": list(np.percentile(br, [2.5, 97.5])),
                "unranked_per_1000_tests": pu, "unranked_ci95": list(np.percentile(bu, [2.5, 97.5])),
                "ranked_over_unranked": pr / pu if pu > 0 else None,
                "ratio_ci95": list(np.percentile(ratio, [2.5, 97.5])) if len(ratio) else None,
            })
    w = np.array([r["weight"] for r in rows], float)
    true_all = np.array([r["true_atrisk_all"] for r in rows], float)
    found_all = np.array([r["ranked"][-1][0] if r["ranked"] else 0 for r in rows], float)
    out["fraction_of_true_atrisk_couples_found_when_all_invited"] = float((w * found_all).sum() / (w * true_all).sum()) if true_all.sum() else None
    out["true_atrisk_couples_per_family"] = float((w * true_all).sum() / w.sum())
    out["n_families"] = len(rows)
    out["n_structures"] = n_struct
    out["drawn_tree_size"] = {"median": float(np.median([r["drawn_size"] for r in rows])),
                              "p95": float(np.percentile([r["drawn_size"] for r in rows], 95))}
    out["eligible_relatives_per_family"] = float(np.average([r["eligible"] for r in rows], weights=w))
    out["index_parents_consanguineous_pct"] = 100 * float(np.average([r["parents_kinship"] > 0 for r in rows], weights=w))
    es = np.array([r["engine_seconds"] for r in rows])
    out["engine_seconds"] = {"median": float(np.median(es)), "p95": float(np.percentile(es, 95)), "max": float(es.max())}
    out["engine_errors"] = sum(1 for r in rows if r["engine_error"])
    return out


def theta_calibration(a, quick, seed) -> dict[str, Any]:
    d = denic2013()
    grid = [0.0, 0.04, 0.08, 0.12, 0.16, 0.2, 0.25, 0.3] if quick else [0.0, 0.02, 0.04, 0.06, 0.08, 0.1, 0.12, 0.15, 0.2, 0.25, 0.3]
    r = 300_000 if quick else 1_000_000
    ys = [S.denic_check(a, th, r, seed)["both_carry"] for th in grid]
    ym = np.maximum.accumulate(ys)
    obs_k, obs_n = d["observed_atrisk_couples"], d["couples"]
    lo, hi = exact_ci(obs_k, obs_n)

    def inv(t):
        return float(np.interp(t, ym, grid)) if ym[0] <= t <= ym[-1] else None
    return {
        "source": CITATIONS["denic2013"],
        "observed": {"atrisk_couples": obs_k, "couples": obs_n, "rate": obs_k / obs_n, "exact_ci95": [lo, hi],
                     "carrier_rate_used": d["bthal_carrier_freq"]},
        "denic_expected_one_in_at_F_0.022": d["expected_couples_per_atrisk_F0022"],
        "denic_expected_one_in_at_F_0": d["expected_couples_per_atrisk_F0"],
        "model_one_in_at_theta_0": 1 / ys[0],
        "grid": [{"theta": t, "p_both_carriers": y, "one_in": 1 / y} for t, y in zip(grid, ys)],
        "theta_fit": inv(obs_k / obs_n), "theta_fit_ci95": [inv(lo), inv(hi)],
        "theta_used": a["theta_uae"],
        "simulated_couples_per_type": r,
    }


def premarital_context() -> dict[str, Any]:
    pv = calibration()["programme_volumes"]
    ad = pv["abu_dhabi_premarital"]
    fed = pv["federal_ehs_premarital"][-1]
    out = {}
    for name, k, n, url, note in (("abu_dhabi_premarital", ad["incompatible"], ad["tested_couples"], ad["url"], ad["period"]),
                                  ("federal_ehs_premarital", fed["incompatible"], fed["couples"], fed["url"], f"to {fed['to']}")):
        lo, hi = exact_ci(k, n)
        out[name] = {"incompatible_couples": k, "couples": n, "per_1000_tests": 1000 * k / (2 * n),
                     "per_1000_tests_ci95": [1000 * lo / 2, 1000 * hi / 2], "period": note, "source": url}
    out["note"] = ("Premarital panels cover ~570 genes / >840 conditions (Gulf News), so these yields are NOT comparable with the "
                   "single-gene yields above; they are shown for scale. Premarital testing is mandatory for Emiratis marrying "
                   "from 1 Jan 2025 and reaches only couples before marriage; couples already married (all couples in the "
                   "cascade simulation) are outside it. Per test, premarital screening of a random couple for one gene has the "
                   "same expected yield as the 'random couples' comparator.")
    return out


def run(quick: bool = False, seed: int = 4_000_000, overrides: dict | None = None) -> dict:
    tm = Timer()
    a = assumption_values(overrides)
    cfg, mixrec = S.calibrated_config(a, "uae")
    cal = theta_calibration(a, quick, seed + 1)
    n_struct = {"HBB": 200, "CYP21A2": 150, "SMN1": 120} if quick else {"HBB": 1000, "CYP21A2": 700, "SMN1": 600}
    settings = {"theta_calibrated": float(a["theta_uae"]), "theta_0_engine_assumption": 0.0}
    results: dict[str, Any] = {}
    chart: dict[str, Any] = {"x_label": "tests per family (budget)", "y_label": "at-risk couples identified per 1,000 tests", "series": []}
    logs = []
    for label, theta in settings.items():
        results[label] = {"theta": theta, "loci": {}}
        for li, lid in enumerate(LOCI):
            n = n_struct[lid] if label == "theta_calibrated" else n_struct[lid] // 2
            jobs = S.uae_jobs(a, cfg, lid, theta, n, seed + 100_000 * (li + 1) + (0 if label == "theta_calibrated" else 50_000),
                              REPLICATES[lid])
            rows = S.run(mapper, S.uae_worker, jobs)
            summ = summarise(rows, seed + li)
            rc = S.uae_random_couples(a, lid, theta, 200_000 if quick else 1_000_000, seed + 7 + li)
            p = rc["mixed"]["both_test_positive"]
            nn = rc["by_type"][next(iter(rc["by_type"]))]["n"]
            se = np.sqrt(p * (1 - p) / nn)
            summ["random_couples"] = {"per_1000_tests": 1000 * p / 2, "ci95": [1000 * (p - 1.96 * se) / 2, 1000 * (p + 1.96 * se) / 2],
                                      "p_both_test_positive": p, "by_type": rc["by_type"],
                                      "note": "two tests per couple; Monte Carlo interval"}
            results[label]["loci"][lid] = summ
            for r in rows:
                rr, ru = r["ranked"], r["unranked"]
                logs.append({"setting": label, "theta": theta, "locus": lid, "structure": r["structure"], "weight": r["weight"],
                             "kindred_size": r["kindred_size"], "drawn_size": r["drawn_size"], "eligible": r["eligible"],
                             "parents_kinship": r["parents_kinship"], "true_atrisk_all": r["true_atrisk_all"],
                             "true_atrisk_repro": r["true_atrisk_repro"], "tests_total": len(rr),
                             "found_all_tests": rr[-1][0] if rr else 0,
                             "ranked_found_at_5": at_budget(rr, 5, 0)[0], "unranked_found_at_5": at_budget(ru, 5, 0)[0],
                             "ranked_found_at_10": at_budget(rr, 10, 0)[0], "unranked_found_at_10": at_budget(ru, 10, 0)[0],
                             "engine_seconds": r["engine_seconds"], "engine_error": r["engine_error"] or ""})
            if label == "theta_calibrated":
                for strat in ("ranked", "unranked"):
                    chart["series"].append({
                        "locus": lid, "strategy": f"{strat} cascade",
                        "points": [{"x": e["budget_tests_per_family"], "mean_tests": e["mean_tests_per_family"],
                                    "y": e[f"{strat}_per_1000_tests"], "lo": e[f"{strat}_ci95"][0], "hi": e[f"{strat}_ci95"][1]}
                                   for e in summ["atrisk_couples"]]})
                chart["series"].append({"locus": lid, "strategy": "random couples", "points": [
                    {"x": k if k < 1000 else "all", "y": summ["random_couples"]["per_1000_tests"], "lo": summ["random_couples"]["ci95"][0],
                     "hi": summ["random_couples"]["ci95"][1]} for k in BUDGETS]})
    write_csv("b4_uae_families.csv", logs)
    chart["note"] = "SYNTHETIC kindreds; theta calibrated to Denic 2013; x='all' means every eligible relative invited."
    write_json("b4_uae_chart.json", chart)
    u = uae_consanguinity()
    out = {
        "benchmark": "B4 UAE cascade yield projection (synthetic kindreds)",
        "provenance": provenance(quick, seed),
        "inputs": {
            "loci": {"value": "HBB (B, S), CYP21A2 (c), SMN1 (del); allele frequencies, detection rates", "source": CITATIONS["loci_yaml"]},
            "background_F": {"value": 0.0222, "source": CITATIONS["algazali1997"]},
            "marriage_mix": {"overall": u["overall"], "first_cousin": u["first_cousin"], "double_first_cousin": u["double_first_cousin"],
                             "source": CITATIONS["algazali1997"]},
            "uptake_proxy": {"value": a["uae_uptake"], "source": CITATIONS["ahmed2002"] + " (591/846 tested)"},
            "assumptions_used": {k: a[k] for k in ("n_generations", "sibship_mean_uae", "marriage_prob", "p_living_grandparent_gen",
                                                   "uae_other_relatives_second_cousin_share", "uae_same_tribe_share", "theta_uae",
                                                   "uae_uptake", "uae_drawn_tree_scope", "uae_living_phenotypes_known",
                                                   "uae_detection_cyp21a2", "reproductive_generation", "ascertainment", "clan_model")},
        },
        "relationship_mix": {"target": mixrec["target"], "generator_request_mix": mixrec["request"],
                             "achieved_over_unascertained_kindreds": mixrec["achieved_in_calibration"], "target_from": uae_mix.__doc__},
        "theta_calibration_denic2013": cal,
        "results": results,
        "premarital_context": premarital_context(),
        "chart": "docs/evidence/b4_uae_chart.json",
        "log": "docs/evidence/logs/b4_uae_families.csv",
        "runtime_seconds": tm(),
    }
    write_json("b4_uae.json", out)
    return out


def headline(quick: bool, seed: int, overrides: dict, locus: str = "HBB", size_factor: float = 1.0) -> dict[str, Any]:
    """Small run for the sensitivity analysis (B5): HBB, budgets 5 and all."""
    a = assumption_values(overrides)
    cfg, mixrec = S.calibrated_config(a, "uae")
    n = max(30, int((100 if quick else 250) * size_factor))
    rows = S.run(mapper, S.uae_worker, S.uae_jobs(a, cfg, locus, float(a["theta_uae"]), n, seed, REPLICATES[locus]))
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {"n_families": len(rows), "achieved_mix": mixrec["achieved_in_calibration"]}
    idx = None
    boots = {}
    for strat in ("ranked", "unranked"):
        for k in (5, 1000):
            rn, rd = yields(rows, strat, k, 0)
            if idx is None:
                idx = rng.integers(0, len(rn), size=(1000, len(rn)))
            b = 1000 * rn[idx].sum(1) / rd[idx].sum(1)
            boots[(strat, k)] = b
            out[f"{strat}_per_1000_at_{'all' if k == 1000 else k}"] = {"estimate": 1000 * rn.sum() / rd.sum(),
                                                                         "ci95": list(np.percentile(b, [2.5, 97.5]))}
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = boots[("ranked", 5)] / boots[("unranked", 5)]
    # Bootstrap draws where the unranked strategy found nothing give an infinite
    # ratio; they are dropped (which can only lower the ratio) and counted.
    n_dropped = int((~np.isfinite(ratio)).sum())
    ratio = ratio[np.isfinite(ratio)]
    out["ranked_over_unranked_at_5"] = {"estimate": out["ranked_per_1000_at_5"]["estimate"] / out["unranked_per_1000_at_5"]["estimate"]
                                        if out["unranked_per_1000_at_5"]["estimate"] > 0 else None,
                                        "ci95": list(np.percentile(ratio, [2.5, 97.5])) if len(ratio) else None,
                                        "bootstrap_draws_dropped_infinite": n_dropped}
    rc = S.uae_random_couples(a, locus, float(a["theta_uae"]), 100_000 if quick else 300_000, seed + 1)
    out["random_couples_per_1000"] = 1000 * rc["mixed"]["both_test_positive"] / 2
    out["cascade_all_over_random"] = out["ranked_per_1000_at_all"]["estimate"] / out["random_couples_per_1000"]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    import json
    print(json.dumps(r["theta_calibration_denic2013"], indent=1, default=str)[:1500])
    for lab, res in r["results"].items():
        for lid, s in res["loci"].items():
            print(lab, lid, s["n_families"], "rand", round(s["random_couples"]["per_1000_tests"], 2),
                  [(e["budget_tests_per_family"], round(e["ranked_per_1000_tests"], 1), round(e["unranked_per_1000_tests"], 1)) for e in s["atrisk_couples"]],
                  s["engine_seconds"], s["fraction_of_true_atrisk_couples_found_when_all_invited"])
    print("runtime", r["runtime_seconds"])
