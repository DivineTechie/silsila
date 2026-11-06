"""Train the character n-gram triage classifier on the DEVELOPMENT set only.

Protocol (to avoid tuning on the test set):
  1. Train on data/dev/triage_devset.jsonl (never on data/eval).
  2. Choose one probability threshold per label by 5-fold cross-validation on
     the dev set: the highest threshold that keeps cross-validated recall at or
     above a target (0.95 for crisis, 0.85 for the other escalation labels,
     0.75 otherwise), so the model leans towards over-alerting.
  3. Fit on the whole dev set, save to data/models/triage_ngram.joblib with a
     model card, then score ONCE on the held-out test set with
     `uv run python -m evals.triage_eval`.

Features: TF-IDF over character 2-5-grams within word boundaries, after the
same Arabic letter normalisation the rules use. Model: one logistic
regression per label (balanced class weights). Small, fast, inspectable.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline

from silsila.triage import LABELS, normalise

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "data/dev/triage_devset.jsonl"
MODEL = ROOT / "data/models/triage_ngram.joblib"
TARGET_RECALL = {"crisis": 0.95, "decision_request": 0.85, "religious": 0.85, "distress": 0.85}


def pipeline():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True, preprocessor=normalise),
        LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000),
    )


def main() -> None:
    rows = [json.loads(line) for line in DEV.read_text().splitlines() if line.strip()]
    texts = [r["text"] for r in rows]
    Y = {lab: np.array([lab in r["labels"] for r in rows]) for lab in LABELS}
    kf = KFold(n_splits=5, shuffle=True, random_state=0)
    thresholds, cv_report = {}, {}
    for lab in LABELS:
        y = Y[lab]
        if y.sum() < 10:
            continue
        oof = np.zeros(len(rows))
        for tr, te in kf.split(texts):
            m = pipeline().fit([texts[i] for i in tr], y[tr])
            oof[te] = m.predict_proba([texts[i] for i in te])[:, 1]
        target = TARGET_RECALL.get(lab, 0.75)
        best = 0.05
        for t in np.arange(0.95, 0.04, -0.01):
            pred = oof >= t
            recall = (pred & y).sum() / y.sum()
            if recall >= target:
                best = float(round(t, 2))
                break
        pred = oof >= best
        thresholds[lab] = best
        cv_report[lab] = {"threshold": best, "target_recall": target, "n_pos": int(y.sum()),
                          "cv_recall": float((pred & y).sum() / y.sum()),
                          "cv_specificity": float((~pred & ~y).sum() / max(1, (~y).sum()))}
    models = {lab: pipeline().fit(texts, Y[lab]) for lab in thresholds}
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"models": models, "thresholds": thresholds,
                 "card": {"trained_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                          "training_data": str(DEV.relative_to(ROOT)), "n_train": len(rows),
                          "features": "TF-IDF char_wb 2-5-grams after Arabic normalisation",
                          "model": "one-vs-rest logistic regression, balanced class weights, C=4",
                          "threshold_rule": "highest threshold meeting target recall in 5-fold CV on dev set",
                          "cv": cv_report,
                          "intended_use": "order the counsellor queue and choose an approved reply; never writes text",
                          "limitations": "trained on synthetic messages written by an AI model; not validated on real "
                                         "patient messages or by native-speaking clinicians"}}, MODEL)
    print(json.dumps(cv_report, indent=2))


if __name__ == "__main__":
    main()
