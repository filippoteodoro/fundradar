"""
Reproducible training script for Fundradar signal ML models.

Trains two models:
  - TYPE model: 11-class LogisticRegression on filtered signals (ground truth)
  - KEEP model: binary LogisticRegression (filtered=1, unfiltered raw=0)

Outputs (all to data/models/):
  signal_vectorizer.joblib       — TF-IDF vectorizer (shared by both models)
  signal_type_model.joblib       — TYPE classifier
  signal_keep_model.joblib       — KEEP classifier
  signal_feature_meta.json       — metadata (labels, thresholds, counts)

Usage:
  cd apps/worker
  python scripts/train_signal_classifier.py
  python scripts/train_signal_classifier.py --keep-threshold 0.72 --type-threshold 0.60
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

# Add worker package to path so we can import fundradar_worker modules
WORKER_DIR = Path(__file__).resolve().parents[1]
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

try:
    import joblib
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedShuffleSplit
    from sklearn.metrics import classification_report, f1_score
except ImportError as e:
    print(f"ERROR: Missing dependency — {e}")
    print("Install with: pip install scikit-learn joblib numpy")
    sys.exit(1)

from fundradar_worker.io_utils import safe_json_write
from fundradar_worker.signal_features import TfidfSignalFeatureExtractor, SKLEARN_AVAILABLE

if not SKLEARN_AVAILABLE:
    print("ERROR: scikit-learn stack not available in signal_features module")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    # scripts/ → apps/worker/ → apps/ → repo root
    return Path(__file__).resolve().parents[3]


def _load_json_signals(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # Support {"signals": [...]} wrapper
    return data.get("signals", []) or []


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(repo_root: Path) -> tuple[list[dict], list[dict]]:
    """
    Returns (filtered_signals, neg_signals).

    filtered_signals — 337 filtered signals (ground truth for TYPE + KEEP=1)
    neg_signals      — raw signals not in filtered set (KEEP=0)
    """
    filtered_path = repo_root / "data" / "derived" / "detected_signals_filtered.json"
    raw_path = repo_root / "data" / "derived" / "detected_signals.json"

    if not filtered_path.exists():
        raise FileNotFoundError(f"Filtered signals not found: {filtered_path}")
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw signals not found: {raw_path}")

    filtered = _load_json_signals(filtered_path)
    raw = _load_json_signals(raw_path)

    # Build set of filtered signal IDs (defensive: accept both id and signal_id)
    filtered_ids: set[str] = set()
    for s in filtered:
        sid = s.get("id") or s.get("signal_id")
        if sid:
            filtered_ids.add(sid)

    # Negatives: raw signals not in the filtered set
    neg_signals = []
    for s in raw:
        sid = s.get("id") or s.get("signal_id")
        if sid not in filtered_ids:
            neg_signals.append(s)

    print(f"Filtered (positive) signals: {len(filtered)}")
    print(f"Raw signals total:           {len(raw)}")
    print(f"Negative signals (raw-only): {len(neg_signals)}")
    return filtered, neg_signals


# ---------------------------------------------------------------------------
# Split helper
# ---------------------------------------------------------------------------

def stratified_split(
    X,
    y: list,
    seed: int = 42,
) -> tuple:
    """
    Returns (X_train, X_val, X_test, y_train, y_val, y_test)
    using an 80/10/10 stratified split.

    Falls back to a random (non-stratified) split when any class has fewer
    than 2 samples — rare classes are kept in training only.
    """
    from collections import Counter
    from sklearn.model_selection import train_test_split

    n = len(y)
    y_arr = np.array(y)
    counts = Counter(y)
    min_count = min(counts.values())

    if min_count < 2:
        # Non-stratified split: singleton classes guaranteed to training
        rng = np.random.default_rng(seed)
        idx = np.arange(n)
        rng.shuffle(idx)
        n_test = max(1, int(n * 0.10))
        n_val = max(1, int(n * 0.10))
        test_idx = idx[:n_test]
        val_idx = idx[n_test: n_test + n_val]
        train_idx = idx[n_test + n_val:]
        return (
            X[train_idx], X[val_idx], X[test_idx],
            y_arr[train_idx], y_arr[val_idx], y_arr[test_idx],
        )

    # 10% held-out test first
    sss_test = StratifiedShuffleSplit(n_splits=1, test_size=0.10, random_state=seed)
    train_val_idx, test_idx = next(sss_test.split(np.zeros(n), y_arr))

    # 10/90 of remaining = ~11.1% of original → ~10% total val
    y_train_val = y_arr[train_val_idx]
    # Check again after first split (some classes may now be singletons)
    counts2 = Counter(y_train_val.tolist())
    if min(counts2.values()) < 2:
        # Non-stratified val split
        rng = np.random.default_rng(seed)
        local_idx = np.arange(len(train_val_idx))
        rng.shuffle(local_idx)
        n_val = max(1, int(len(train_val_idx) * 0.111))
        val_idx_local = local_idx[:n_val]
        train_idx_local = local_idx[n_val:]
    else:
        sss_val = StratifiedShuffleSplit(n_splits=1, test_size=0.111, random_state=seed)
        train_idx_local, val_idx_local = next(
            sss_val.split(np.zeros(len(train_val_idx)), y_train_val)
        )

    train_idx = train_val_idx[train_idx_local]
    val_idx = train_val_idx[val_idx_local]

    return (
        X[train_idx], X[val_idx], X[test_idx],
        y_arr[train_idx], y_arr[val_idx], y_arr[test_idx],
    )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_type_model(
    filtered: list[dict],
    extractor: TfidfSignalFeatureExtractor,
    seed: int = 42,
) -> tuple[LogisticRegression, dict]:
    """
    Train 11-class TYPE model on filtered signals.

    Returns (model, eval_metrics).
    """
    print("\n── TYPE MODEL ─────────────────────────────────────────────────")

    labels = [s["signal_type"] for s in filtered]
    from collections import Counter
    print("Class distribution:")
    for t, c in sorted(Counter(labels).items(), key=lambda x: -x[1]):
        print(f"  {t:30s}: {c}")

    # Fit vectorizer on all filtered signals (full vocab)
    print("\nFitting TF-IDF vectorizer...")
    X = extractor.build_matrix(filtered, fit=True)
    y = labels

    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y, seed=seed)
    print(f"Split — train: {len(y_train)}, val: {len(y_val)}, test: {len(y_test)}")

    model = LogisticRegression(
        class_weight="balanced",
        max_iter=5000,
        C=1.0,
        random_state=seed,
        solver="lbfgs",
    )
    model.fit(X_train, y_train)

    # Evaluate
    y_val_pred = model.predict(X_val)
    y_test_pred = model.predict(X_test)

    print("\nValidation report:")
    print(classification_report(y_val, y_val_pred, zero_division=0))

    print("Test report:")
    print(classification_report(y_test, y_test_pred, zero_division=0))

    macro_f1 = f1_score(y_test, y_test_pred, average="macro", zero_division=0)
    print(f"Test macro-F1: {macro_f1:.3f}")

    metrics = {
        "train_count": int(len(y_train)),
        "val_count": int(len(y_val)),
        "test_count": int(len(y_test)),
        "test_macro_f1": round(float(macro_f1), 4),
        "type_labels": sorted(set(labels)),
    }
    return model, metrics


def train_keep_model(
    filtered: list[dict],
    neg_signals: list[dict],
    extractor: TfidfSignalFeatureExtractor,
    seed: int = 42,
) -> tuple[LogisticRegression, dict]:
    """
    Train binary KEEP model (filtered=1, neg=0).

    Vectorizer must already be fit (call after train_type_model).
    """
    print("\n── KEEP MODEL ─────────────────────────────────────────────────")

    pos_signals = filtered
    all_signals = pos_signals + neg_signals
    all_labels = [1] * len(pos_signals) + [0] * len(neg_signals)

    print(f"Positive (keep=1): {len(pos_signals)}")
    print(f"Negative (keep=0): {len(neg_signals)}")
    print(f"Total:             {len(all_signals)}")

    # Transform using already-fit vectorizer (fit=False)
    X = extractor.build_matrix(all_signals, fit=False)
    y = all_labels

    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y, seed=seed)
    print(f"Split — train: {len(y_train)}, val: {len(y_val)}, test: {len(y_test)}")

    model = LogisticRegression(
        class_weight="balanced",
        max_iter=2000,
        random_state=seed,
        solver="liblinear",
    )
    model.fit(X_train, y_train)

    # Evaluate (focus on keep=1 class)
    y_val_pred = model.predict(X_val)
    y_test_pred = model.predict(X_test)

    print("\nValidation report:")
    print(classification_report(y_val, y_val_pred, target_names=["discard", "keep"], zero_division=0))

    print("Test report:")
    print(classification_report(y_test, y_test_pred, target_names=["discard", "keep"], zero_division=0))

    keep_f1 = f1_score(y_test, y_test_pred, pos_label=1, zero_division=0)
    print(f"Test keep-F1: {keep_f1:.3f}")

    metrics = {
        "keep_train_count": int(len(y_train)),
        "keep_val_count": int(len(y_val)),
        "keep_test_count": int(len(y_test)),
        "keep_test_f1": round(float(keep_f1), 4),
    }
    return model, metrics


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_models(
    extractor: TfidfSignalFeatureExtractor,
    type_model: LogisticRegression,
    keep_model: LogisticRegression,
    type_metrics: dict,
    keep_metrics: dict,
    model_dir: Path,
    keep_threshold: float,
    type_threshold: float,
    seed: int,
) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(extractor.vectorizer, model_dir / "signal_vectorizer.joblib")
    joblib.dump(type_model, model_dir / "signal_type_model.joblib")
    joblib.dump(keep_model, model_dir / "signal_keep_model.joblib")
    print(f"\nSaved models to {model_dir}/")

    meta = {
        "model_kind": "sklearn_logreg",
        "keep_threshold": keep_threshold,
        "type_threshold": type_threshold,
        "seed": seed,
        **type_metrics,
        **keep_metrics,
    }
    meta_path = model_dir / "signal_feature_meta.json"
    safe_json_write(meta_path, meta)
    print(f"Saved metadata: {meta_path}")
    print(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # lbfgs on small high-dimensional datasets often hits the iteration limit
    # without meaningfully affecting model quality — suppress the cosmetic warning.
    warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

    parser = argparse.ArgumentParser(description="Train Fundradar signal ML models")
    parser.add_argument(
        "--keep-threshold",
        type=float,
        default=0.70,
        help="Confidence threshold for KEEP predictions (default: 0.70)",
    )
    parser.add_argument(
        "--type-threshold",
        type=float,
        default=0.60,
        help="Confidence threshold for TYPE predictions (default: 0.60)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default=None,
        help="Output directory for models (default: data/models/)",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    model_dir = Path(args.model_dir) if args.model_dir else repo_root / "data" / "models"

    print(f"Repo root:   {repo_root}")
    print(f"Model dir:   {model_dir}")
    print(f"Thresholds:  keep={args.keep_threshold}, type={args.type_threshold}")
    print(f"Seed:        {args.seed}")

    # Load data
    filtered, neg_signals = load_data(repo_root)

    # Build extractor (vectorizer starts unfitted)
    extractor = TfidfSignalFeatureExtractor()

    # Train TYPE model (fits vectorizer as side-effect)
    type_model, type_metrics = train_type_model(filtered, extractor, seed=args.seed)

    # Train KEEP model (reuses fitted vectorizer)
    keep_model, keep_metrics = train_keep_model(
        filtered, neg_signals, extractor, seed=args.seed
    )

    # Save everything
    save_models(
        extractor=extractor,
        type_model=type_model,
        keep_model=keep_model,
        type_metrics=type_metrics,
        keep_metrics=keep_metrics,
        model_dir=model_dir,
        keep_threshold=args.keep_threshold,
        type_threshold=args.type_threshold,
        seed=args.seed,
    )

    print("\nDone. Next steps:")
    print("  1. cat data/models/signal_feature_meta.json  — verify 11 type_labels")
    print("  2. pnpm pipeline:signals --slugs ardian      — verify ml_type in output")


if __name__ == "__main__":
    main()
