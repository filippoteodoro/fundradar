"""Shared signal text cleaning utilities.

Single source of truth for all text display cleaning used by both
filter_signals.py and enrich_signals_openai.py.  Every text field
(title, what_changed, enriched_summary, diff_summary) runs through
the same `clean_display_text()` pipeline, eliminating title-vs-text
sync gaps.
"""

from __future__ import annotations

import re

from signal_patterns import _strip_read_time, _strip_urls

# ---------------------------------------------------------------------------
# Constants (previously duplicated in filter + enricher)
# ---------------------------------------------------------------------------

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
    "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]

MONTHS_PATTERN = "(?:" + "|".join(MONTHS) + ")"

DATE_PREFIX_NUMERIC_RE = re.compile(
    r"^\s*\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}\s*", re.IGNORECASE,
)
DATE_PREFIX_WORD_RE = re.compile(
    r"^\s*\d{1,2}\s+" + MONTHS_PATTERN + r"\s+\d{4}\s*", re.IGNORECASE,
)
DATE_PREFIX_WORD_RE2 = re.compile(
    r"^\s*" + MONTHS_PATTERN + r"\s+\d{1,2},?\s*\d{4}\s*", re.IGNORECASE,
)

DATE_SUFFIX_NUMERIC_RE = re.compile(
    r"\s*\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}\s*$", re.IGNORECASE,
)
DATE_SUFFIX_WORD_RE = re.compile(
    r"\s*\d{1,2}\s+" + MONTHS_PATTERN + r"\s+\d{4}\s*$", re.IGNORECASE,
)
DATE_SUFFIX_WORD_RE2 = re.compile(
    r"\s*" + MONTHS_PATTERN + r"\s+\d{1,2},?\s*\d{4}\s*$", re.IGNORECASE,
)

PRESS_RELEASE_PREFIX_RE = re.compile(
    r"^(?:press\s*release|comunicato\s*stampa)\s*[-:]?\s*", re.IGNORECASE,
)

LEADING_LABEL_RE = re.compile(
    r"^\s*(?:news|update|announcement|new announcement|team update|"
    r"fundraising update|fund close|press release|comunicato stampa|"
    r"news release)\b\s*(?:[:\-–]|\s+\d|\d)\s*",
    re.IGNORECASE,
)

FRAGMENTED_PHRASES = [
    "continua a leggere",
    "read more",
    "leggi di piu",
    "leggi di più",
    "approfondisci",
]

NEWSPAPER_ONLY_RE = re.compile(
    r"^\s*(?:Il Sole 24 Ore|Corriere\s+\w+|BeBeez|Forbes|Bloomberg|Reuters|"
    r"Financial Times|Milano Finanza|MF[\s\-]Milano Finanza|La Repubblica|"
    r"Italia Oggi|MF Newswires|StartupItalia|Corriere della Sera)\s*$",
    re.IGNORECASE,
)

# Newspaper attribution suffix pattern
_NEWSPAPER_ATTR_SUFFIX_RE = re.compile(
    r"\s*[\u2013\u2014\-]+\s*(?:IL SOLE 24 ORE|CORRIERE\s+\w+|BEBEEZ|FORBES|"
    r"BLOOMBERG|REUTERS|FINANCIAL TIMES|MILANO FINANZA|MF[\s\-]MILANO FINANZA|"
    r"LA REPUBBLICA|ITALIA OGGI|MF NEWSWIRES|STARTUPITALIA)\s*$",
    re.IGNORECASE,
)

# Sector+date suffix (Astorg pattern: "Healthcare 29 October 2025")
_SECTOR_DATE_SUFFIX_RE = re.compile(
    r"(?:Healthcare|Tech(?:nology)?|Business\s+Services|Industrials|"
    r"Financial\s+Services|Consumer|TMT|Energy)\s*\d{1,2}\s+"
    + MONTHS_PATTERN + r"\s+\d{4}\s*$",
    re.IGNORECASE,
)

# Attached connectors (for _repair_attached_connectors)
_ATTACHED_CONNECTORS = (
    "dello", "della", "degli", "delle", "dall", "dell", "allo", "alla", "agli", "alle",
    "nelle", "negli", "nello", "sullo", "sulla", "sugli", "sulle",
    "with", "from", "into", "through", "between",
    "dei", "del", "con", "per", "for", "and", "the", "to", "of", "in",
    "nel", "nei", "gli", "all", "sul", "sui",
    "di", "da", "al", "ai", "il", "la", "le", "lo", "su", "un", "una", "uno",
)
_ATTACHED_CONNECTOR_RE = "|".join(sorted(set(_ATTACHED_CONNECTORS), key=len, reverse=True))
_ATTACHED_PREFIX_CONNECTOR_RE = (
    "di|da|del|della|dello|dei|degli|delle|con|for|of|in|with|to|al|alla|allo|ai|agli|alle"
)
_ATTACHED_SUFFIX_CONNECTOR_RE = (
    "per|con|di|da|del|della|dello|dei|degli|delle|for|of|in|with|to|and"
)

