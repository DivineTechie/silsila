"""B3 - Reproduction of Ahmed et al., NEJM 2002 (PMID 12374877) on synthetic kindreds.

Published targets (calibration file, section 3):
  (i)   carriers among tested relatives in 10 index families: 183/591 (31%)
  (ii)  couples where both partners are carriers (identified by testing or by
        an affected child) among the 214 couples of the index families: 17/214
  (iii) carriers among tested members of 5 control families: 0/397
  (iv)  at-risk couples among 350 antenatal (random) couples: 0/350

Comparison method: the published value is compared with the distribution of
the same pooled statistic across 4,000 simulated replicate studies of the same
size (10 index families, 5 control families, 350 couples). A value is called
'compatible' when it lies inside the central 95% of that distribution
(two-sided Monte Carlo p > 0.05). The model's expected value (mean over all
simulated families) is reported with a 95% cluster-bootstrap interval, and the
published proportion with its exact (Clopper-Pearson) interval.

Biradri (clan) structure has no published F_ST, so results are reported over a
grid of theta, at theta = 0 (no clan effect), and at the theta fitted to (i)
(a calibration, stated as such), after which (ii)-(iv) are out-of-sample checks.
"""

from __future__ import annotations

import argparse
from typing import Any

import numpy as np

from silsila.sim import scenarios as S
from silsila.sim.sources import CITATIONS, ahmed, ahmed_per_family, assumption_values
from silsila.sim.stats import cluster_bootstrap_ratio, compare, exact_ci, study_replicates

from .common import Timer, mapper, provenance, write_csv, write_json


def _arr(rows, k):
    return np.array([r[k] for r in rows], float)


def model_estimate(rows, num, den, seed=0, scale=1.0):
    p, lo, hi = cluster_bootstrap_ratio(_arr(rows, "structure"), _arr(rows, num), _arr(rows, den), _arr(rows, "weight"),
                                        b=1000, seed=seed, scale=scale)
    return {"estimate": p, "ci95": [lo, hi]}


def per_family_mean(rows, k):
    w = _arr(rows, "weight")
    return float(np.sum(w * _arr(rows, k)) / w.sum())


def index_rows(a, cfg, theta, n, seed):
    return S.run(mapper, S.nejm_worker, S.nejm_jobs(a, cfg, theta, "index", n, seed))


def carrier_rate(a, cfg, theta, n, seed) -> float:
    rows = index_rows(a, cfg, theta, n, seed)
    w = _arr(rows, "weight")
    return float(np.sum(w * _arr(rows, "carriers")) / np.sum(w * _arr(rows, "tested")))


def fit_theta(a, cfg, grid, n, seed, targets: dict[str, float]) -> dict[str, Any]:
    rates = [carrier_rate(a, cfg, th, n, seed) for th in grid]
    out = {"grid": [{"theta": th, "carrier_rate": r} for th, r in zip(grid, rates)]}
    xs, ys = np.array(grid), np.array(rates)
    # enforce monotone interpolation on the running maximum (simulation noise)
    ys_m = np.maximum.accumulate(ys)
    for name, t in targets.items():
        if t < ys_m[0]:
            out[name] = {"theta": None, "note": f"below theta=0 value {ys_m[0]:.3f}"}
        elif t > ys_m[-1]:
            out[name] = {"theta": None, "note": f"above theta={xs[-1]} value {ys_m[-1]:.3f}"}
        else:
            out[name] = {"theta": float(np.interp(t, ys_m, xs))}
    return out


