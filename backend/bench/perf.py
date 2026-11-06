"""Engine latency for family trees of about 10, 30 and 60 people that contain
consanguineous loops (synthetic UAE kindreds, drawn around a random child).

Measured call: family_report (every person's carrier probability, every
couple's risk, the ranked invitation list), i.e. what the app computes after
each change to the tree. Timed single-threaded, best of 3 runs per tree.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from silsila import params
from silsila.engine import Pedigree, Person, Phenotype, family_report
from silsila.sim import scenarios as S
from silsila.sim.kindred import KindredConfig, generate_kindred, kinship_matrix
from silsila.sim.sources import assumption_values

from .common import Timer, provenance, write_csv, write_json

TARGETS = {10: (8, 12), 30: (26, 34), 60: (54, 66)}


def sample_trees(n_per_size: int, seed: int) -> dict[int, list[Pedigree]]:
    a = assumption_values()
    cfg, _ = S.calibrated_config(a, "uae")
    # small kindreds (fewer generations, smaller sibships, many cousin marriages)
    # supply the ~10-person trees with a loop
    small = KindredConfig(n_generations=4, sibship_mean=2.0, request_mix={"first_cousin": 0.6, "double_first_cousin": 0.1, "same_clan": 0.3})
    rng = np.random.default_rng(seed)
    out: dict[int, list[Pedigree]] = {s: [] for s in TARGETS}
    tries = 0
    while any(len(v) < n_per_size for v in out.values()) and tries < 20000:
        tries += 1
        k = generate_kindred(cfg if tries % 2 else small, rng)
        young = [p for p in k.pedigree.people if k.generation[p] == k.youngest]
        if not young:
            continue
        idx = young[int(rng.integers(len(young)))]
        for scope in ("parents", "grandparents", "great_grandparents"):
            if scope == "parents":
                if k.pedigree.people[idx].mother is None:
                    continue
                members = S.drawn_tree(k, idx, "grandparents")
                # parents' sibships only: drop the cousins' children generation
                members = {m for m in members if k.generation[m] < k.youngest or k.pedigree.people[m].mother == k.pedigree.people[idx].mother}
            else:
                members = S.drawn_tree(k, idx, scope)
            size = len(members)
            for s, (lo, hi) in TARGETS.items():
                if lo <= size <= hi and len(out[s]) < n_per_size:
                    src = k.pedigree.people
                    ppl = [Person(p, src[p].sex, src[p].mother, src[p].father, deceased=src[p].deceased) for p in sorted(members)]
                    ped = Pedigree.from_people(ppl)
                    _, km = kinship_matrix(ped)
                    order = ped.topological_order()
                    ix = {p: i for i, p in enumerate(order)}
                    if not any(km[ix[f], ix[m]] > 0 for f, m in ped.couples()):
                        continue  # require at least one consanguineous loop
                    ped.people[idx].phenotype = Phenotype("beta-thalassaemia major or intermedia")
                    out[s].append(ped)
    return out


def run(quick: bool = False, seed: int = 6_000_000) -> dict:
    tm = Timer()
    n = 10 if quick else 40
    trees = sample_trees(n, seed)
    rows = []
    summary = {}
    for lid in ("HBB", "SMN1"):
        rec = params.load()[lid]
        for size, peds in trees.items():
            times = []
            for i, ped in enumerate(peds):
                if lid == "SMN1":
                    for p in ped.people.values():
                        if p.phenotype is not None:
                            p.phenotype = Phenotype("spinal muscular atrophy")
                best = float("inf")
                for _ in range(3):
                    t0 = time.perf_counter()
                    family_report(ped, rec.locus, background_f=rec.background_f)
                    best = min(best, time.perf_counter() - t0)
                times.append(best)
                rows.append({"locus": lid, "size_class": size, "tree": i, "n_people": len(ped.people), "n_couples": len(ped.couples()),
                             "seconds": best})
            t = np.array(times)
            summary[f"{lid}_{size}"] = {"locus": lid, "size_class": size, "n_trees": len(t),
                                        "mean_people": float(np.mean([len(p.people) for p in peds])) if peds else None,
                                        "median_ms": 1000 * float(np.median(t)) if len(t) else None,
                                        "p95_ms": 1000 * float(np.percentile(t, 95)) if len(t) else None,
                                        "max_ms": 1000 * float(t.max()) if len(t) else None}
    write_csv("perf_engine_latency.csv", rows)
    out = {"benchmark": "Engine latency (family_report)", "provenance": provenance(quick, seed),
           "genotypes": {"HBB": 6, "SMN1": 3}, "results": summary, "log": "docs/evidence/logs/perf_engine_latency.csv",
           "note": "Single thread, best of 3 runs per tree; every tree has at least one consanguineous loop.",
           "runtime_seconds": tm()}
    write_json("perf_engine.json", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    r = run(ap.parse_args().quick)
    for k, v in r["results"].items():
        print(k, v)
