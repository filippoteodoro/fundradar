"""
Centralized date normalization for news signals.

Extracts and enhances the date parsing logic from news_extractor.py
into a standalone utility. Called by monitor.py to normalize all dates
before they enter the signal pipeline.
"""

import re
from datetime import datetime, timedelta

# Italian and English month names → zero-padded month number
MONTH_NAMES: dict[str, str] = {
    # Italian full
    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
    # English full
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    # English short
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08", "sep": "09",
    "oct": "10", "nov": "11", "dec": "12",
    # Italian short
    "gen": "01", "mag": "05", "giu": "06", "lug": "07", "ago": "08",
    "set": "09", "ott": "10", "dic": "12",
    # Note: feb, mar, apr, nov shared between Italian and English (already defined above)
}

# Month-only patterns that should return None (not enough info for a full date)
MONTH_ONLY_RE = re.compile(
    r"^(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
    r"|gen|mag|giu|lug|ago|set|ott|dic)$",
    re.IGNORECASE,
)

# "Month YYYY" or "YYYY Month" — not precise enough
MONTH_YEAR_ONLY_RE = re.compile(
    r"^(?:"
    r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
    r"|gen|mag|giu|lug|ago|set|ott|dic)"
    r"\s+\d{4}"
    r"|"
    r"\d{4}\s+"
    r"(?:gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
    r"|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
    r"|gen|mag|giu|lug|ago|set|ott|dic)"
    r")$",
    re.IGNORECASE,
)


def _parse_relative_date(text: str) -> str | None:
    """Parse relative date expressions (Italian and English) to YYYY-MM-DD."""
    text_lower = text.lower().strip()
    today = datetime.now()

    patterns: list[tuple[str, int | None]] = [
        # Italian
        (r"^oggi$", 0),
        (r"^ieri$", 1),
        (r"^l'?altro\s*ieri$|^altroieri$", 2),
        (r"^(\d+)\s*(?:giorn[oi]|gg)\s*fa$", None),
        (r"^(\d+)\s*settiman[ae]\s*fa$", None),
        (r"^(\d+)\s*mes[ei]\s*fa$", None),
        (r"^una\s*settimana\s*fa$", 7),
        (r"^un\s*mese\s*fa$", 30),
        # English
        (r"^today$", 0),
        (r"^yesterday$", 1),
        (r"^(\d+)\s*days?\s*ago$", None),
        (r"^(\d+)\s*weeks?\s*ago$", None),
        (r"^(\d+)\s*months?\s*ago$", None),
        (r"^a\s*week\s*ago$|^one\s*week\s*ago$", 7),
        (r"^a\s*month\s*ago$|^one\s*month\s*ago$", 30),
    ]

    for pattern, days_ago in patterns:
        match = re.search(pattern, text_lower)
        if match:
            if days_ago is not None:
                result_date = today - timedelta(days=days_ago)
            else:
                num = int(match.group(1))
                if "settiman" in pattern or "week" in pattern:
                    result_date = today - timedelta(weeks=num)
                elif "mes" in pattern or "month" in pattern:
                    result_date = today - timedelta(days=num * 30)
                else:
                    result_date = today - timedelta(days=num)
            return result_date.strftime("%Y-%m-%d")

    return None


def _validate_date(year: int, month: int, day: int) -> str | None:
    """Validate date components and return YYYY-MM-DD or None."""
    try:
        dt = datetime(year, month, day)
    except ValueError:
        return None

    # Reject dates before 2000 or more than 7 days in the future
    if dt.year < 2000:
        return None
    max_future = datetime.now() + timedelta(days=7)
    if dt > max_future:
        return None

    return dt.strftime("%Y-%m-%d")


def normalize_news_date(raw: str | None) -> str | None:
    """
    Normalize any date string to YYYY-MM-DD or return None.

    Handles formats found in actual fund signal data:
    - ISO: 2024-01-15
    - ISO datetime: 2024-01-15T10:30:00Z
    - DD.MM.YYYY: 13.01.2026
    - DD/MM/YYYY: 15/01/2024
    - DD Mon YYYY: 24 Dec 2025
    - Mese DD, YYYY: Ottobre 29, 2024
    - DD Mese YYYY: 15 gennaio 2024
    - Relative: oggi, yesterday, 2 giorni fa
    - Month-only → None (not precise enough)
    """
    if not raw or not isinstance(raw, str):
        return None

    text = raw.strip()
    if not text:
        return None

    # Already ISO YYYY-MM-DD — fast path
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:T|\s|$)", text)
    if iso_match:
        y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        return _validate_date(y, m, d)

    # Month-only or Month+Year-only → None
    if MONTH_ONLY_RE.match(text):
        return None
    if MONTH_YEAR_ONLY_RE.match(text):
        return None

    # Relative dates
    rel = _parse_relative_date(text)
    if rel:
        return rel

    # Replace month names with numeric values for subsequent pattern matching
    text_lower = text.lower()
    month_num = None
    for name, num in MONTH_NAMES.items():
        if name in text_lower:
            month_num = num
            # Replace the month name with its number in the working string
            text = re.sub(re.escape(name), num, text, count=1, flags=re.IGNORECASE)
            break

    # --- Numeric patterns (order matters: more specific first) ---

    # DD.MM.YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", text.strip())
    if m:
        return _validate_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # DD - MM - YYYY (progressio style with spaces around dashes)
    m = re.search(r"(\d{1,2})\s*-\s*(\d{1,2})\s*-\s*(\d{4})", text)
    if m:
        return _validate_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # After month-name substitution: "DD MM YYYY" or "DD, MM, YYYY" or "MM DD, YYYY"
    # Pattern: "Mese DD, YYYY" → after substitution → "MM DD, YYYY"
    if month_num:
        # "MM DD, YYYY" (e.g. "Ottobre 29, 2024" → "10 29, 2024")
        m = re.search(r"(\d{2})\s+(\d{1,2}),?\s+(\d{4})", text)
        if m:
            candidate_month = int(m.group(1))
            candidate_day = int(m.group(2))
            candidate_year = int(m.group(3))
            if 1 <= candidate_month <= 12:
                return _validate_date(candidate_year, candidate_month, candidate_day)

        # "DD MM YYYY" (e.g. "15 gennaio 2024" → "15 01 2024")
        m = re.search(r"(\d{1,2})\s+(\d{2})\s+(\d{4})", text)
        if m:
            candidate_day = int(m.group(1))
            candidate_month = int(m.group(2))
            candidate_year = int(m.group(3))
            if 1 <= candidate_month <= 12:
                return _validate_date(candidate_year, candidate_month, candidate_day)

        # "DD MM, YYYY" variant
        m = re.search(r"(\d{1,2})\s+(\d{2}),?\s+(\d{4})", text)
        if m:
            candidate_day = int(m.group(1))
            candidate_month = int(m.group(2))
            candidate_year = int(m.group(3))
            if 1 <= candidate_month <= 12:
                return _validate_date(candidate_year, candidate_month, candidate_day)

    # Fallback: generic "DD MM YYYY" without month substitution
    m = re.search(r"(\d{1,2})[,\s]+(\d{1,2})[,\s]+(\d{4})", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12:
            return _validate_date(y, mo, d)

    # DD/MM/YY (2-digit year)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})(?!\d)", text)
    if m:
        return _validate_date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)))

    return None
