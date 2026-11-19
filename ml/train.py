"""Train the congestion forecasting model.

    python -m ml.train --data output/events --horizon 30

Pipeline: load -> clean -> features -> chronological split ->
ColumnTransformer(OneHot + passthrough) -> HistGradientBoostingClassifier.
Compared against a persistence baseline ("congestion stays as it is now").
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.features import (
    CATEGORICAL_FEATURES, CONGESTION_LEVELS, FEATURES, NUMERIC_FEATURES, REPO_ROOT, TARGET,
    build_features, clean_events, load_events, time_split,
)

DEFAULT_MODEL_DIR = REPO_ROOT / "models"


def make_pipeline() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ("num", "passthrough", NUMERIC_FEATURES),
    ])
    clf = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
        class_weight="balanced", early_stopping=True, random_state=42,
    )
    return Pipeline([("pre", pre), ("clf", clf)])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=REPO_ROOT / "output" / "events")
    p.add_argument("--horizon", type=int, default=30, help="forecast horizon in minutes")
    p.add_argument("--test-fraction", type=float, default=0.2)
    p.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = p.parse_args()

    df = build_features(clean_events(load_events(args.data)), args.horizon)
    labelled = df.dropna(subset=[TARGET])
    train, test = time_split(labelled, args.test_fraction)
    print(f"rows: {len(labelled):,} labelled | train {len(train):,} | test {len(test):,}")

    model = make_pipeline().fit(train[FEATURES], train[TARGET])
    pred = model.predict(test[FEATURES])
    baseline = test["congestion_level"]  # persistence: future == now

    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizon_minutes": args.horizon,
        "train_rows": len(train),
        "test_rows": len(test),
        "test_period": [str(test["event_ts"].min()), str(test["event_ts"].max())],
        "model": {
            "accuracy": round(accuracy_score(test[TARGET], pred), 4),
            "macro_f1": round(f1_score(test[TARGET], pred, average="macro"), 4),
        },
        "persistence_baseline": {
            "accuracy": round(accuracy_score(test[TARGET], baseline), 4),
            "macro_f1": round(f1_score(test[TARGET], baseline, average="macro"), 4),
        },
        "per_class": classification_report(
            test[TARGET], pred, labels=CONGESTION_LEVELS, output_dict=True, zero_division=0),
        "confusion_matrix": {
            "labels": CONGESTION_LEVELS,
            "matrix": confusion_matrix(test[TARGET], pred, labels=CONGESTION_LEVELS).tolist(),
        },
    }

    print(classification_report(test[TARGET], pred, labels=CONGESTION_LEVELS, zero_division=0))
    print(f"model    : acc {metrics['model']['accuracy']:.3f}  macro-F1 {metrics['model']['macro_f1']:.3f}")
    print(f"baseline : acc {metrics['persistence_baseline']['accuracy']:.3f}  "
          f"macro-F1 {metrics['persistence_baseline']['macro_f1']:.3f}  (persistence)")

    # Refit on all labelled data for the deployable model.
    final = make_pipeline().fit(labelled[FEATURES], labelled[TARGET])
    args.model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": final, "horizon_minutes": args.horizon, "features": FEATURES},
                args.model_dir / "congestion_model.joblib")
    (args.model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"saved model + metrics to {args.model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
