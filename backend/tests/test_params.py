"""The parameter loader must reproduce every published input exactly when the
derived allele frequencies are pushed back through the forward formulas."""

from __future__ import annotations

import pytest

from silsila import params
from silsila.engine import Pedigree, Person, Sex, marginals


def test_every_published_value_round_trips():
    reg = params.register()
    f = reg["background_inbreeding"]["value"]
    for entry in reg["loci"]:
        rec = params.load()[entry["id"]]
        loc = rec.locus
        q = {a.id: a.frequency for a in loc.alleles}
        q_ref = q[entry["reference_allele"]["id"]]
        for a in entry["alleles"]:
            qi = q[a["id"]]
            if a["published_measure"] == "heterozygote_proportion":
                assert 2 * qi * q_ref * (1 - f) == pytest.approx(a["published_value"], rel=1e-12)
            elif a["published_measure"] == "detected_heterozygote_proportion":
                assert 2 * qi * q_ref * (1 - f) * a["detection_rate"] == pytest.approx(a["published_value"], rel=1e-12)
            elif a["published_measure"] == "affected_incidence":
                assert qi * qi + f * qi * (1 - qi) == pytest.approx(a["published_value"], rel=1e-12)


def test_engine_founder_reproduces_published_rates():
    """A single founder in the engine shows the published carrier rate or incidence."""
    reg = params.register()
    for entry in reg["loci"]:
        rec = params.load()[entry["id"]]
        ped = Pedigree.from_people([Person("x", Sex.FEMALE)])
        post = marginals(ped, rec.locus, background_f=rec.background_f)["x"]
        loc = rec.locus
        for a in entry["alleles"]:
            k_het = loc.genotype_index[tuple(sorted((0, loc.allele_index[a["id"]])))]
            k_hom = loc.genotype_index[(loc.allele_index[a["id"]],) * 2]
            if a["published_measure"] == "heterozygote_proportion":
                assert post[k_het] == pytest.approx(a["published_value"], rel=1e-9)
            elif a["published_measure"] == "detected_heterozygote_proportion":
                assert post[k_het] * a["detection_rate"] == pytest.approx(a["published_value"], rel=1e-9)
            elif a["published_measure"] == "affected_incidence":
                assert post[k_hom] == pytest.approx(a["published_value"], rel=1e-9)


def test_every_parameter_has_a_source():
    reg = params.register()
    assert reg["background_inbreeding"]["source"]["pmid"]
    for entry in reg["loci"]:
        for a in entry["alleles"]:
            assert a["source"]["citation"] and a["source"]["url"].startswith("https://")
            if a.get("detection_rate") is not None:
                assert a["detection_source"]["url"].startswith("https://")
            else:
                assert a.get("detection_note"), "a missing detection rate must be explained"
        assert entry["phenotype_source"]["url"].startswith("https://")


def test_missing_detection_rate_disables_residual_risk():
    rec = params.load()["CYP21A2"]
    assert rec.residual_risk_modelled == {"c": False}
