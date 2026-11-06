"""Interval estimates used by the benchmarks.

* exact_ci: Clopper-Pearson exact binomial interval (scipy) for published
  counts and for simple simulated proportions.
* cluster_bootstrap_ratio: percentile bootstrap for a ratio of weighted sums
  when simulated families from the same generated structure are correlated
  (resampling whole structures).
* study_replicates: the distribution of a pooled statistic across simulated
  replicate studies the size of the published one (e.g. 10 families); this
  is what a published value is compared with, because family-to-family
  variation makes a naive binomial interval far too narrow.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def exact_ci(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    ci = stats.binomtest(int(k), int(n)).proportion_ci(confidence_level=level, method="exact")
    return (float(ci.low), float(ci.high))


def cluster_bootstrap_ratio(
    groups: np.ndarray,
    num: np.ndarray,
    den: np.ndarray,
    weights: np.ndarray | None = None,
    b: int = 2000,
    seed: int = 0,
    scale: float = 1.0,
) -> tuple[float, float, float]:
    """Point estimate and 95% percentile interval of scale * sum(w num) / sum(w den),
    resampling clusters (groups) with replacement."""
    groups = np.asarray(groups)
    w = np.ones(len(num)) if weights is None else np.asarray(weights, float)
    num, den = np.asarray(num, float) * w, np.asarray(den, float) * w
    point = scale * num.sum() / den.sum() if den.sum() > 0 else float("nan")
    uniq, inv = np.unique(groups, return_inverse=True)
    gn = np.bincount(inv, weights=num, minlength=len(uniq))
    gd = np.bincount(inv, weights=den, minlength=len(uniq))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(uniq), size=(b, len(uniq)))
    sn, sd = gn[idx].sum(axis=1), gd[idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        boots = scale * sn / sd
    boots = boots[np.isfinite(boots)]
    lo, hi = np.percentile(boots, [2.5, 97.5]) if len(boots) else (float("nan"), float("nan"))
    return float(point), float(lo), float(hi)


def study_replicates(
    num: np.ndarray,
    den: np.ndarray,
    weights: np.ndarray,
    n_families: int,
    b: int = 4000,
    seed: int = 0,
) -> np.ndarray:
    """Pooled ratio sum(num)/sum(den) over `n_families` families drawn (with
    probability proportional to weight) from the simulated pool, b times."""
    rng = np.random.default_rng(seed)
    p = np.asarray(weights, float)
    p = p / p.sum()
    idx = rng.choice(len(num), size=(b, n_families), p=p)
    sn = np.asarray(num, float)[idx].sum(axis=1)
    sd = np.asarray(den, float)[idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return sn / sd


def compare(observed: float, replicate_values: np.ndarray) -> dict[str, float | bool]:
    """Two-sided Monte Carlo p-value of the observed value under the replicate
    distribution and whether it lies inside the central 95% interval."""
    v = replicate_values[np.isfinite(replicate_values)]
    lo, hi = np.percentile(v, [2.5, 97.5])
    p_le = float(np.mean(v <= observed + 1e-12))
    p_ge = float(np.mean(v >= observed - 1e-12))
    return {
        "predictive_95_low": float(lo),
        "predictive_95_high": float(hi),
        "p_two_sided": float(min(1.0, 2 * min(p_le, p_ge))),
        "compatible": bool(min(p_le, p_ge) > 0.025),
    }
