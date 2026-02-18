import re
from dataclasses import dataclass
from typing import Optional, Sequence

SKLEARN_AVAILABLE = False
try:  # Optional sklearn stack
    import numpy as np
    from scipy.sparse import csr_matrix, hstack
    from sklearn.feature_extraction.text import TfidfVectorizer

    SKLEARN_AVAILABLE = True
except Exception:
    np = None
    csr_matrix = None
    hstack = None
    TfidfVectorizer = None

MONEY_RE = re.compile(r"(?:€|\$|£)\s*\d+|\b\d+(?:[.,]\d+)?\s*(?:m|mn|mln|million|m€|bn|billion)\b", re.IGNORECASE)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b", re.IGNORECASE)
PERCENT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*%\b")

DEAL_KW_RE = re.compile(r"\b(acquis|acquire|acquisition|invest|investment|deal|rileva|entra in|enters?)\b", re.IGNORECASE)
EXIT_KW_RE = re.compile(r"\b(exit|divest|sale|sold|cessione|ced(e|e?))\b", re.IGNORECASE)
FUND_KW_RE = re.compile(r"\b(fund|fondo|fundraising|close|closing|lancia|lancio|nasce|launch)\b", re.IGNORECASE)
PEOPLE_KW_RE = re.compile(r"\b(appoint|appointed|joins?|joined|promot|nominat|nomina|team)\b", re.IGNORECASE)
JOB_KW_RE = re.compile(r"\b(job|career|careers|lavora con noi|position|opening)\b", re.IGNORECASE)

TOKEN_RE = re.compile(r"[a-z0-9à-öø-ÿ']{2,}", re.IGNORECASE)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _text_for_signal(signal: dict, raw_title: Optional[str] = None, raw_summary: Optional[str] = None) -> str:
    title = raw_title if raw_title is not None else (signal.get("title") or "")
    summary = raw_summary if raw_summary is not None else (signal.get("what_changed") or "")
    return _normalize_text(f"{title} {summary}")


def _feature_tokens(signal: dict, text: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]

    page_category = (signal.get("page_category") or "OTHER").upper()
    tokens.append(f"PAGE_{page_category}")

    signal_type = (signal.get("signal_type") or "other").upper()
    tokens.append(f"TYPE_{signal_type}")

    if MONEY_RE.search(text):
        tokens.append("__HAS_AMOUNT__")
    if DATE_RE.search(text):
        tokens.append("__HAS_DATE__")
    if PERCENT_RE.search(text):
        tokens.append("__HAS_PERCENT__")
    if DEAL_KW_RE.search(text):
        tokens.append("__HAS_DEAL_KW__")
    if EXIT_KW_RE.search(text):
        tokens.append("__HAS_EXIT_KW__")
    if FUND_KW_RE.search(text):
        tokens.append("__HAS_FUND_KW__")
    if PEOPLE_KW_RE.search(text):
        tokens.append("__HAS_PEOPLE_KW__")
    if JOB_KW_RE.search(text):
        tokens.append("__HAS_JOB_KW__")

    if signal.get("italy_relevant") is True:
        tokens.append("__ITALY_RELEVANT__")

    relevance_score = signal.get("relevance_score")
    if isinstance(relevance_score, (int, float)):
        if relevance_score >= 0.7:
            tokens.append("__REL_HIGH__")
        elif relevance_score >= 0.4:
            tokens.append("__REL_MED__")
        else:
            tokens.append("__REL_LOW__")

    return tokens


def _extra_features(signal: dict, text: str) -> list[float]:
    page_category = (signal.get("page_category") or "").upper()
    italy_relevant = 1.0 if signal.get("italy_relevant") is True else 0.0
    relevance_score = signal.get("relevance_score") or 0.0

    tokens = text.split()
    char_len = len(text)
    token_len = len(tokens)
    avg_token_len = (char_len / token_len) if token_len else 0.0

    has_amount = 1.0 if MONEY_RE.search(text) else 0.0
    has_date = 1.0 if DATE_RE.search(text) else 0.0
    has_percent = 1.0 if PERCENT_RE.search(text) else 0.0

    has_deal_kw = 1.0 if DEAL_KW_RE.search(text) else 0.0
    has_exit_kw = 1.0 if EXIT_KW_RE.search(text) else 0.0
    has_fund_kw = 1.0 if FUND_KW_RE.search(text) else 0.0
    has_people_kw = 1.0 if PEOPLE_KW_RE.search(text) else 0.0
    has_job_kw = 1.0 if JOB_KW_RE.search(text) else 0.0

    is_news = 1.0 if page_category == "NEWS" else 0.0
    is_portfolio = 1.0 if page_category == "PORTFOLIO" else 0.0
    is_team = 1.0 if page_category == "TEAM" else 0.0
    is_careers = 1.0 if page_category == "CAREERS" else 0.0
    is_other = 1.0 if page_category not in {"NEWS", "PORTFOLIO", "TEAM", "CAREERS"} else 0.0

    return [
        char_len,
        token_len,
        avg_token_len,
        has_amount,
        has_date,
        has_percent,
        has_deal_kw,
        has_exit_kw,
        has_fund_kw,
        has_people_kw,
        has_job_kw,
        is_news,
        is_portfolio,
        is_team,
        is_careers,
        is_other,
        italy_relevant,
        float(relevance_score),
    ]


EXTRA_FEATURE_NAMES = [
    "char_len",
    "token_len",
    "avg_token_len",
    "has_amount",
    "has_date",
    "has_percent",
    "has_deal_kw",
    "has_exit_kw",
    "has_fund_kw",
    "has_people_kw",
    "has_job_kw",
    "is_news",
    "is_portfolio",
    "is_team",
    "is_careers",
    "is_other",
    "italy_relevant",
    "relevance_score",
]


@dataclass
class SignalFeatureExtractor:
    def tokens_for_signal(
        self,
        signal: dict,
        raw_title: Optional[str] = None,
        raw_summary: Optional[str] = None,
    ) -> list[str]:
        text = _text_for_signal(signal, raw_title=raw_title, raw_summary=raw_summary)
        return _feature_tokens(signal, text)


class TfidfSignalFeatureExtractor:
    def __init__(self, vectorizer: Optional["TfidfVectorizer"] = None):
        if not SKLEARN_AVAILABLE:
            raise RuntimeError("scikit-learn stack not available")
        self.vectorizer = vectorizer or TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.95,
            lowercase=True,
            strip_accents="unicode",
        )

    def build_matrix(
        self,
        signals: Sequence[dict],
        fit: bool = False,
        raw_titles: Optional[Sequence[Optional[str]]] = None,
        raw_summaries: Optional[Sequence[Optional[str]]] = None,
    ):
        texts = []
        extras = []
        for idx, signal in enumerate(signals):
            raw_title = raw_titles[idx] if raw_titles is not None else None
            raw_summary = raw_summaries[idx] if raw_summaries is not None else None
            text = _text_for_signal(signal, raw_title=raw_title, raw_summary=raw_summary)
            texts.append(text)
            extras.append(_extra_features(signal, text))

        if fit:
            text_matrix = self.vectorizer.fit_transform(texts)
        else:
            text_matrix = self.vectorizer.transform(texts)

        extras_matrix = csr_matrix(np.array(extras, dtype=float))
        return hstack([text_matrix, extras_matrix])

    def feature_names(self) -> list[str]:
        text_features = list(getattr(self.vectorizer, "get_feature_names_out")())
        return text_features + EXTRA_FEATURE_NAMES
