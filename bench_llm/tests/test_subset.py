"""The reduced item set (AMENDMENTS A10) is fixed by the T5 sample and covers every track."""

from __future__ import annotations

import collections

from silsila_bench.items import t5_sample
from silsila_bench.runner import select_items


def test_t5_sample_subset_counts_and_balance():
    counts = {t: len(select_items(t, subset="t5-sample")) for t in ("T1", "T2", "T3", "T5")}
    assert counts == {"T1": 100, "T2": 100, "T3": 100, "T5": 50}
    by_type = collections.Counter(i.family_type for i in select_items("T3", subset="t5-sample"))
    assert sorted(by_type.values()) == [32, 34, 34]  # 16/17/17 families x 2 registers


def test_subset_uses_the_t5_question_per_family():
    sample = t5_sample()
    for t in ("T1", "T2"):
        for i in select_items(t, subset="t5-sample"):
            assert i.qid == sample[i.family_id] and i.register in ("en", "gulf")
    t5 = {(i.family_id, i.qid) for i in select_items("T5", subset="t5-sample")}
    assert t5 == set(sample.items())