def evaluate(a, cfg, theta, n_index, n_control, r_couples, seed) -> dict[str, Any]:
    pub = ahmed()
    idx = index_rows(a, cfg, theta, n_index, seed)
    ctl = S.run(mapper, S.nejm_worker, S.nejm_jobs(a, cfg, theta, "control", n_control, seed + 500_000))
    ante = S.nejm_antenatal(a, theta, r_couples, seed + 900_000)
    w_i, w_c = _arr(idx, "weight"), _arr(ctl, "weight")
    n_idx_fam = len(ahmed_per_family()[0])
    n_ctl_fam = len(ahmed_per_family()[1])

    res: dict[str, Any] = {"theta": theta, "n_index_families_simulated": len(idx), "n_control_families_simulated": len(ctl)}
    # (i)
    reps = study_replicates(_arr(idx, "carriers"), _arr(idx, "tested"), w_i, n_idx_fam, seed=seed + 1)
    obs = pub["carriers_index"] / pub["tested"]["index"]
    res["i_carriers_among_tested"] = {
        "published": {"k": pub["carriers_index"], "n": pub["tested"]["index"], "value": obs,
                      "exact_ci95": exact_ci(pub["carriers_index"], pub["tested"]["index"])},
        "model": model_estimate(idx, "carriers", "tested", seed + 2),
        "replicate_study_10_families": compare(obs, reps),
        "true_carrier_rate_among_tested_model": model_estimate(idx, "carriers_true_among_tested", "tested", seed + 3),
    }
    # (ii)
    reps = study_replicates(_arr(idx, "atrisk_identified"), _arr(idx, "couples"), w_i, n_idx_fam, seed=seed + 4)
    obs = pub["atrisk_couples"] / pub["couples"]["index"]
    res["ii_atrisk_couples_identified"] = {
        "published": {"k": pub["atrisk_couples"], "n": pub["couples"]["index"], "value": obs,
                      "exact_ci95": exact_ci(pub["atrisk_couples"], pub["couples"]["index"])},
        "model": model_estimate(idx, "atrisk_identified", "couples", seed + 5),
        "replicate_study_10_families": compare(obs, reps),
        "model_true_both_carrier_couples": model_estimate(idx, "atrisk_true", "couples", seed + 6),
        "definition": "both partners living; identified = both tested positive, or the couple has an affected child",
    }
    # (iii)
    reps = study_replicates(_arr(ctl, "carriers"), _arr(ctl, "tested"), w_c, n_ctl_fam, seed=seed + 7)
    res["iii_control_family_carriers"] = {
        "published": {"k": 0, "n": pub["tested"]["control"], "value": 0.0, "exact_ci95": exact_ci(0, pub["tested"]["control"])},
        "model": model_estimate(ctl, "carriers", "tested", seed + 8),
        "replicate_study_5_families": compare(0.0, reps),
        "p_zero_carriers_in_5_family_study": float(np.mean(reps == 0)),
        "definition": "control kindreds conditioned on no affected member",
    }
    # (iv)
    p_ar = ante["mixed"]["both_carry"]
    n_ante = pub["antenatal"]["n"]
    rng = np.random.default_rng(seed + 9)
    reps = rng.binomial(n_ante, p_ar, size=4000) / n_ante
    se = np.sqrt(p_ar * (1 - p_ar) / r_couples)
    res["iv_random_couples_atrisk"] = {
        "published": {"k": pub["antenatal"]["atrisk_couples"], "n": n_ante, "value": 0.0, "exact_ci95": exact_ci(0, n_ante)},
        "model": {"estimate": p_ar, "ci95": [p_ar - 1.96 * se, p_ar + 1.96 * se], "simulated_couples_per_type": r_couples},
        "replicate_study_350_couples": compare(0.0, reps),
        "p_zero_atrisk_in_350": float((1 - p_ar) ** n_ante),
        "women_carrier_rate_model": ante["mixed"]["woman_carries"],
        "women_carriers_published": {"k": pub["antenatal"]["carriers"], "n": n_ante, "exact_ci95": exact_ci(pub["antenatal"]["carriers"], n_ante)},
        "by_couple_type": ante["by_type"],
    }
    # structure checks (reported, not fitted except living size via sibship)
    pub_idx = ahmed_per_family()[0]
    res["family_structure_check"] = {
        "living_members_per_index_family": {"model": per_family_mean(idx, "living"), "published": float(np.mean([r[0] for r in pub_idx])),
                                            "published_range": [min(r[0] for r in pub_idx), max(r[0] for r in pub_idx)],
                                            "note": "fitted through sibship_mean_nejm (calibrated assumption)"},
        "couples_per_index_family": {"model": per_family_mean(idx, "couples"), "published": pub["couples"]["index"] / n_idx_fam},
        "consanguineous_share_of_couples": {"model": model_estimate(idx, "consanguineous_couples", "couples", seed + 10)["estimate"],
                                            "published_index_families": sum(r[3] for r in pub_idx) / sum(r[2] for r in pub_idx),
                                            "note": "the generator targets 44% over all couples; ascertainment through an affected child enriches consanguineous families"},
        "unmarried_share_of_living": {"model": model_estimate(idx, "unmarried", "living", seed + 11)["estimate"], "published_all_15_families": 0.54},
        "tested_share_of_living": {"model": model_estimate(idx, "tested", "living", seed + 12)["estimate"],
                                   "published": pub["tested"]["index"] / pub["living_members"]["index"]},
    }
    res["_rows_index"] = idx
    res["_rows_control"] = ctl
    return res


