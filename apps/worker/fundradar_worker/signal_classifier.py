import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import joblib
    JOBLIB_AVAILABLE = True
except Exception:
    joblib = None
    JOBLIB_AVAILABLE = False

from .nb_model import NaiveBayesModel
from .signal_features import SignalFeatureExtractor, SKLEARN_AVAILABLE, TfidfSignalFeatureExtractor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "data" / "models"

FUND_LABEL = "fund"
JOB_LABEL = "job"
FUND_SIGNAL_TYPES = {"fundraise_announced", "fundraise_closed", "fund_launch"}


def _load_model_dir() -> Path:
    return Path(os.environ.get("SIGNAL_MODEL_DIR", str(DEFAULT_MODEL_DIR)))


@dataclass
class SignalClassifierResult:
    keep: bool
    keep_prob: float
    keep_confidence: float
    keep_confident: bool
    type_label: str
    type_prob: float
    type_confident: bool
    confidence: float


class SignalClassifier:
    def __init__(
        self,
        extractor: SignalFeatureExtractor,
        keep_model,
        type_model,
        keep_threshold: float,
        type_threshold: float,
    ) -> None:
        self.extractor = extractor
        self.keep_model = keep_model
        self.type_model = type_model
        self.keep_threshold = keep_threshold
        self.type_threshold = type_threshold

    def predict(
        self,
        signal: dict,
        raw_title: Optional[str] = None,
        raw_summary: Optional[str] = None,
    ) -> SignalClassifierResult:
        tokens = self.extractor.tokens_for_signal(
            signal,
            raw_title=raw_title,
            raw_summary=raw_summary,
        )

        keep_probs = self.keep_model.predict_proba(tokens)
        keep_prob = float(keep_probs.get("keep", 0.0))
        keep = keep_prob >= 0.5
        keep_confidence = max(keep_prob, 1 - keep_prob)
        keep_confident = keep_confidence >= self.keep_threshold

        type_probs = self.type_model.predict_proba(tokens)
        type_label = max(type_probs, key=type_probs.get)
        type_prob = float(type_probs.get(type_label, 0.0))
        type_confident = type_prob >= self.type_threshold

        confidence = min(keep_confidence, type_prob)

        return SignalClassifierResult(
            keep=keep,
            keep_prob=keep_prob,
            keep_confidence=keep_confidence,
            keep_confident=keep_confident,
            type_label=type_label,
            type_prob=type_prob,
            type_confident=type_confident,
            confidence=confidence,
        )


class SklearnSignalClassifier:
    def __init__(
        self,
        extractor: TfidfSignalFeatureExtractor,
        keep_model,
        type_model,
        keep_threshold: float,
        type_threshold: float,
    ) -> None:
        self.extractor = extractor
        self.keep_model = keep_model
        self.type_model = type_model
        self.keep_threshold = keep_threshold
        self.type_threshold = type_threshold

    def predict(
        self,
        signal: dict,
        raw_title: Optional[str] = None,
        raw_summary: Optional[str] = None,
    ) -> SignalClassifierResult:
        matrix = self.extractor.build_matrix(
            [signal],
            fit=False,
            raw_titles=[raw_title],
            raw_summaries=[raw_summary],
        )

        keep_probs = self.keep_model.predict_proba(matrix)[0]
        keep_prob = float(keep_probs[1])
        keep = keep_prob >= 0.5
        keep_confidence = max(keep_prob, 1 - keep_prob)
        keep_confident = keep_confidence >= self.keep_threshold

        type_probs = self.type_model.predict_proba(matrix)[0]
        type_idx = int(type_probs.argmax())
        type_prob = float(type_probs[type_idx])
        type_label = str(self.type_model.classes_[type_idx])
        type_confident = type_prob >= self.type_threshold

        confidence = min(keep_confidence, type_prob)

        return SignalClassifierResult(
            keep=keep,
            keep_prob=keep_prob,
            keep_confidence=keep_confidence,
            keep_confident=keep_confident,
            type_label=type_label,
            type_prob=type_prob,
            type_confident=type_confident,
            confidence=confidence,
        )


_CLASSIFIER: Optional[SignalClassifier] = None


def get_signal_classifier() -> Optional[SignalClassifier]:
    global _CLASSIFIER
    if _CLASSIFIER is not None:
        return _CLASSIFIER

    model_dir = _load_model_dir()
    keep_path = model_dir / "signal_keep_model.pkl"
    type_path = model_dir / "signal_type_model.pkl"
    keep_sklearn_path = model_dir / "signal_keep_model.joblib"
    type_sklearn_path = model_dir / "signal_type_model.joblib"
    vectorizer_path = model_dir / "signal_vectorizer.joblib"
    meta_path = model_dir / "signal_feature_meta.json"

    keep_threshold = float(os.environ.get("SIGNAL_ML_KEEP_THRESHOLD", "0.7"))
    type_threshold = float(os.environ.get("SIGNAL_ML_TYPE_THRESHOLD", "0.65"))

    if keep_sklearn_path.exists() and type_sklearn_path.exists() and vectorizer_path.exists():
        if SKLEARN_AVAILABLE and JOBLIB_AVAILABLE:
            vectorizer = joblib.load(vectorizer_path)
            extractor = TfidfSignalFeatureExtractor(vectorizer=vectorizer)
            keep_model = joblib.load(keep_sklearn_path)
            type_model = joblib.load(type_sklearn_path)
            if meta_path.exists():
                try:
                    with meta_path.open("r") as f:
                        meta = json.load(f)
                    meta_keep = meta.get("keep_threshold")
                    meta_type = meta.get("type_threshold")
                    if isinstance(meta_keep, (int, float)):
                        keep_threshold = float(meta_keep)
                    if isinstance(meta_type, (int, float)):
                        type_threshold = float(meta_type)
                except Exception:
                    pass
            _CLASSIFIER = SklearnSignalClassifier(
                extractor=extractor,
                keep_model=keep_model,
                type_model=type_model,
                keep_threshold=keep_threshold,
                type_threshold=type_threshold,
            )
            return _CLASSIFIER

    if not (keep_path.exists() and type_path.exists()):
        return None

    extractor = SignalFeatureExtractor()
    keep_model = NaiveBayesModel.load(keep_path)
    type_model = NaiveBayesModel.load(type_path)

    if meta_path.exists():
        try:
            with meta_path.open("r") as f:
                meta = json.load(f)
            meta_keep = meta.get("keep_threshold")
            meta_type = meta.get("type_threshold")
            if isinstance(meta_keep, (int, float)):
                keep_threshold = float(meta_keep)
            if isinstance(meta_type, (int, float)):
                type_threshold = float(meta_type)
        except Exception:
            pass

    _CLASSIFIER = SignalClassifier(
        extractor=extractor,
        keep_model=keep_model,
        type_model=type_model,
        keep_threshold=keep_threshold,
        type_threshold=type_threshold,
    )
    return _CLASSIFIER


def map_type_to_signal_type(
    type_label: str,
    current_type: str,
) -> str:
    if type_label == "deal":
        return "deal_announced"
    if type_label == "exit":
        return "exit_announced"
    if type_label == "people":
        return "people_move"
    if type_label == FUND_LABEL:
        if current_type in FUND_SIGNAL_TYPES:
            return current_type
        return "fund_launch"
    if type_label == JOB_LABEL:
        return "job_posting"
    if type_label == "other":
        return "other"
    return type_label or current_type