# Known name corrections (from CDP VC extractor spacing artifacts)
CDP_NAME_CORRECTIONS = {
    "WS ense": "WSense",
    "3 DN extech": "3DNextech",
    "T 2 Y Capital": "T2Y Capital",
    "Visio Ning": "VisiONing",
    "CAPC orp": "CAPCorp",
    "job Tech": "jobTech",
    "Serie Cdi": "Serie C di",
    "ID e A": "IDeA",
    "AI 3 D": "AI3D",
    "Icelake S Acquisition": "Icelakes Acquisition",
    "De A Capital": "DeA Capital",
    "B 4 Investimenti": "B4 Investimenti",
    "Ne Xt RE": "NeXt RE",
}

# Acronyms to restore after title() lowercases them
_TITLE_CASE_ACRONYMS = [
    "Sgr", "Spa", "Srl", "Sas", "Eur", "Ceo", "Cfo", "Coo", "Cio",
    "Ipo", "Esg", "Aifi", "Pem", "S.P.A.", "S.R.L.",
]

# Italian prepositions/articles to lowercase in title case (not at start)
_TITLE_CASE_PREPS = [
    "Di", "Da", "Del", "Dello", "Della", "Dei", "Degli", "Delle", "De",
    "Il", "Lo", "La", "Le", "Gli", "Un", "Una", "Uno",
    "Al", "Allo", "Alla", "Ai", "Agli", "Alle",
    "Nel", "Nello", "Nella", "Nei", "Negli", "Nelle",
    "Sul", "Sullo", "Sulla", "Sui", "Sugli", "Sulle",
    "Per", "Con", "Tra", "Fra", "Ed", "In",
]


# ---------------------------------------------------------------------------
# Atomic helpers
# ---------------------------------------------------------------------------

def strip_date_prefixes(text: str) -> str:
    """Remove date prefixes from text (numeric and word forms)."""
    if not text:
        return text
    cleaned = DATE_PREFIX_NUMERIC_RE.sub("", text)
    cleaned = DATE_PREFIX_WORD_RE.sub("", cleaned)
    cleaned = DATE_PREFIX_WORD_RE2.sub("", cleaned)
    return cleaned.strip()


def strip_date_suffixes(text: str) -> str:
    """Remove date suffixes from text (numeric and word forms)."""
    if not text:
        return text
    cleaned = DATE_SUFFIX_NUMERIC_RE.sub("", text)
    cleaned = DATE_SUFFIX_WORD_RE.sub("", cleaned)
    cleaned = DATE_SUFFIX_WORD_RE2.sub("", cleaned)
    return cleaned.strip()


def strip_press_release_prefix(text: str) -> str:
    """Remove 'Press Release' / 'Comunicato Stampa' prefix."""
    if not text:
        return text
    return PRESS_RELEASE_PREFIX_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# fix_spacing — canonical version (was filter's _fix_spacing)
# ---------------------------------------------------------------------------

