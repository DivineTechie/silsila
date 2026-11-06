"""Published inputs and labelled assumptions for the simulator.

Published numbers are read from data/calibration/12_sim_calibration.yaml (a
verbatim copy of research/12_sim_calibration.yaml) and data/params/loci.yaml.
Each value handed to a scenario carries its citation so outputs can print it.
Structural guesses are read from assumptions.yaml in this package.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..params import DATA

CALIBRATION_FILE = DATA / "calibration" / "12_sim_calibration.yaml"
ASSUMPTIONS_FILE = Path(__file__).with_name("assumptions.yaml")

CITATIONS = {
    "ahmed2002": "Ahmed S, Saleem M, Modell B, Petrou M. Screening extended families for genetic hemoglobin disorders in Pakistan. N Engl J Med 2002;347(15):1162-8. PMID 12374877, doi 10.1056/NEJMsa013234 (full text: https://discovery.ucl.ac.uk/id/eprint/7166/1/7166.pdf)",
    "algazali1997": "al-Gazali LI, Bener A, Abdulrazzaq YM, et al. J Biosoc Sci 1997;29(4):491-497. PMID 9881148",
    "denic2013": "Denic S, Aden B, Nagelkerke N, Essa AA. Beta-thalassemia in Abu Dhabi: consanguinity and tribal stratification are major factors explaining the high prevalence of the disease. Hemoglobin 2013;37:351-358. PMID 23600619 (https://pubmed.ncbi.nlm.nih.gov/23600619/)",
    "fcsc_tfr": "Emirati TFR 2016-2022, FCSC/MoHAP via GLMM: https://gulfmigration.grc.net/uae-crude-birth-rates-and-emirati-womens-total-fertility-rates-2016-2022/",
    "ad_premarital": "Abu Dhabi premarital genetic programme, Gulf News (updated 3 Oct 2026): https://gulfnews.com/uae/health/abu-dhabi-genetic-screening-flags-565-incompatible-cases-among-couples-1.500697261",
    "ehs_premarital": "Federal (EHS) premarital screening, Gulf News: https://gulfnews.com/uae/health/uae-premarital-genetic-screening-71-per-cent-of-incompatible-couples-choose-marriage-1.500731467",
    "balding_nichols1995": "Balding DJ, Nichols RA. A method for quantifying differentiation between populations at multi-allelic loci and its implications for investigating identity and paternity. Genetica 1995;96:3-12. PMID 7607457 (clan allele-frequency model; method, no numbers taken)",
    "loci_yaml": "data/params/loci.yaml (per-allele citations: Belhoul 2013 PMID 23647352; Al Hosani 2014 PMID 24932929; Rabea 2024 PMID 38879606; detection: ARUP HBB; Sugarman 2012 PMID 21811307)",
}


@lru_cache(maxsize=1)
def calibration() -> dict[str, Any]:
    return yaml.safe_load(CALIBRATION_FILE.read_text())


@lru_cache(maxsize=1)
def _assumptions_doc() -> dict[str, Any]:
    return yaml.safe_load(ASSUMPTIONS_FILE.read_text())["assumptions"]


def assumptions_doc() -> dict[str, Any]:
    return copy.deepcopy(_assumptions_doc())


def assumption_values(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    vals = {k: copy.deepcopy(v["value"]) for k, v in _assumptions_doc().items()}
    for k, v in (overrides or {}).items():
        if k not in vals:
            raise KeyError(f"Unknown assumption '{k}'")
        vals[k] = v
    return vals


# ------------------------------------------------------- published inputs --
def ahmed() -> dict[str, Any]:
    return calibration()["ahmed_nejm2002"]


def ahmed_per_family() -> tuple[list[list[int]], list[list[int]]]:
    """(index families, control families); each row is
    [members, married, couples, consang_couples, tested, carriers, carrier_couples]."""
    pf = ahmed()["per_family"]
    index = [v for k, v in pf.items() if not str(k).startswith("control")]
    control = [v for k, v in pf.items() if str(k).startswith("control")]
    return index, control


def uae_consanguinity() -> dict[str, Any]:
    return next(e for e in calibration()["consanguinity"]["uae"] if e["id"] == "alg1997")


def denic2013() -> dict[str, Any]:
    return next(e for e in calibration()["consanguinity"]["uae"] if e["id"] == "denic2013")


def nejm_mix(a: dict[str, Any]) -> dict[str, float]:
    """Couple-type mix for Ahmed 2002 families: 44% consanguineous (split by
    assumption), 50% same biradri, 6% unrelated (published)."""
    ct = ahmed()["couple_types_all"]
    split = a["nejm_consanguineous_split"]
    s = sum(split.values())
    mix = {t: ct["consanguineous_2nd_cousin_or_closer"] * v / s for t, v in split.items()}
    mix["same_clan"] = ct["same_biradri"]
    mix["other_clan"] = ct["unrelated"]
    return mix


def uae_mix(a: dict[str, Any]) -> dict[str, float]:
    """al-Gazali 1997 mix: first cousin 26.2%, double first cousin 3.5%,
    other relatives 20.8% (split by assumption), non-consanguineous 49.5%
    (same-tribe share by assumption)."""
    u = uae_consanguinity()
    other = u["overall"] - u["first_cousin"] - u["double_first_cousin"]
    s = a["uae_other_relatives_second_cousin_share"]
    non = 1 - u["overall"]
    tau = a["uae_same_tribe_share"]
    return {
        "first_cousin": u["first_cousin"],
        "double_first_cousin": u["double_first_cousin"],
        "second_cousin": other * s,
        "distant_relative": other * (1 - s),
        "same_clan": non * tau,
        "other_clan": non * (1 - tau),
    }
