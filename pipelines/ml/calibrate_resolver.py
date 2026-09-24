from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/backend/src"))
from cabqp.shared.normalization import normalize_text  # noqa: E402


def no_accents(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")


def variants(name: str) -> list[str]:
    words = name.split()
    variants_ = [
        name,
        no_accents(name),
        name.lower(),
        name.replace("-", " "),
        " ".join(words[-2:]) if len(words) >= 2 else name,
        words[-1],
        " ".join(words[:-1]) if len(words) > 1 else name,
        " ".join(words[:2]),
        " ".join(words[:3]),
        name[:-2] if len(name) > 5 else name,
        name.replace("tỉnh", "tinh").replace("thành phố", "tp"),
    ]
    # One deterministic character deletion approximates OCR/typing noise.
    stripped = re.sub(r"\s+", " ", name)
    if len(stripped) > 8:
        mid = len(stripped) // 2
        variants_.append(stripped[:mid] + stripped[mid + 1 :])
    return list(dict.fromkeys(x.strip() for x in variants_ if x and x.strip()))


def bm25_normalized(query: str, docs: list[str]) -> list[float]:
    q = normalize_text(query).split()
    tokenized = [normalize_text(d).split() for d in docs]
    n = len(tokenized)
    avgdl = sum(len(x) for x in tokenized) / max(n, 1)
    df = Counter()
    for tokens in tokenized:
        df.update(set(tokens))
    scores = []
    k1, b = 1.5, 0.75
    for tokens in tokenized:
        dl = max(1, len(tokens))
        counts = Counter(tokens)
        score = 0.0
        for term in q:
            tf = counts[term]
            if not tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1e-9)))
        scores.append(score)
    m = max(scores, default=0.0)
    return [x / m if m else 0.0 for x in scores]


def feature_row(query: str, names: list[str], true_index: int) -> tuple[list[float], int]:
    fuzzy_scores = [float(fuzz.WRatio(normalize_text(query), normalize_text(name))) for name in names]
    bm25_scores = bm25_normalized(query, names)
    order = sorted(
        range(len(names)),
        key=lambda i: 0.8 * fuzzy_scores[i] / 100 + 0.2 * bm25_scores[i],
        reverse=True,
    )
    top = order[0]
    second = order[1] if len(order) > 1 else top
    top_combined = 0.8 * fuzzy_scores[top] / 100 + 0.2 * bm25_scores[top]
    second_combined = 0.8 * fuzzy_scores[second] / 100 + 0.2 * bm25_scores[second]
    margin = max(0.0, top_combined - second_combined) * 100
    return [fuzzy_scores[top] / 100, margin / 100, bm25_scores[top], 0.0], int(top == true_index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(ROOT / "datasets/curated/master_units_baseline43.csv"))
    parser.add_argument("--output", default=str(ROOT / "apps/backend/artifacts/resolver_calibration.json"))
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.registry).open(encoding="utf-8-sig")))
    names = [r["canonical_name"] for r in rows]
    X, y = [], []
    for idx, name in enumerate(names):
        for query in variants(name):
            features, label = feature_row(query, names, idx)
            X.append(features)
            y.append(label)

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.30, random_state=42, stratify=y
    )
    model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_val)[:, 1]
    threshold = 0.90
    pred = (prob >= threshold).astype(int)
    payload = {
        "version": "resolver-calibration-2026.09-v1",
        "method": "logistic",
        "features": ["fuzzy", "margin", "bm25", "semantic"],
        "intercept": float(model.intercept_[0]),
        "coefficients": {
            name: float(value)
            for name, value in zip(
                ["fuzzy", "margin", "bm25", "semantic"], model.coef_[0]
            )
        },
        "decision_threshold": threshold,
        "validation": {
            "samples": len(y_val),
            "positive_rate": sum(y_val) / len(y_val),
            "brier": float(brier_score_loss(y_val, prob)),
            "roc_auc": float(roc_auc_score(y_val, prob)),
            "precision_at_threshold": float(precision_score(y_val, pred, zero_division=0)),
            "recall_at_threshold": float(recall_score(y_val, pred, zero_division=0)),
            "autoaccept_count": int(pred.sum()),
        },
        "training_note": "Calibration uses deterministic synthetic mention noise derived from the repository registry. It is safe for project/demo gating only; refit on labeled production validation data before real deployment.",
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["validation"], indent=2))
    print(out)


if __name__ == "__main__":
    main()