def fix_spacing(text: str) -> str:
    """Fix missing spaces caused by HTML extraction (e.g., 'diAlba', 'eCasa').

    This is the canonical version, merging the filter's comprehensive 119-line
    implementation with the enricher's broader quote pattern.
    """
    if not text:
        return text
    cleaned = text
    # Insert space between digits and letters (e.g., "2025Comunicato")
    cleaned = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ÖØ-öø-ÿ])", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=\d)", " ", cleaned)
    # Insert space between uppercase acronym and lowercase word (e.g., "NTCsostenuta")
    cleaned = re.sub(r"(?<=[A-ZÀ-ÖØ-Þ]{2})(?=[a-zà-öø-ÿ])", " ", cleaned)
    # Insert space between lowercase word and uppercase acronym (e.g., "tedescaKBC")
    cleaned = re.sub(r"(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ]{2,})", " ", cleaned)
    # Insert space after punctuation if missing
    cleaned = re.sub(r"([,;:])(?=[A-Za-zÀ-ÖØ-öø-ÿ])", r"\1 ", cleaned)
    cleaned = re.sub(r"(?<=\d),\s+(?=\d)", ",", cleaned)
    # Insert space after common Italian prepositions/conjunctions when followed by uppercase
    cleaned = re.sub(
        r"\b(?:di|da|del|dello|della|dei|degli|delle|de|e|ed|la|il|lo|gli|le|al|allo|alla|ai|agli|alle|nel|nello|nella|nei|negli|nelle|sul|sullo|sulla|sui|sugli|sulle|per|con|su|in)(?=[A-ZÀ-ÖØ-Þ])",
        r"\g<0> ",
        cleaned,
    )
    # Insert space between long lowercase word and following CamelCase word
    cleaned = re.sub(r"(?<=[a-zà-öø-ÿ]{3})(?=[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ])", " ", cleaned)
    # Insert space before common Italian verbs/adverbs concatenated to proper nouns
    cleaned = re.sub(
        r"(?<=[a-zà-öø-ÿA-ZÀ-ÖØ-Þ]{4})(acquis\w+|annunci\w+|insieme|accompagn\w+)\b",
        r" \1",
        cleaned,
    )
    # Space before opening quotes if attached (enricher's broader pattern merged in)
    cleaned = re.sub(r'(?<=[A-Za-zÀ-ÖØ-öø-ÿ])(?=["\u201c\u201d])', " ", cleaned)
    # Restore known names/acronyms broken by digit-letter spacing
    cleaned = re.sub(r"\bF\s+2\s+i\b", "F2i", cleaned)
    cleaned = re.sub(r"\bB\s+4\s+i\b", "B4i", cleaned)
    cleaned = re.sub(r"\bCO\s+2\b", "CO2", cleaned)
    cleaned = re.sub(r"\b3\s+i\b", "3i", cleaned)
    cleaned = re.sub(r"\bK\s+3\s*R\s*X\b", "K3RX", cleaned)
    cleaned = re.sub(r"\bE\s+4\s+G\b", "E4G", cleaned)
    cleaned = re.sub(r"\bP\s+101\b", "P101", cleaned)
    cleaned = re.sub(r"\bT\s+2\s+Y\b", "T2Y", cleaned)
    cleaned = re.sub(r"\bB\s+2\s+O\b", "B2O", cleaned)
    cleaned = re.sub(r"\b3\s+D\s+AI\b", "3D AI", cleaned)
    cleaned = re.sub(r"\bSME\s+s\b", "SMEs", cleaned)
    # Quarter/half notation
    cleaned = re.sub(r"\b([QH])\s+(\d)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b(\d)\s+([QH])\s+(\d{4})\b", r"\2\1 \3", cleaned)
    # Units: "39 M W" → "39MW"
    cleaned = re.sub(r"\b(\d+)\s+M\s*W\b", r"\1MW", cleaned)
    # Brand name OCR artifacts
    cleaned = re.sub(r"\bMi\s*CROTEC\b", "MiCROTEC", cleaned)
    cleaned = re.sub(r"\bAAV\s*antgarde\b", "AAVantgarde", cleaned)
    cleaned = re.sub(r"\bLV\s*enture\b", "LVenture", cleaned)
    cleaned = re.sub(r"\bWS\s*ense\b", "WSense", cleaned)
    cleaned = re.sub(r"\bNano\s+Phoria\b", "NanoPhoria", cleaned)
    cleaned = re.sub(r"\bPintau\s+di\b", "Pintaudi", cleaned)
    cleaned = re.sub(r"\bUV\s*T[\s-]*Growth\b", "UVT-Growth", cleaned)
    cleaned = re.sub(r"\b[Bb]ee\s*2\s*[Ll]ink\b", "Bee2Link", cleaned)
    cleaned = re.sub(r"\bSmart\s*4\s*T\s*ech\b", "Smart4Tech", cleaned)
    cleaned = re.sub(r"\bID\s*e\s*A\b", "IDea", cleaned)
    cleaned = re.sub(r"\bGT\s*x\b", "GTx", cleaned)
    cleaned = re.sub(r"\bFounta\s*in\s*Vest\b", "FountainVest", cleaned)
    # Italian word splits from OCR/PDF
    cleaned = re.sub(r"\b([Tt]rasferimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ff]inanziamen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Dd]eposi)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ss]tabilimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Pp]otenziamen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ii]nvestimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Rr]iferimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\bi\s*SPLASH\b", "iSPLASH", cleaned, flags=re.IGNORECASE)
    # "Warste in" → "Warstein"
    cleaned = re.sub(r"\bWarste\s+in\b", "Warstein", cleaned)
    # "Series Cfinancing" → "Series C financing"
    cleaned = re.sub(r"\bSeries\s+([ABC])(?=[a-z])", r"Series \1 ", cleaned)
    # Media brand token split
    cleaned = re.sub(r"\bTGC\s*om\s*24\b", "TGCom24", cleaned, flags=re.IGNORECASE)
    # L Catterton scrape artifact
    cleaned = re.sub(r"\bLC\s*atterton\b", "L Catterton", cleaned)
    # "CL ub" → "Club"
    cleaned = re.sub(r"\bCL\s+ub\b", "Club", cleaned)
    # "T erm" → "Term"
    cleaned = re.sub(r"T\s+erm\b", "Term", cleaned)
    # "M arch" → "March"
    cleaned = re.sub(r"\bM\s+arch\b", "March", cleaned)
    # Ordinal splits: "14 th" → "14th"
    cleaned = re.sub(r"\b(\d+)\s+(th|st|nd|rd)\b", r"\1\2", cleaned, flags=re.IGNORECASE)
    # "Cdp Venture Capital" → "CDP Venture Capital"
    cleaned = re.sub(r"\bCdp\s+Venture\s+Capital\b", "CDP Venture Capital", cleaned)
    # "2025–2028Term" → "2025–2028 Term"
    cleaned = re.sub(r"(\d{4})Term\b", r"\1 Term", cleaned)
    # "Serie A/B/C" → "Series A/B/C"
    cleaned = re.sub(r"\b[Ss][Ee][Rr][Ii][Ee]\s+([A-Ga-g])\b", lambda m: f"Series {m.group(1).upper()}", cleaned)
    # Mojibake: â¬€ / â¬ → €
    cleaned = cleaned.replace("â¬€", "€").replace("â¬", "€")
    # Finance jargon: "aucap" → "capital increase"
    cleaned = re.sub(r"\baucap\b", "capital increase", cleaned, flags=re.IGNORECASE)
    # Italian legal abbreviations
    cleaned = re.sub(r"\b[Ss]gr\b", "SGR", cleaned)
    cleaned = re.sub(r"\b[Ss]icaf\b", "SICAF", cleaned)
    # Fund abbreviations that LLM title-cases
    cleaned = re.sub(r"\bDif\b", "DIF", cleaned)
    cleaned = re.sub(r"\bDws\b", "DWS", cleaned)
    # Italian thousands in non-monetary context
    cleaned = re.sub(r"\b(\d{1,3})\.(\d{3})\s+mq\b", lambda m: f"{m.group(1)},{m.group(2)} sqm", cleaned)
    cleaned = re.sub(r"\b(\d{1,3})\.(\d{3})(?=\s+(?:beds?|employees?|people|square|units?|staff|workers?))", lambda m: f"{m.group(1)},{m.group(2)}", cleaned)
    # "2 T au" → "Tau"
    cleaned = re.sub(r"\b2\s+T\s+au\b", "Tau", cleaned)
    # Strip leading numbered list artifacts
    cleaned = re.sub(r"^\d+\s+(?=[A-Z])", "", cleaned)
    # Italian ordinals in text
    cleaned = re.sub(r"\b(\d+)\s+([ao])\s+", r"\1\2 ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # Re-compact currency amount suffixes split by digit-letter spacing
    cleaned = re.sub(r'([€$£]\d+(?:[.,]\d+)?)\s+([KMBT])\b', r'\1\2', cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# repair_token_splits — merges filter's _repair_common_splits + enricher's
#                        _normalize_token_splits + additional patterns
# ---------------------------------------------------------------------------

def repair_token_splits(text: str, strip_leading_label: bool = True) -> str:
    """Repair fragmented tokens from OCR/PDF/HTML extraction artifacts.

    Merges filter's _repair_common_splits() and enricher's _normalize_token_splits().
    """
    if not text:
        return text
    cleaned = text

    # Strip fragmented read-more phrases
    for phrase in FRAGMENTED_PHRASES:
        pattern = r"".join(re.escape(ch) + r"\s*" for ch in phrase)
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Strip leading label if requested
    if strip_leading_label:
        cleaned = LEADING_LABEL_RE.sub("", cleaned)

    # Repair split Italian prepositions/articles
    cleaned = re.sub(r"\bde\s+l\b", "del", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdi\s+l\b", "del", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bi\s+l\b", "il", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bsu\s+l\b", "sul", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+la\b", "della", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+le\b", "delle", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+lo\b", "dello", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+i\b", "dei", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdel\s+gli\b", "degli", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+la\b", "alla", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+lo\b", "allo", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+le\b", "alle", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bal\s+gli\b", "agli", cleaned, flags=re.IGNORECASE)

    # Merge single-letter uppercase fragments
    cleaned = re.sub(
        r"\b([A-Za-zÀ-ÖØ-öø-ÿ]{2,})\s([ECIPSV])\s+([a-zà-öø-ÿ]{2,})",
        r"\1 \2\3",
        cleaned,
    )

    # Fix common investment splits (I nvestimento -> Investimento)
    cleaned = re.sub(
        r"\b([Ii])\s+nvest",
        lambda m: ("I" if m.group(1).isupper() else "i") + "nvest",
        cleaned,
    )

    # Company/place name splits from enricher's _normalize_token_splits
    cleaned = re.sub(r"\bAcceler\s+ORA\b", "AccelerORA", cleaned)
    # Power unit splits: "39M W" → "39MW"
    cleaned = re.sub(r"\b(\d[\d.,]*)M\s+W\b", r"\1MW", cleaned)
    # "ID ea" → "Idea"
    cleaned = re.sub(r"\bID\s+ea\b", "Idea", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# normalize_monetary_values — canonical from filter, merged with enricher's
#                              "oltre"→"over" and "circa"→"~"
# ---------------------------------------------------------------------------

def _format_amount(number_str: str, multiplier: str, currency: str = "€") -> str | None:
    """Format a number with multiplier suffix."""
    num = number_str.strip().rstrip(".")
    if "," in num and "." not in num:
        parts = num.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            num = num.replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "." in num and "," not in num:
        parts = num.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            num = num.replace(".", "")
    elif "," in num and "." in num:
        if num.index(",") < num.index("."):
            num = num.replace(",", "")
        else:
            num = num.replace(".", "").replace(",", ".")
    try:
        val = float(num)
    except ValueError:
        return None
    if val == int(val):
        formatted = str(int(val))
    else:
        formatted = f"{val:.1f}"
    return f"{currency}{formatted}{multiplier}"


def normalize_monetary_values(text: str) -> str:
    """Normalize monetary values to consistent €X.XM / €X.XB format.

    Handles Italian (milioni, miliardi, mln) and English (million, billion, bn).
    Preserves USD/GBP prefix when present. Defaults to EUR (€) for unspecified.
    Also normalizes Italian "oltre"→"over" and "circa"→"~" (from enricher).
    """
    if not text:
        return text

    result = text

    # Italian quantity words (from enricher)
    result = re.sub(r"\boltre\b", "over", result, flags=re.IGNORECASE)
    result = re.sub(r"\bcirca\b", "~", result, flags=re.IGNORECASE)

    # "X million(i/e) (di) euro/EUR" → €XM
    result = re.sub(
        r'(?:€\s*)?(\d+(?:[.,]\d+)?)\s*(?:milion[ie]?\s+(?:di\s+)?(?:euro|eur)|million\s+(?:euro|eur)|mln\s+(?:di\s+)?(?:euro|eur))\b',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "X miliard(i/o) (di) euro/EUR" → €XB
    result = re.sub(
        r'(?:€\s*)?(\d+(?:[.,]\d+)?)\s*(?:miliard[io]?\s+(?:di\s+)?(?:euro|eur)|billion\s+(?:euro|eur)|bn\s+(?:di\s+)?(?:euro|eur))\b',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "EUR/E X million/mln/m" → €XM
    result = re.sub(
        r'\b(?:EUR|E)\s+(\d+(?:[.,]\d+)?)\s*(?:million|mln|m)\b',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "EUR/E X billion/bn/b" → €XB
    result = re.sub(
        r'\b(?:EUR|E)\s+(\d+(?:[.,]\d+)?)\s*(?:billion|bn|b)\b',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "€X million/mln" → €XM
    result = re.sub(
        r'€\s*(\d+(?:[.,]\d+)?)\s*(?:million|milion[ie]?|mln)\b',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "€X billion/miliard*" → €XB
    result = re.sub(
        r'€\s*(\d+(?:[.,]\d+)?)\s*(?:billion|miliard[io]?|bn)\b',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "$X million/mln/m" → $XM
    result = re.sub(
        r'\$\s*(\d+(?:[.,]\d+)?)\s*(?:million|mln|m)\b',
        lambda m: _format_amount(m.group(1), "M", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "$X billion/bn/b" → $XB
    result = re.sub(
        r'\$\s*(\d+(?:[.,]\d+)?)\s*(?:billion|bn|b)\b',
        lambda m: _format_amount(m.group(1), "B", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "£X million" → £XM
    result = re.sub(
        r'£\s*(\d+(?:[.,]\d+)?)\s*(?:million|mln|m)\b',
        lambda m: _format_amount(m.group(1), "M", "£") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # standalone "X milioni" / "X miliardi" (optional currency symbol)
    result = re.sub(
        r'(?:(€|\$|£)\s*)?(\d+(?:[.,]\d+)?)\s+milion[ie]\b',
        lambda m: _format_amount(m.group(2), "M", m.group(1) or "€") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'(?:(€|\$|£)\s*)?(\d+(?:[.,]\d+)?)\s+miliard[io]\b',
        lambda m: _format_amount(m.group(2), "B", m.group(1) or "€") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "X million/billion euros/euro/eur" → €XM/€XB
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+million\s+euro[s]?\b',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+(?:billion|bn)\s+euro[s]?\b',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "euro X million/billion" → €XM/€XB
    result = re.sub(
        r'\beuro\s+(\d+(?:[.,]\d+)?)\s+(?:million|mln)\b',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\beuro\s+(\d+(?:[.,]\d+)?)\s+(?:billion|bn)\b',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "USD X million/billion" → $XM/$XB
    result = re.sub(
        r'\bUSD\s+(\d+(?:[.,]\d+)?)\s+(?:million|mln)\b',
        lambda m: _format_amount(m.group(1), "M", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\bUSD\s+(\d+(?:[.,]\d+)?)\s+(?:billion|bn)\b',
        lambda m: _format_amount(m.group(1), "B", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "€1,65 M", "$2.0 B", "£570 K euro" → normalized
    result = re.sub(
        r'([€$£])\s*(\d+(?:[.,]\d+)?)\s*([KMBT])\s*(?:euro|eur)?\b',
        lambda m: _format_amount(m.group(2), m.group(3).upper(), m.group(1)) or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "1,65 M euro" / "570 K EUR" (no symbol) → normalized
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s*([KMBT])\s*(?:euro|eur)\b',
        lambda m: _format_amount(m.group(1), m.group(2).upper()) or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "X M€" → "€XM"
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s*M€',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "X M$" → "$XM"
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s*M\$',
        lambda m: _format_amount(m.group(1), "M", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # Descriptive "tens/hundreds of mln/mld"
    result = re.sub(r'\b(tens?|hundreds?|dozens?)\s+of\s+mln\b', r'\1 of millions', result, flags=re.IGNORECASE)
    result = re.sub(r'\b(tens?|hundreds?|dozens?)\s+of\s+mld\b', r'\1 of billions', result, flags=re.IGNORECASE)
    # Standalone "X mln" / "X mld" → €XM / €XB (default EUR in Italian PE/VC context)
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+mln\b(?!\s+(?:di\s+)?(?:euro|eur|dollar|sterlina|\$|£))',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+mld\b(?!\s+(?:di\s+)?(?:euro|eur|dollar|sterlina|\$|£))',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    # "€X million" / "$X million" (enricher patterns)
    result = re.sub(r"€(\d[\d.,]*)\s+million\b", lambda m: f"€{m.group(1)}M", result, flags=re.IGNORECASE)
    result = re.sub(r"\$(\d[\d.,]*)\s+million\b", lambda m: f"${m.group(1)}M", result, flags=re.IGNORECASE)
    result = re.sub(r"€(\d[\d.,]*)\s+billion\b", lambda m: f"€{m.group(1)}B", result, flags=re.IGNORECASE)
    result = re.sub(r"\$(\d[\d.,]*)\s+billion\b", lambda m: f"${m.group(1)}B", result, flags=re.IGNORECASE)

    # Safety: ensure separator between compact amount and following letters
    result = re.sub(
        r'([€$£]\d+(?:[.,]\d+)?)\s*([KMBT])(?=[A-Za-zÀ-ÖØ-öø-ÿ])',
        r'\1\2 ',
        result,
    )
    result = re.sub(
        r'(\b\d+(?:[.,]\d+)?)\s*([KMBT])(?=[A-Za-zÀ-ÖØ-öø-ÿ])',
        r'\1\2 ',
        result,
    )
    result = re.sub(
        r'([€$£]\d+(?:[.,]\d+)?[KMBT])(?=[A-Za-zÀ-ÖØ-öø-ÿ])',
        r'\1 ',
        result,
    )
    result = re.sub(
        r'(\b\d+(?:[.,]\d+)?[KMBT])(?=[A-Za-zÀ-ÖØ-öø-ÿ])',
        r'\1 ',
        result,
    )

    # "€XM di dollari" → "$XM" (EUR/USD confusion from translation)
    result = re.sub(
        r'€(\d+(?:[.,]\d+)?[MBK])\s+(?:di\s+)?dollar[is]?\b',
        lambda m: f"${m.group(1)}",
        result, flags=re.IGNORECASE,
    )
    # "X M €" → "€XM"
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s*M\s*€',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result,
    )
    # "X mila euro" → "€0.XXM"
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+mila\s+euro\b',
        lambda m: _format_amount(str(float(m.group(1).replace(",", ".")) / 1000), "M") if m.group(1).replace(",", ".").replace(".", "", 1).isdigit() else m.group(0),
        result, flags=re.IGNORECASE,
    )
    # Italian full number "1.350.000 euro" → "€1.35M"
    result = re.sub(
        r'\b(\d{1,3}(?:\.\d{3})+)\s+euro\b',
        lambda m: _format_amount(str(int(m.group(1).replace(".", "")) / 1_000_000), "M") if int(m.group(1).replace(".", "")) >= 100_000 else _format_amount(str(int(m.group(1).replace(".", "")) / 1_000), "K"),
        result, flags=re.IGNORECASE,
    )

    # Fix lost Italian thousands separator: €4985M → €4.985M
    def _fix_lost_thousands(m):
        currency = m.group(1) or "€"
        digits = m.group(2)
        return f"{currency}{digits[0]}.{digits[1:]}M"
    result = re.sub(r'([€$£])(\d{4})\s*M\b', _fix_lost_thousands, result)
    result = re.sub(r'\b(\d{4})\s*M\s*(?:€|euro)\b',
        lambda m: f"€{m.group(1)[0]}.{m.group(1)[1:]}M",
        result, flags=re.IGNORECASE)

    # Clean up spacing: "€ 500M" → "€500M"
    result = re.sub(r"€\s+(\d)", r"€\1", result)

    result = repair_attached_connectors(result)
    return re.sub(r"\s{2,}", " ", result).strip()


# ---------------------------------------------------------------------------
# repair_attached_connectors
# ---------------------------------------------------------------------------

def _iter_company_compacts(company_candidates: list[str] | None) -> list[str]:
    """Return unique compact company identifiers suitable for glue-token repairs."""
    if not company_candidates:
        return []
    compacts: list[str] = []
    seen: set[str] = set()
    for raw in company_candidates:
        compact = re.sub(r"[^A-Za-z0-9À-ÖØ-öø-ÿ]+", "", str(raw or ""))
        if len(compact) < 5:
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        compacts.append(compact)
    return compacts


def repair_attached_connectors(text: str, company_candidates: list[str] | None = None) -> str:
    """Repair words glued to prepositions/articles around company names and deal nouns."""
    if not text:
        return text
    cleaned = text

    # Prefix connector stuck to a capitalized token: "diMarullo" → "di Marullo"
    cleaned = re.sub(
        rf"\b({_ATTACHED_CONNECTOR_RE})(?=[A-ZÀ-ÖØ-Þ])",
        r"\1 ",
        cleaned,
    )

    # Context-aware fallback for unknown company names
    cleaned = re.sub(
        rf"\b({_ATTACHED_PREFIX_CONNECTOR_RE})\s+([A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]{{4,}})({_ATTACHED_SUFFIX_CONNECTOR_RE})\b",
        r"\1 \2 \3",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Entity-aware repairs around known company names
    for raw_company in company_candidates or []:
        value = str(raw_company or "").strip()
        if not value or " " in value:
            continue
        spaced_value = re.sub(r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])", " ", value)
        if spaced_value != value:
            cleaned = re.sub(
                rf"\b{re.escape(spaced_value)}\b",
                value,
                cleaned,
            )

    for compact in _iter_company_compacts(company_candidates):
        spaced_compact_pattern = re.sub(
            r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])",
            r"\\s*",
            re.escape(compact),
        )
        cleaned = re.sub(
            rf"(?i)\b({_ATTACHED_CONNECTOR_RE})({spaced_compact_pattern})(?=\b|[A-Za-zÀ-ÖØ-öø-ÿ])",
            lambda m, c=compact: f"{m.group(1)} {c}",
            cleaned,
        )
        cleaned = re.sub(
            rf"(?i)\b({spaced_compact_pattern})({_ATTACHED_CONNECTOR_RE})(?=\b|[A-Za-zÀ-ÖØ-öø-ÿ])",
            lambda m, c=compact: f"{c} {m.group(2)}",
            cleaned,
        )

    # English/Italian deal nouns glued to connectors
    cleaned = re.sub(
        r"\b([A-Za-z]{5,}(?:ment|tion|sion|ship|ness))(for|with|of|in|to|per|con|di)\b",
        r"\1 \2",
        cleaned,
        flags=re.IGNORECASE,
    )

    return re.sub(r"\s{2,}", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# caps_to_title_case — unified ALL CAPS → title case
# ---------------------------------------------------------------------------

def caps_to_title_case(text: str) -> str:
    """Convert ALL CAPS text to title case, preserving acronyms and lowercasing prepositions."""
    if not text:
        return text
    if len(text) <= 20:
        return text
    if not re.match(r"^[A-ZÀ-ÖØ-Þ0-9\s.,':;!?()\-–—]+$", text):
        return text

    cleaned = text.title()
    # Restore common acronyms that title() lowercased
    for acr in _TITLE_CASE_ACRONYMS:
        cleaned = re.sub(r"\b" + re.escape(acr) + r"\b", acr.upper(), cleaned)
    # Lowercase Italian prepositions/articles (not at start of string)
    for prep in _TITLE_CASE_PREPS:
        cleaned = re.sub(r"(?<=\s)" + re.escape(prep) + r"(?=\s)", prep.lower(), cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# clean_display_text — THE key function replacing both _clean_signal_title
#                      and _clean_signal_text
# ---------------------------------------------------------------------------

def clean_display_text(text: str, is_title: bool = False) -> str:
    """Clean a signal text field for user-facing display.

    Applied uniformly to title, what_changed, enriched_summary, diff_summary.
    The is_title flag controls two minor behavioral differences:
    - Newspaper-only text is cleared for non-title fields
    - Label-repair minimum length: 18 chars for titles, 25 for text
    """
    if not text:
        return text

    # For non-title fields, clear text that is just a newspaper name
    if not is_title and NEWSPAPER_ONLY_RE.match(text):
        return ""

    cleaned = _strip_read_time(text)
    cleaned = _strip_urls(cleaned)

    # Strip "added to X portfolio" suffix
    cleaned = re.sub(r"(.+?)\s+added to\s+.+?\s+portfolio(?:\s*\(.*?\))?\s*$", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(.+?)\s+aggiunt[oa]\s+al?\s+portafoglio\s+.+$", r"\1", cleaned, flags=re.IGNORECASE)

    # Strip "Read more" / "Continue reading" / "LEGGI TUTTO" / "Approfondisci" link text
    cleaned = re.sub(r"\s*Approfondisci\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^LEGGI\s+TUTTO\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Continua a leggere\s*[\"'\u201c\u201d]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^Continue reading\s*["\u201c]?\s*', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'["\u201d]\s*$', "", cleaned)

    # Strip "more details" suffix
    cleaned = re.sub(r"\s*more\s+details\s*$", "", cleaned, flags=re.IGNORECASE)

    # Insert space before ALL-CAPS word concatenated to lowercase
    cleaned = re.sub(r"([a-z])([A-Z]{3,})", r"\1 \2", cleaned)

    # Strip leading/trailing curly quotes
    cleaned = re.sub('^[\u201c\u201d"]+\\s*', '', cleaned)
    cleaned = re.sub('\\s*[\u201c\u201d"]+$', '', cleaned)

    # Insert missing space after common prefixes if concatenated
    cleaned = re.sub(r"(?i)\b(press\s*release|comunicato\s*stampa)(?=[A-Z])", r"\1 ", cleaned)
    # Insert space between year and following word if concatenated
    cleaned = re.sub(r"(\d{4})(?=[A-Za-z])", r"\1 ", cleaned)

    # Remove date prefixes
    cleaned = strip_date_prefixes(cleaned)

    # Remove press release prefix
    cleaned = strip_press_release_prefix(cleaned)

    # Remove date suffixes
    cleaned = strip_date_suffixes(cleaned)

    # Currency normalization (inline compact forms only — full normalize_monetary_values
    # is called separately by _clean_signal_fields)
    cleaned = re.sub(r"€\s*(\d[\d.,]*)\s*bn\b", lambda m: f"€{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"€\s*(\d[\d.,]*)\s*(?:mln|million)\b", lambda m: f"€{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*milion[ei]\s+(?:di\s+)?euro", lambda m: f"€{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*miliard[ei]\s+(?:di\s+)?euro", lambda m: f"€{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*mln\s+(?:di\s+)?euros?", lambda m: f"€{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*mld\s+(?:di\s+)?euros?", lambda m: f"€{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d[\d.,]*)\s+mln\b", lambda m: f"€{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d[\d.,]*)\s+mld\b", lambda m: f"€{m.group(1)}B", cleaned, flags=re.IGNORECASE)

    # Apply spacing fixes
    cleaned = fix_spacing(cleaned)

    # After spacing fix, strip sector+date suffixes
    cleaned = _SECTOR_DATE_SUFFIX_RE.sub("", cleaned).strip()
    # Re-strip date suffixes exposed by spacing fix
    cleaned = DATE_SUFFIX_WORD_RE.sub("", cleaned).strip()
    # Strip orphaned trailing 1-2 digit numbers (leftover day from stripped dates)
    cleaned = re.sub(r"\s+\d{1,2}\s*$", "", cleaned).strip()

    # Repair token splits — label-repair min length depends on is_title
    min_len = 18 if is_title else 25
    base = cleaned
    cleaned = repair_token_splits(cleaned, strip_leading_label=True)
    if len(cleaned.strip()) < min_len:
        cleaned = repair_token_splits(base, strip_leading_label=False)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -|")

    # Strip newspaper attribution suffix
    cleaned = _NEWSPAPER_ATTR_SUFFIX_RE.sub("", cleaned)

    # Final curly quote strip (may be exposed after other prefix removals)
    cleaned = re.sub('^[\u201c\u201d"]+\\s*', '', cleaned)
    cleaned = re.sub('\\s*[\u201c\u201d"]+$', '', cleaned)

    # Known name corrections
    for wrong, correct in CDP_NAME_CORRECTIONS.items():
        cleaned = cleaned.replace(wrong, correct)

    # ALL CAPS → title case
    cleaned = caps_to_title_case(cleaned)

    # Strip leading list-number artifacts ("1. ", "2. ")
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned)

    # Strip press release dateline: "City (XX), date – "
    cleaned = re.sub(
        r"^[A-Z][a-z]+(?:\s+\([A-Z]{2,4}\))?,\s*\d{1,2}\s+\w+\s+\d{4}\s*[-–—]\s*",
        "", cleaned,
    )

    # Strip navigation breadcrumbs: "... | Press releases."
    cleaned = re.sub(r"\s*\|?\s*[Pp]ress\s+[Rr]eleases?\.?\s*$", ".", cleaned).strip()

    return cleaned.strip()
