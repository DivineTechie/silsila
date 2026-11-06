"""Load the sourced parameter register (data/params/loci.yaml) into engine loci.

Publications report carrier rates or disease incidence, while the engine needs
allele frequencies. The conversions below are standard population-genetics
identities, applied in code and recorded with their inputs so the working is
visible in the app and in docs/parameters.md:

  Heterozygote proportion h_i for pathogenic allele i (reference allele N),
  population inbreeding F:  h_i = 2 q_i q_N (1 - F).
  Summing over pathogenic alleles, H = 2 q_N (1 - q_N)(1 - F), so
      q_N = (1 + sqrt(1 - 2H / (1 - F))) / 2   and   q_i = h_i / (2 q_N (1 - F)).

  Measured heterozygote proportion with detection rate d counts only detected
  carriers, so the true proportion is h = h_measured / d.

  Incidence I of the affected genotype for a single pathogenic allele:
      I = q^2 + F q (1 - q)  ->  q = (-F + sqrt(F^2 + 4 (1 - F) I)) / (2 (1 - F)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .engine import Allele, Locus

DATA = Path(__file__).resolve().parents[3] / "data"
PARAMS_FILE = DATA / "params" / "loci.yaml"


@dataclass
class Derivation:
    allele: str
    measure: str
    published_value: float
    formula: str
    inputs: dict[str, float]
    allele_frequency: float


@dataclass
class LocusRecord:
    locus: Locus
    display: str
    display_ar: str
    content_ids: list[str]
    background_f: float
    derivations: list[Derivation]
    residual_risk_modelled: dict[str, bool]
    raw: dict[str, Any] = field(repr=False)


def _hetero_solution(h: dict[str, float], f: float) -> tuple[float, dict[str, float]]:
    total = sum(h.values())
    disc = 1 - 2 * total / (1 - f)
    if disc < 0:
        raise ValueError("Published heterozygote proportions are too high to be consistent")
    q_ref = (1 + math.sqrt(disc)) / 2
    return q_ref, {a: v / (2 * q_ref * (1 - f)) for a, v in h.items()}


def _incidence_solution(incidence: float, f: float) -> float:
    return (-f + math.sqrt(f * f + 4 * (1 - f) * incidence)) / (2 * (1 - f))


def build_locus(entry: dict[str, Any], f: float) -> LocusRecord:
    ref = entry["reference_allele"]
    het: dict[str, float] = {}
    derivations: list[Derivation] = []
    freqs: dict[str, float] = {}
    for a in entry["alleles"]:
        d = a.get("detection_rate")
        measure, value = a["published_measure"], float(a["published_value"])
        if measure == "heterozygote_proportion":
            het[a["id"]] = value
        elif measure == "detected_heterozygote_proportion":
            if d is None:
                raise ValueError(f"{a['id']}: detected proportion needs a detection rate")
            het[a["id"]] = value / d
        elif measure == "affected_incidence":
            if len(entry["alleles"]) != 1:
                raise ValueError("Incidence-based derivation supports one pathogenic allele per locus")
            q = _incidence_solution(value, f)
            freqs[a["id"]] = q
            derivations.append(Derivation(a["id"], measure, value,
                                          "q = (-F + sqrt(F^2 + 4(1-F)I)) / (2(1-F))", {"I": value, "F": f}, q))
        else:
            raise ValueError(f"Unknown published_measure '{measure}'")
    if het:
        q_ref, qs = _hetero_solution(het, f)
        freqs.update(qs)
        for a in entry["alleles"]:
            if a["id"] in qs:
                inputs = {"h": het[a["id"]], "H_total": sum(het.values()), "F": f, "q_reference": q_ref}
                formula = "q_i = h_i / (2 q_N (1-F)),  q_N = (1 + sqrt(1 - 2H/(1-F))) / 2"
                if a["published_measure"] == "detected_heterozygote_proportion":
                    inputs.update({"h_measured": float(a["published_value"]), "detection_rate": float(a["detection_rate"])})
                    formula = "h = h_measured / d;  " + formula
                derivations.append(Derivation(a["id"], a["published_measure"], float(a["published_value"]),
                                              formula, inputs, qs[a["id"]]))

    alleles = [Allele(ref["id"], ref["label"], 1 - sum(freqs.values()), False)]
    residual: dict[str, bool] = {}
    for a in entry["alleles"]:
        d = a.get("detection_rate")
        residual[a["id"]] = d is not None
        alleles.append(Allele(a["id"], a["label"], freqs[a["id"]], True, 1.0 if d is None else float(d)))

    phenotypes: dict[tuple[str, str], str] = {}
    affected: set[str] = set()
    for ph in entry["phenotypes"]:
        key = tuple(sorted(ph["genotype"]))
        phenotypes[key] = ph["label"]  # type: ignore[index]
        if ph["affected"]:
            affected.add(ph["label"])
    locus = Locus(entry["id"], entry["gene"], tuple(alleles), phenotypes, frozenset(affected))
    return LocusRecord(locus, entry["display"], entry.get("display_ar", entry["display"]), entry.get("content_ids", []),
                       f, derivations, residual, entry)


def display_for(entry_or_record: Any, lang: str) -> str:
    """Condition name in the reader's language (Arabic falls back to English)."""
    if isinstance(entry_or_record, LocusRecord):
        return entry_or_record.display_ar if lang == "ar" else entry_or_record.display
    return entry_or_record.get("display_ar", entry_or_record["display"]) if lang == "ar" else entry_or_record["display"]


@lru_cache(maxsize=1)
def load(path: Path = PARAMS_FILE) -> dict[str, LocusRecord]:
    doc = yaml.safe_load(path.read_text())
    f = float(doc["background_inbreeding"]["value"])
    return {e["id"]: build_locus(e, f) for e in doc["loci"]}


@lru_cache(maxsize=1)
def register(path: Path = PARAMS_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())