def run(quick: bool = False, seed: int = 3_000_000, overrides: dict | None = None) -> dict:
    tm = Timer()
    a = assumption_values(overrides)
    cfg, mixrec = S.calibrated_config(a, "nejm")
    grid = [0.0, 0.05, 0.1, 0.2] if quick else [0.0, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2]
    n_grid = 600 if quick else 3000
    ci = exact_ci(183, 591)
    fit = fit_theta(a, cfg, grid, n_grid, seed + 10, {"fit_to_published_31pct": 183 / 591, "fit_ci_low": ci[0], "fit_ci_high": ci[1]})
    theta_star = fit["fit_to_published_31pct"].get("theta")
    n_index, n_control, r_c = (800, 300, 100_000) if quick else (4000, 1500, 400_000)
    evals = {"theta_default_no_biradri_effect": evaluate(a, cfg, float(a["theta_nejm"]), n_index, n_control, r_c, seed + 20)}
    if theta_star is not None:
        evals["theta_fitted_to_i"] = evaluate(a, cfg, theta_star, n_index, n_control, r_c, seed + 30)
    logs = []
    for label, ev in evals.items():
        for r in ev.pop("_rows_index") + ev.pop("_rows_control"):
            logs.append({"setting": label, "theta": ev["theta"], **r})
    write_csv("b3_nejm_families.csv", logs, ["setting", "theta", "mode", "structure", "weight", "living", "tested", "carriers",
                                            "carriers_true_among_tested", "couples", "consanguineous_couples", "atrisk_identified",
                                            "atrisk_true", "couples_both_tested", "unmarried", "affected_living_or_dead"])
    out = {
        "benchmark": "B3 NEJM 2002 reproduction (synthetic kindreds)",
        "provenance": provenance(quick, seed),
        "source": CITATIONS["ahmed2002"],
        "inputs": {
            "population_carrier_rate": {"value": ahmed()["population_bthal_carrier_freq"], "source": CITATIONS["ahmed2002"]},
            "couple_types": {"value": ahmed()["couple_types_all"], "source": CITATIONS["ahmed2002"]},
            "per_family_tested_fractions": {"value": "tested/members from the published per-family table", "source": CITATIONS["ahmed2002"]},
            "assumptions_used": {k: a[k] for k in ("n_generations", "sibship_mean_nejm", "marriage_prob", "p_living_grandparent_gen",
                                                   "nejm_consanguineous_split", "theta_nejm", "founder_f_nejm", "nejm_test_sensitivity",
                                                   "nejm_tested_selection", "ascertainment", "clan_model")},
        },
        "relationship_mix": {"target": mixrec["target"], "generator_request_mix": mixrec["request"],
                             "achieved_over_unascertained_kindreds": mixrec["achieved_in_calibration"]},
        "ascertainment_method": "rejection sampling: accept every (structure, genotype replicate) with >=1 affected child; exact for P(family | ascertained)",
        "theta_fit": fit,
        "evaluations": evals,
        "log": "docs/evidence/logs/b3_nejm_families.csv",
        "runtime_seconds": tm(),
    }
    write_json("b3_nejm.json", out)
    return out


def headline(quick: bool, seed: int, overrides: dict) -> dict[str, Any]:
    """Small run for the sensitivity analysis (B5)."""
    a = assumption_values(overrides)
    cfg, _ = S.calibrated_config(a, "nejm")
    n = 400 if quick else 1500
    idx = index_rows(a, cfg, float(a["theta_nejm"]), n, seed)
    grid = [0.0, 0.05, 0.1, 0.2]
    fit = fit_theta(a, cfg, grid, n // 2, seed + 1, {"t": 183 / 591})
    return {
        "carriers_among_tested": model_estimate(idx, "carriers", "tested", seed),
        "atrisk_couples_identified": model_estimate(idx, "atrisk_identified", "couples", seed),
        "living_per_family": per_family_mean(idx, "living"),
        "theta_needed_for_31pct": fit["t"].get("theta"),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    import json
    print(json.dumps({"theta_fit": r["theta_fit"], **{k: {kk: vv for kk, vv in v.items() if kk != "family_structure_check"} for k, v in r["evaluations"].items()}}, indent=1, default=str)[:6000])
