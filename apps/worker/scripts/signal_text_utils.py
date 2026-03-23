"""Shared signal text cleaning utilities.

Single source of truth for all text display cleaning used by both
filter_signals.py and enrich_signals_openai.py.  Every text field
(title, what_changed, enriched_summary, diff_summary) runs through
the same `clean_display_text()` pipeline, eliminating title-vs-text
sync gaps.
"""

from __future__ import annotations

import re
from functools import lru_cache

from signal_patterns import _strip_read_time, _strip_urls

# ---------------------------------------------------------------------------
# Thresholds and tuning constants
# ---------------------------------------------------------------------------

# Minimum text length after label-repair — if cleaning produces text shorter
# than this, we re-try without stripping the leading label. Titles are shorter
# than body text, so they get a lower threshold.
MIN_CLEANED_TITLE_LEN = 18
MIN_CLEANED_TEXT_LEN = 25

# Fraction of 3+ char words that must start uppercase to trigger title-case
# detection. 0.65 = titles like "Apollo Invests In Italian Company" (5/6 = 83%)
# while "Apollo invests in Italian company" (2/6 = 33%) stays as-is.
TITLE_CASE_DETECTION_THRESHOLD = 0.65

# Maximum single-token length in a summary. Tokens longer than this are
# fused-word artifacts (e.g. "appointedClaudiaPingueasheadoffondo") that make
# the summary look unprofessional.
MAX_SUMMARY_TOKEN_LEN = 25

# Minimum summary length (chars). Below this, a summary is just a bare name
# with no context — cleared so the frontend falls back to the title.
MIN_SUMMARY_LEN = 15

# Number of Italian stop words that trigger "untranslated" detection.
# 3+ means the text is clearly Italian, not just a borrowed word.
ITALIAN_STOP_WORD_THRESHOLD = 3

# Maximum text length for the "no verb" garbage check. Longer texts may
# legitimately lack a verb (long noun-phrase headlines).
NO_VERB_MAX_LEN = 80

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
    r"news release|contents)\b\s*(?:[:\-–]|\s+\d|\d)\s*",
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
    r"Italia Oggi|MF Newswires|StartupItalia|Corriere della Sera|"
    r"The Messenger|Il Messaggero|Verona Courier|Il Giornale|"
    r"Avvenire|Quotidiano Nazionale|Il Giorno|Il Mattino|La Stampa|"
    r"L[''\u2019]Arena|Gazzetta di Mantova)\s*$",
    re.IGNORECASE,
)

# Newspaper attribution suffix pattern
_RE_DANGLING_END = re.compile(
    r"\b(?:and|or|for|with|in|of|to|the|a|an|di|del|della|con|per|che|un|una|al|alla|alle|ai|agli|nel|nella|nelle|sul|sulla|co-in)\s*$",
    re.IGNORECASE,
)

# AUM boilerplate patterns — fund self-descriptions, NOT deal amounts.
# Monetary amounts in these patterns should never be extracted as deal sizes.
_MONETARY_MAGNITUDE = r"(?:billion|trillion|million|bn|tn|mln|mld|B|T|M)"
_MONETARY_AMOUNT = r"[€$£]?\s*\d[\d.,]*\s*" + _MONETARY_MAGNITUDE

# Full appositive clause: ", a leading global firm with $70B of capital under management,"
_RE_AUM_APPOSITIVE = re.compile(
    r",\s+"
    r"(?:a|one\s+of\s+the|the|which)"
    r"[\w\s,()'\".\-\u2013\u2014€$£~#%&/]{5,150}?"
    r"(?:under\s+management|AuM|AUM)"
    r"\s*,",
    re.IGNORECASE,
)
# Standalone clause: "with [over] $70B [of] capital under management"
_RE_AUM_STANDALONE = re.compile(
    r"(?:with|has|having|manages?|managing)\s+"
    r"(?:over\s+|approximately\s+|more\s+than\s+|about\s+|circa\s+|nearly\s+|~\s*)?"
    + _MONETARY_AMOUNT +
    r"\s+(?:of\s+|in\s+)?"
    r"(?:capital|assets?|funds?|investments?)\s+"
    r"(?:under\s+management|AuM|AUM)",
    re.IGNORECASE,
)
# Bare AUM: "$70B AUM" / "€50B of AUM" / "$1.2T in AUM"
_RE_AUM_BARE = re.compile(
    _MONETARY_AMOUNT +
    r"\s+(?:of\s+|in\s+)?(?:AuM|AUM)\b",
    re.IGNORECASE,
)

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
    "Uni Credit": "UniCredit",
    "Berar di": "Berardi",
}

# Acronyms to restore after title() lowercases them
_TITLE_CASE_ACRONYMS = [
    # Italian legal/institutional
    "Sgr", "Spa", "Srl", "Sas", "Eur", "Aifi", "Pem", "S.P.A.", "S.R.L.",
    # C-suite roles
    "Ceo", "Cfo", "Coo", "Cio",
    # Finance/PE terms
    "Ipo", "Esg", "Lbo", "Mbo", "Npl", "Spac", "Lp", "Gp", "Vc", "Pe",
    # Performance metrics
    "Irr", "Nav", "Ev", "Dpi", "Moic", "Tvpi",
    # Business/tech
    "Saas", "Ai", "Ict", "B2b", "B2c", "Sme", "Cvc",
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

@lru_cache(maxsize=8192)
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
    # Re-attach monetary magnitude letter to currency amount after digit-letter split
    # "€200 Magreementfor" → "€200M agreementfor" (M = millions, split from word)
    cleaned = re.sub(r"([€$£]\d+(?:[.,]\d+)?)\s([KMBT])([a-zà-öø-ÿ])", r"\1\2 \3", cleaned)
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
    cleaned = re.sub(r"\bF\s+2\s+[iI]\b", "F2i", cleaned)
    cleaned = re.sub(r"\bF2I\b", "F2i", cleaned)
    cleaned = re.sub(r"\bB\s+4\s+[iI]\b", "B4i", cleaned)
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
    cleaned = re.sub(r"\bBe\s*Beez\b", "BeBeez", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bSmart\s*4\s*T\s*ech\b", "Smart4Tech", cleaned)
    cleaned = re.sub(r"\bID\s*e\s*A\b", "IDea", cleaned)
    cleaned = re.sub(r"\bGT\s*x\b", "GTx", cleaned)
    cleaned = re.sub(r"\bFounta\s*in\s*Vest\b", "FountainVest", cleaned)
    cleaned = re.sub(r"\bXG\s+en\b", "XGen", cleaned)
    # Company name OCR/line-break artifacts (word split mid-name)
    cleaned = re.sub(r"\bTommas\s+in\s+Utensili\b", "Tommasin Utensili", cleaned)
    cleaned = re.sub(r"\bSaa\s+S\s*solutions\b", "SaaS solutions", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bAcceler\s+ORA\b", "AccelerORA", cleaned)
    # OCR verb corruption: "integers BIA" → "enters BIA" (scraping artifact from specific fund site)
    # Scoped to known Italian company/market abbreviations to avoid corrupting tech signals
    # that legitimately use the word "integers" (data types, programming context).
    cleaned = re.sub(r"\bintegers\s+(BIA|BV|SPA|SRL|NV|AG|SA)\b", r"enters \1", cleaned)
    cleaned = re.sub(r"\bTeamsystem\b", "TeamSystem", cleaned, flags=re.IGNORECASE)
    # Italian word splits from OCR/PDF
    cleaned = re.sub(r"\b([Tt]rasferimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ff]inanziamen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Dd]eposi)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ss]tabilimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Pp]otenziamen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Ii]nvestimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\b([Rr]iferimen)\s+(to)\b", r"\1\2", cleaned)
    cleaned = re.sub(r"\bRosari\s+to(?=,\s)", "Rosario", cleaned)
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
    # "financ ING" → "financing" (ING bank name splits the word)
    cleaned = re.sub(r"\bfinanc\s+ING\b", "financing", cleaned)
    # "2025–2028Term" → "2025–2028 Term"
    cleaned = re.sub(r"(\d{4})Term\b", r"\1 Term", cleaned)
    # "Serie A/B/C" → "Series A/B/C"
    cleaned = re.sub(r"\b[Ss][Ee][Rr][Ii][Ee]\s+([A-Ga-g])\b", lambda m: f"Series {m.group(1).upper()}", cleaned)
    # Mojibake: â¬€ / â¬ → €
    cleaned = cleaned.replace("â¬€", "€").replace("â¬", "€")
    # Fix newspaper domain split: "ilsole 24 ore" → "ilsole24ore"
    cleaned = re.sub(r"\bilsole\s+24\s+ore\b", "ilsole24ore", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bsole\s+24\s+ore\b", "sole24ore", cleaned, flags=re.IGNORECASE)
    # Italian appointment phrases → English (common untranslated pattern)
    cleaned = re.sub(r"\bnominat[oa]\s+", "appointed ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bamministratore\s+delegato\b", "CEO", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdirettore\s+generale\b", "general manager", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bresponsabile\s+del?\b", "head of", cleaned, flags=re.IGNORECASE)
    # Italian connectives in otherwise English text: "e" → "and", "di" → "of"
    # Only replace when surrounded by English context (capitalized words / roles)
    cleaned = re.sub(r"\b([A-Z]\w+)\s+e\s+([A-Z]\w+)", r"\1 and \2", cleaned)
    cleaned = re.sub(r"\bCEO\s+e\s+", "CEO and ", cleaned)
    cleaned = re.sub(r"\b(officer|manager|director)\s+di\s+", r"\1 of ", cleaned, flags=re.IGNORECASE)

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
    # "XI talia" → "XItalia" (OCR artifact from CDP newsroom)
    cleaned = re.sub(r"\bXI\s+talia\b", "XItalia", cleaned)
    # "Ifund" → "I Fund" (font/encoding artifact)
    cleaned = re.sub(r"\bIfund\b", "I Fund", cleaned)
    # "Travelso" → "Travelsoft" (common truncation)
    cleaned = re.sub(r"\bTravelso\b", "Travelsoft", cleaned)
    # Strip leading numbered list artifacts (e.g. "1. Item" or "1) Item")
    # Require period or closing paren — prevents stripping fund names like "21 Invest" or "3i"
    cleaned = re.sub(r"^\d+[.)]\s+(?=[A-Z])", "", cleaned)
    # Italian ordinals in text ("1 a edizione" → "1a edizione"), but only when
    # followed by an ordinal noun. This avoids corrupting plain prose like
    # "140 a fine 2026" back into "140a fine 2026".
    cleaned = re.sub(
        r"\b(\d+)\s+([ao])\s+(?=(?:edizione|fase|serie|tranche|volta|giornata|rata|classe|semestre|trimestre|anno)\b)",
        r"\1\2 ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Brand name corrections (common LLM/OCR token splits)
    cleaned = re.sub(r"\bOpen\s+AI\b", "OpenAI", cleaned)
    cleaned = re.sub(r"\bUni\s*Credit\b", "UniCredit", cleaned)
    cleaned = re.sub(r"\bBorg\s*Warner\b", "BorgWarner", cleaned)
    cleaned = re.sub(r"\bInfo\s+Cert\b", "InfoCert", cleaned)
    cleaned = re.sub(r"\b[Bb]rand\s*[Oo]n\s+[Gg]roup\b", "BrandOn Group", cleaned)
    cleaned = re.sub(r"\b[Ff]in\s*[Tt]ech\b", "fintech", cleaned)
    cleaned = re.sub(r"\bTechnology\s*transfer\b", "Technology Transfer", cleaned, flags=re.IGNORECASE)
    # Lowercase company names before fund parenthetical + deal verb.
    # "errevi system (Kyip Capital SGR) acquires ..." → "Errevi System (Kyip Capital SGR) acquires ..."
    cleaned = re.sub(
        r"^([a-zà-öø-ÿ][a-zà-öø-ÿ'’.\-]*(?:\s+[a-zà-öø-ÿ][a-zà-öø-ÿ'’.\-]*){0,3})\s+\(([^)]{2,40})\)\s+((?:acquir\w+|sells?|selling|invests?|merg\w+|raises?))\b",
        lambda m: f"{m.group(1).title()} ({m.group(2)}) {m.group(3)}",
        cleaned,
    )
    # Italian phrases that slip through translation
    cleaned = re.sub(r"\bgestito\s+da\b", "managed by", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bsociet[àa]\s+di\s+gestione\b", "management company", cleaned, flags=re.IGNORECASE)
    # "IndustriaItaliana:" prefix artifact from RSS feeds
    cleaned = re.sub(r"\bIndustria\s*[Ii]taliana\s*:\s*", "", cleaned)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # Re-compact currency amount suffixes split by digit-letter spacing
    cleaned = re.sub(r'([€$£]\d+(?:[.,]\d+)?)\s+([KMBT])\b', r'\1\2', cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# repair_token_splits — merges filter's _repair_common_splits + enricher's
#                        _normalize_token_splits + additional patterns
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8192)
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
            # Period-before-3-digits is Italian thousands separator (e.g. 1.000 = 1000)
            # — except with B (billions), where it's always a decimal: stripping it
            # would yield thousands of billions, which is never realistic.
            if multiplier != "B":
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


@lru_cache(maxsize=8192)
def normalize_monetary_values(text: str) -> str:
    """Normalize monetary values to consistent €X.XM / €X.XB format.

    Handles Italian (milioni, miliardi, mln) and English (million, billion, bn).
    Preserves USD/GBP prefix when present. Defaults to EUR (€) for unspecified.
    Also normalizes Italian "oltre"→"over" and "circa"→"~" (from enricher).
    """
    if not text:
        return text

    result = text

    # Comma-formatted thousands → compact notation: €720,000 → €720K, €1,200,000 → €1.2M
    # Must run before other rules to avoid double-processing.
    def _expand_comma_thousands(m: re.Match) -> str:  # type: ignore[type-arg]
        sym = m.group(1)
        val = int(m.group(2).replace(",", ""))
        if val >= 1_000_000_000:
            return f"{sym}{val / 1e9:.3g}B"
        if val >= 1_000_000:
            return f"{sym}{val / 1e6:.3g}M"
        if val >= 1_000:
            return f"{sym}{val // 1000}K"
        return m.group(0)
    result = re.sub(
        r"([€$£])\s*(\d{1,3}(?:,\d{3})+)(?!\s*[KMBT]|\d)",
        _expand_comma_thousands,
        result,
    )

    # Italian quantity words (from enricher)
    result = re.sub(r"\boltre\b", "over", result, flags=re.IGNORECASE)
    result = re.sub(r"\bcirca\b", "~", result, flags=re.IGNORECASE)

    # Verbal amounts: "two/three/... million euros" → €2M/€3M
    _VERBAL_NUMBERS = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    }
    for word, digit in _VERBAL_NUMBERS.items():
        result = re.sub(
            rf"\b{word}\s+(?:million|milion[ei]?)\s+(?:di\s+)?euro[s]?\b",
            f"€{digit}M",
            result, flags=re.IGNORECASE,
        )
        result = re.sub(
            rf"\b{word}\s+(?:billion|miliard[io]?)\s+(?:di\s+)?euro[s]?\b",
            f"€{digit}B",
            result, flags=re.IGNORECASE,
        )

    # Fix "approximately of X millions euros" → "approximately €XM"
    result = re.sub(
        r"\bapproximately\s+of\s+(\d+)\s+millions?\s+euros?\b",
        lambda m: f"approximately €{m.group(1)}M",
        result, flags=re.IGNORECASE,
    )
    # Fix "X millions euros" → "€XM"
    result = re.sub(
        r"\b(\d+)\s+millions?\s+(?:di\s+)?euros?\b",
        lambda m: f"€{m.group(1)}M",
        result, flags=re.IGNORECASE,
    )

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
    # "X m Funding/Investment/Round/Raise/Deal" (no currency symbol) → €XM
    # Handles patterns like "7 m Funding Round" from translated press releases that drop the
    # currency symbol. Only fires in financial context to avoid false positives on other "m" words.
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\s+m\b(?=\s+(?:Funding|Investment|Round|Raise|Deal)\b)',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )

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

    # "X+ mln €" / "X mln $" (reversed currency) → €XM / $XM
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\+?\s+mln\s+€',
        lambda m: _format_amount(m.group(1), "M") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\+?\s+mln\s+\$',
        lambda m: _format_amount(m.group(1), "M", "$") or m.group(0),
        result, flags=re.IGNORECASE,
    )
    result = re.sub(
        r'\b(\d+(?:[.,]\d+)?)\+?\s+mld\s+€',
        lambda m: _format_amount(m.group(1), "B") or m.group(0),
        result, flags=re.IGNORECASE,
    )

    # Italian descriptive amounts in deal_amount: "decine di mln" → "tens of millions"
    result = re.sub(r'\bdecine\s+di\s+mln\b', 'tens of millions', result, flags=re.IGNORECASE)
    result = re.sub(r'\bcentinaia\s+di\s+mln\b', 'hundreds of millions', result, flags=re.IGNORECASE)
    result = re.sub(r'\bdecine\s+di\s+milioni\b', 'tens of millions', result, flags=re.IGNORECASE)

    # Catch-all: "EUR" + compact amount → € symbol (e.g. "EUR 200M" → "€200M")
    result = re.sub(r'\bEUR\s*(\d+(?:[.,]\d+)?)\s*([KMBT])\b', lambda m: f"€{m.group(1)}{m.group(2)}", result)
    # Reversed: "200M EUR" → "€200M"
    result = re.sub(r'\b(\d+(?:[.,]\d+)?)\s*([KMBT])\s*EUR\b', lambda m: f"€{m.group(1)}{m.group(2)}", result)

    # Clean up spacing: "€ 500M" → "€500M"
    result = re.sub(r"€\s+(\d)", r"€\1", result)

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

@lru_cache(maxsize=4096)
def caps_to_title_case(text: str) -> str:
    """Convert ALL CAPS text to title case, preserving acronyms and lowercasing prepositions.

    Handles two cases:
    1. Fully uppercase: "SENIOR INVESTMENT ASSOCIATE" — entire string is ALL CAPS.
    2. Mostly uppercase: "SENIOR INVESTMENT ASSOCIATE, CLEAN ENERGY - Capital Dynamics"
       — mixed string where >50% of words are ALL CAPS. Converts the ALL CAPS
       words individually and leaves already-correct mixed-case words untouched.
    """
    if not text:
        return text
    if len(text) <= 20:
        return text

    # Build a set of known acronyms (upper) for quick lookup during word conversion
    _acr_set = {a.upper() for a in _TITLE_CASE_ACRONYMS}

    fully_caps = bool(re.match(r"^[A-ZÀ-ÖØ-Þ0-9\s.,':;!?()\-–—€$£%/&]+$", text))

    if not fully_caps:
        # Check for "mostly caps": >50% of alphabetic words (3+ chars) are ALL CAPS
        words = text.split()
        alpha_words = [re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", w) for w in words]
        long_alpha = [w for w in alpha_words if len(w) >= 3]
        if not long_alpha:
            return text
        caps_count = sum(1 for w in long_alpha if w == w.upper())
        if caps_count / len(long_alpha) <= 0.5:
            return text  # Not mostly caps — leave untouched

        # Convert word-by-word: only touch fully-uppercase words
        def _convert_word(w: str) -> str:
            core = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", w)
            if len(core) < 3 or core != core.upper():
                return w  # Short word or already mixed-case — preserve as-is
            if core.upper() in _acr_set:
                return w  # Known acronym — preserve uppercase
            return w[0].upper() + w[1:].lower() if len(w) == len(core) else w.title()

        cleaned = " ".join(_convert_word(w) for w in words)
    else:
        cleaned = text.title()

    # Restore common acronyms that title() lowercased
    for acr in _TITLE_CASE_ACRONYMS:
        cleaned = re.sub(r"\b" + re.escape(acr) + r"\b", acr.upper(), cleaned)
    # Lowercase Italian prepositions/articles (not at start of string)
    for prep in _TITLE_CASE_PREPS:
        cleaned = re.sub(r"(?<=\s)" + re.escape(prep) + r"(?=\s)", prep.lower(), cleaned)
    return cleaned


# Words that should stay lowercase in sentence case (English articles/preps/conjunctions)
_SENTENCE_CASE_LOWERCASE = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "yet", "so",
    "in", "on", "at", "to", "by", "of", "up", "as", "if", "is",
    "with", "from", "into", "over", "after", "before", "between",
    "through", "during", "without", "within", "about", "its",
}

# Words that should ALWAYS stay uppercase (acronyms, fund names)
_SENTENCE_CASE_ALWAYS_UPPER = {
    "sgr", "spa", "srl", "sas", "ceo", "cfo", "coo", "cio", "cto",
    "ipo", "esg", "ai", "vc", "pe", "lp", "gp", "aum", "eu", "uk", "us",
    "kkr", "eqt", "dif", "dws", "clm",
}


def _is_title_cased(text: str) -> bool:
    """Detect if text has Every Word Capitalized (title case).

    Returns True if >60% of words (with 3+ chars) start uppercase,
    which indicates title-case text that should be normalized to
    sentence case.
    """
    words = text.split()
    if len(words) < 4:
        return False
    long_words = [w for w in words if len(w) >= 3 and w[0].isalpha()]
    if len(long_words) < 3:
        return False
    capitalized = sum(1 for w in long_words if w[0].isupper())
    # Also check it's NOT all caps (already handled by caps_to_title_case)
    all_caps_count = sum(1 for w in long_words if w.isupper())
    if all_caps_count > len(long_words) * 0.5:
        return False
    return capitalized / len(long_words) > TITLE_CASE_DETECTION_THRESHOLD


@lru_cache(maxsize=4096)
def title_case_to_sentence_case(text: str) -> str:
    """Convert Title Case text to sentence case.

    'Capza Invests In Travelsoft' → 'Capza invests in Travelsoft'

    Preserves:
    - First word capitalization
    - Proper nouns (heuristic: words not in common lowercase set)
    - Known acronyms
    - Words after sentence-ending punctuation
    """
    if not text or not _is_title_cased(text):
        return text

    words = text.split()
    result = []
    after_sentence_end = True  # First word starts capitalized

    for i, word in enumerate(words):
        # Strip leading punctuation for analysis, preserve it
        stripped = word.lstrip("(\"'")
        prefix = word[:len(word) - len(stripped)]
        core = stripped

        if not core or not core[0].isalpha():
            result.append(word)
            after_sentence_end = word.endswith((".", "!", "?", ":"))
            continue

        core_lower = core.lower()

        # Always uppercase acronyms
        if core_lower in _SENTENCE_CASE_ALWAYS_UPPER:
            result.append(prefix + core.upper())
            after_sentence_end = False
            continue

        # Keep first word / word after sentence break capitalized
        if after_sentence_end:
            result.append(word)
            after_sentence_end = False
            continue

        # Lowercase common articles/prepositions/conjunctions
        if core_lower in _SENTENCE_CASE_LOWERCASE:
            result.append(prefix + core_lower)
            after_sentence_end = False
            continue

        # For remaining words: lowercase them UNLESS they look like proper nouns.
        # Heuristic: words with mixed case (e.g. "MacQuarie") or all-caps ≥2 chars
        # are likely proper nouns / acronyms — keep as-is.
        if core.isupper() and len(core) >= 2:
            # Acronym — keep uppercase
            result.append(word)
        elif len(core) >= 2 and core[0].isupper() and any(c.isupper() for c in core[1:]):
            # Mixed case like "iPhone", "McKinsey" — keep as-is
            result.append(word)
        else:
            # Regular title-cased word — lowercase it
            result.append(prefix + core[0].lower() + core[1:])

        after_sentence_end = word.endswith((".", "!", "?", ":"))

    # Re-capitalize the very first alpha character
    final = " ".join(result)
    for i, ch in enumerate(final):
        if ch.isalpha():
            final = final[:i] + ch.upper() + final[i+1:]
            break

    return final



# Module-level constants for pipeline stages
_GEO_PROPER_NOUNS = [
    "italy", "italian", "spain", "spanish", "france", "french",
    "germany", "german", "europe", "european", "benelux", "nordic",
    "belgium", "netherlands", "portugal", "austria", "switzerland",
    "london", "paris", "milan", "rome", "madrid", "berlin", "mexico", "rosario",
    "americas", "emea", "asia", "uk", "us", "usa",
]

_FUSED_WORD_PAIRS = [
    (r"chiefexecutiveofficer", "chief executive officer"),
    (r"chiefexecutive", "chief executive"),
    (r"generalmanager", "general manager"),
    (r"headof", "head of"),
    (r"officerand", "officer and"),
    (r"officeror", "officer or"),
    (r"officerof", "officer of"),
    (r"managerof", "manager of"),
    (r"directorof", "director of"),
    (r"partnerof", "partner of"),
    (r"presidentof", "president of"),
    (r"chairmanof", "chairman of"),
    (r"ashead", "as head"),
    (r"aschief", "as chief"),
    (r"asdirector", "as director"),
    (r"asmanaging", "as managing"),
    (r"aspartner", "as partner"),
    (r"asadvisors?", "as advisor"),
    (r"asincoming", "as incoming"),
    (r"oftheboardof", "of the board of"),
    (r"oftheboard", "of the board"),
    (r"boardof", "board of"),
    (r"tomanagethe", "to manage the"),
    (r"tomanage", "to manage"),
    (r"incominghead", "incoming head"),
    (r"theprocess", "the process"),
    (r"forthe(\d)", r"for the \1"),
    # LLM token-merge artifacts — prepositions/articles fused to adjacent words
    (r"appointedas\b", "appointed as"),
    (r"managingdirector", "managing director"),
    (r"ofthe\b", "of the"),
    (r"inthe\b", "in the"),
    (r"tothe\b", "to the"),
    (r"bythe\b", "by the"),
    (r"onthe\b", "on the"),
    (r"atthe\b", "at the"),
    (r"andthe\b", "and the"),
    (r"withthe\b", "with the"),
    (r"fromthe\b", "from the"),
    (r"forthe\b", "for the"),
    (r"asthe\b", "as the"),
    (r"launchesthe\b", "launches the"),
    (r"announcesthe\b", "announces the"),
    (r"completesthe\b", "completes the"),
    (r"closedthe\b", "closed the"),
    (r"signsthe\b", "signs the"),
    (r"entersthe\b", "enters the"),
    (r"exitsthe\b", "exits the"),
    (r"joinsthe\b", "joins the"),
    (r"sellsthe\b", "sells the"),
    (r"acquiredby\b", "acquired by"),
    (r"managedby\b", "managed by"),
    (r"investedin\b", "invested in"),
    (r"partnerswith\b", "partners with"),
    # Fused title/role words
    (r"managingpartner", "managing partner"),
    (r"seniorpartner", "senior partner"),
    (r"senioradvisor", "senior advisor"),
    (r"chiefoperatingofficer", "chief operating officer"),
    (r"chieffinancialofficer", "chief financial officer"),
    (r"chiefinvestmentofficer", "chief investment officer"),
    (r"vicepresident", "vice president"),
    (r"deputychief", "deputy chief"),
]


# ---------------------------------------------------------------------------
# clean_display_text — composable pipeline stages
# ---------------------------------------------------------------------------


def _cdt_strip_boilerplate(text: str, is_title: bool) -> str:
    """Strip scraping artifacts, boilerplate templates, and AUM self-descriptions.

    Handles: Logo prefix, duplicate labels, News prefix, Italian articles,
    read time, URLs, 'New X involving Y' templates, AUM self-descriptions,
    portfolio template rewrites, 'Read more' link text.
    """
    # Strip "Logo X" prefix (image caption artifacts)
    cleaned = re.sub(r"^Logo\s+", "", text, flags=re.IGNORECASE).strip()
    if not cleaned:
        cleaned = text

    # Strip duplicate label prefixes: "News: News ..." -> "News ..."
    cleaned = re.sub(r"^(News|Update|Announcement)\s*:\s*\1\b\s*", r"\1 ", cleaned, flags=re.IGNORECASE)
    # Strip bare "News:" / "News -" prefix
    cleaned = re.sub(r"^News\s*[:\-\u2013]\s*", "", cleaned, flags=re.IGNORECASE)

    # Strip leading Italian articles before proper nouns (display artifact)
    cleaned = re.sub(r"^(?:Il|La|Lo|Le|Gli|I)\s+(?=[A-Z\u00C0-\u00D6\u00D8-\u00DE][a-z\u00E0-\u00F6\u00F8-\u00FF])", "", cleaned)

    cleaned = _strip_read_time(cleaned)
    cleaned = _strip_urls(cleaned)

    # Strip boilerplate "New X involving Y" templates (scraping artifacts)
    cleaned = re.sub(
        r"^New\s+(?:investment|announcement|fundraise|deal|exit|partnership)\s+involving\s+",
        "", cleaned, flags=re.IGNORECASE,
    )

    # AUM boilerplate — fund self-descriptions, not deal amounts
    cleaned = _RE_AUM_APPOSITIVE.sub(",", cleaned)
    cleaned = _RE_AUM_STANDALONE.sub("", cleaned)
    cleaned = _RE_AUM_BARE.sub("", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)

    # Portfolio rewrites moved to clean_display_text() to preserve original casing

    # Strip "Read more" / "Continue reading" / "LEGGI TUTTO" / "Approfondisci" link text
    cleaned = re.sub(r"\s*Approfondisci\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^LEGGI\s+TUTTO\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Continua a leggere\s*[\"'\u201c\u201d]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^Continue reading\s*["\u201c]?\s*', "", cleaned, flags=re.IGNORECASE)
    # Strip "Continue reading" at END of text (WordPress blog excerpt artifact)
    cleaned = re.sub(r'\s*Continue reading\s*["\u201c\u201d]?.*$', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*Continua a leggere\s*["\u201c\u201d]?.*$', "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'["\u201d]\s*$', "", cleaned)

    # Strip "more details" suffix
    cleaned = re.sub(r"\s*more\s+details\s*$", "", cleaned, flags=re.IGNORECASE)

    # Strip "Back Download Press Release" navigation artifact
    cleaned = re.sub(r"\s*Back\s+Download\s+Press\s+Release\s*", " ", cleaned, flags=re.IGNORECASE)

    # Strip trailing placeholder word "Historical" (LLM artifact)
    cleaned = re.sub(r"\s*\.?\s*Historical\s*\.?\s*$", ".", cleaned, flags=re.IGNORECASE)

    # Strip LLM meta-commentary sentences — reasoning leaked from the enricher/monitor LLM.
    # These are sentences where the LLM explains what TYPE of signal this is instead of
    # describing actual news content.  They always appear as trailing sentences.
    # e.g. "This is news of a management change, not an M&A transaction."
    # e.g. "This is not a deal announcement."  "This article covers X, not a deal."
    #
    # IMPORTANT: _META_SEP must only match sentence-ending punctuation, NOT bare whitespace.
    # Using \s+ would match spaces within sentences (e.g. "Note: This is..." becomes
    # "Note: " + "This is..." match, leaving orphaned "Note:" after stripping).
    _META_SEP = r"(?:[.!?]\s*)"  # sentence boundary — requires sentence-ending punctuation

    # "This is news of X, not an M&A transaction." / "This is a management change, not a deal."
    # Applied both at start-of-text (^) and after a sentence boundary
    _META_CORE_1 = (
        r"This\s+is\s+(?:news\s+of\s+)?(?:a\s+|an\s+)?[\w\s,'\u2019\-]{3,60}?"
        r"\bnot\s+an?\s+(?:M&A|M\s*&\s*A|merger|acquisition|deal|exit|transaction|fundraise)\b[^.]{0,60}\."
    )
    cleaned = re.sub(r"^" + _META_CORE_1, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(_META_SEP + _META_CORE_1, ".", cleaned, flags=re.IGNORECASE)

    # "This is not an M&A transaction / deal / announcement."
    _META_CORE_2 = (
        r"This\s+is\s+not\s+an?\s+(?:M&A|M\s*&\s*A|merger|acquisition|deal|exit|fundraise|investment)"
        r"\s*(?:transaction|announcement|event|deal)?[^.]{0,40}\."
    )
    cleaned = re.sub(r"^" + _META_CORE_2, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(_META_SEP + _META_CORE_2, ".", cleaned, flags=re.IGNORECASE)

    # "This article/signal/piece reports on X, not a deal."
    _META_CORE_3 = (
        r"This\s+(?:article|signal|piece|report|news\s+item|post)"
        r"\s+(?:is\s+about|reports?\s+on|covers?|discusses?|describes?|concerns?)\s+[^.]{0,120}\."
    )
    cleaned = re.sub(r"^" + _META_CORE_3, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(_META_SEP + _META_CORE_3, ".", cleaned, flags=re.IGNORECASE)

    # "Note: This is a people move, not a deal." — possibly at start of text
    _META_NOTE = (
        r"Note[:\s]+[Tt]his\s+is\s+(?:not\s+)?(?:a\s+|an\s+)?"
        r"[\w\s,]{3,80}?(?:not\s+an?\s+[\w\s]{3,40}?)?[.!]"
    )
    cleaned = re.sub(r"^" + _META_NOTE, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(_META_SEP + _META_NOTE, ".", cleaned, flags=re.IGNORECASE)

    # Collapse orphaned "." artifacts left by stripping
    cleaned = re.sub(r"\.\s*\.\s*$", ".", cleaned)
    cleaned = re.sub(r"^\.\s*", "", cleaned)

    # Clean up trailing/leading period artifacts
    cleaned = re.sub(r"^\.\s*", "", cleaned)
    cleaned = re.sub(r"\.\.\s*$", ".", cleaned)

    return cleaned


def _cdt_normalize_spacing_and_dates(text: str) -> str:
    """Fix spacing issues, strip dates, and normalize inline currencies.

    Handles: ALL-CAPS/lowercase concatenation, curly quotes, prefix/year
    concatenation, date prefixes/suffixes, press release prefix, inline
    currency normalization, fix_spacing(), sector+date suffixes.
    """
    cleaned = text

    # Insert space before ALL-CAPS word concatenated to lowercase
    cleaned = re.sub(r"([a-z])([A-Z]{3,})", r"\1 \2", cleaned)

    # Fix doubled articles: "the The" → "The", "a A" → "A", "an An" → "An"
    cleaned = re.sub(r"\b(the)\s+the\b", "the", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(a)\s+a\b(?!\s*\w*[a-z]{2})", "a", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(an)\s+an\b", "an", cleaned, flags=re.IGNORECASE)
    # Mixed-case double article: "the The" → "The" (capital follows lower)
    cleaned = re.sub(r"\bthe\s+The\b", "The", cleaned)
    cleaned = re.sub(r"\ba\s+A\b", "A", cleaned)

    # Strip leading/trailing curly quotes
    cleaned = re.sub('^[\u201c\u201d"]+\\s*', '', cleaned)
    cleaned = re.sub('\\s*[\u201c\u201d"]+$', '', cleaned)

    # Insert missing space after common prefixes if concatenated
    cleaned = re.sub(r"(?i)\b(press\s*release|comunicato\s*stampa)(?=[A-Z])", r"\1 ", cleaned)
    # Insert space between year and following word if concatenated
    cleaned = re.sub(r"(\d{4})(?=[A-Za-z])", r"\1 ", cleaned)

    # Remove date prefixes and suffixes
    cleaned = strip_date_prefixes(cleaned)
    cleaned = strip_press_release_prefix(cleaned)
    cleaned = strip_date_suffixes(cleaned)

    # Currency normalization (inline compact forms only — full normalize_monetary_values
    # is called separately by _clean_signal_fields)
    cleaned = re.sub(r"\u20ac\s*(\d[\d.,]*)\s*bn\b", lambda m: f"\u20ac{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\u20ac\s*(\d[\d.,]*)\s*(?:mln|million)\b", lambda m: f"\u20ac{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*milion[ei]\s+(?:di\s+)?euro", lambda m: f"\u20ac{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*miliard[ei]\s+(?:di\s+)?euro", lambda m: f"\u20ac{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*mln\s+(?:di\s+)?euros?", lambda m: f"\u20ac{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\d[\d.,]*)\s*mld\s+(?:di\s+)?euros?", lambda m: f"\u20ac{m.group(1)}B", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d[\d.,]*)\s+mln\b", lambda m: f"\u20ac{m.group(1)}M", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\d[\d.,]*)\s+mld\b", lambda m: f"\u20ac{m.group(1)}B", cleaned, flags=re.IGNORECASE)

    # Apply spacing fixes
    cleaned = fix_spacing(cleaned)

    # After spacing fix, strip sector+date suffixes
    cleaned = _SECTOR_DATE_SUFFIX_RE.sub("", cleaned).strip()
    # Re-strip date suffixes exposed by spacing fix
    cleaned = DATE_SUFFIX_WORD_RE.sub("", cleaned).strip()
    # Strip orphaned trailing 1-2 digit numbers (leftover day from stripped dates)
    cleaned = re.sub(r"\s+\d{1,2}\s*$", "", cleaned).strip()

    return cleaned


def _cdt_repair_tokens_and_attributes(text: str, is_title: bool) -> str:
    """Repair fragmented tokens, strip attributions, and fix trailing artifacts.

    Handles: repair_token_splits with label-repair fallback, newspaper
    attribution suffix, final curly quotes, dangling connectors, CDP name
    corrections.
    """
    # Repair token splits — label-repair min length depends on is_title
    min_len = MIN_CLEANED_TITLE_LEN if is_title else MIN_CLEANED_TEXT_LEN
    base = text
    cleaned = repair_token_splits(text, strip_leading_label=True)
    if len(cleaned.strip()) < min_len:
        cleaned = repair_token_splits(base, strip_leading_label=False)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" -|")

    # Strip newspaper attribution suffix
    cleaned = _NEWSPAPER_ATTR_SUFFIX_RE.sub("", cleaned)

    # Final curly quote strip (may be exposed after other prefix removals)
    cleaned = re.sub('^[\u201c\u201d"]+\\s*', '', cleaned)
    cleaned = re.sub('\\s*[\u201c\u201d"]+$', '', cleaned)

    # Strip dangling connectors at end of text (not titles)
    if not is_title and _RE_DANGLING_END.search(cleaned):
        cleaned = re.sub(r"\s+\S+\s*$", "", cleaned).strip()

    # Known name corrections
    for wrong, correct in CDP_NAME_CORRECTIONS.items():
        cleaned = cleaned.replace(wrong, correct)
    cleaned = re.sub(r"\buni\s+credit\b", "UniCredit", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bberar\s+di\b", "Berardi", cleaned, flags=re.IGNORECASE)

    # Restore canonical legal suffix formatting (S.p.A., S.r.l.) when used as
    # corporate suffixes, without touching generic words like "spa" (wellness).
    cleaned = re.sub(
        r"(\b[A-Z][A-Za-z0-9&'’.\-]{1,60})\s+S\.?\s*P\.?\s*A\.?\b",
        r"\1 S.p.A.",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(\b[A-Z][A-Za-z0-9&'’.\-]{1,60})\s+S\.?\s*R\.?\s*L\.?\b",
        r"\1 S.r.l.",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bHIG\s+Capital\b", "H.I.G. Capital", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bHIG\s+Europe\b", "H.I.G. Europe", cleaned, flags=re.IGNORECASE)

    # Remove redundant CDP long-form parenthetical expansions when acronym is
    # already present (e.g. "CDP Equity (Cassa Depositi and Prestiti)").
    cleaned = re.sub(
        r"\b(CDP(?:\s+Equity)?)\s*\(\s*Cassa\s+Depositi(?:\s+e|\s+and)\s+Prestiti\s*\)",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(CDP(?:\s+Equity)?)\s*\(\s*Cassa\s+Depositi\s+e\s+Prestiti\s+S\.?p\.?A\.?\s*\)",
        r"\1",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned


def _cdt_normalize_casing(text: str, is_title: bool) -> str:
    """Normalize text casing: ALL CAPS to title, Title Case to sentence, person names.

    Handles: ALL CAPS conversion, title case detection and normalization,
    person name capitalization after appointment verbs.
    """
    cleaned = text

    # Detect "mostly caps" before conversion so we can skip sentence-case afterwards.
    # "SENIOR INVESTMENT ASSOCIATE, CLEAN ENERGY - Capital Dynamics" is mostly-caps:
    # >50% of long alpha words are ALL CAPS but the string isn't fully uppercase.
    # After caps_to_title_case() converts the ALL CAPS words, the result is already
    # correct title case — running title_case_to_sentence_case() on top would then
    # lowercase already-correct proper nouns like "Capital Dynamics".
    _words_tmp = cleaned.split()
    _alpha_tmp = [re.sub(r"[^A-Za-z\u00C0-\u00D6\u00D8-\u00DE\u00E0-\u00F6\u00F8-\u00FF]", "", w) for w in _words_tmp]
    _long_tmp = [w for w in _alpha_tmp if len(w) >= 3]
    _fully_caps = bool(re.match(r"^[A-Z\u00C0-\u00D6\u00D8-\u00DE0-9\s.,':;!?()\-\u2013\u2014\u20AC$\u00A3%/&]+$", cleaned))
    _was_mostly_caps = (
        not _fully_caps
        and bool(_long_tmp)
        and sum(1 for w in _long_tmp if w == w.upper()) / len(_long_tmp) > 0.5
    )

    # ALL CAPS -> title case
    cleaned = caps_to_title_case(cleaned)

    # Title Case -> sentence case.
    # Skipped when the original text was mostly-caps (not fully-caps): the
    # caps_to_title_case() word-by-word path already produced the correct title
    # case by converting only the ALL CAPS tokens and leaving mixed-case words
    # (proper nouns, fund names) intact.  Applying sentence-case on top would
    # incorrectly lowercase those preserved words.
    if not _was_mostly_caps:
        cleaned = title_case_to_sentence_case(cleaned)

    # Capitalize person names after appointment verbs
    # "appointed claudia pingue" -> "appointed Claudia Pingue"
    def _capitalize_person_after_verb(m: re.Match) -> str:
        verb = m.group(1)
        name_part = m.group(2)
        # name_part ends with trailing whitespace (from the \s+ in each repetition).
        # Preserve it so we don't merge the last captured word with the next word.
        trailing_space = " " if name_part.endswith((" ", "\t")) else ""
        words = name_part.split()
        capitalized = []
        for w in words:
            if w.lower() in ("as", "to", "di", "del", "della", "come", "quale"):
                capitalized.append(w)
                break
            if len(w) >= 2 and w[0].islower():
                capitalized.append(w[0].upper() + w[1:])
            else:
                capitalized.append(w)
        remaining_start = len(capitalized)
        capitalized.extend(words[remaining_start:])
        return verb + " " + " ".join(capitalized) + trailing_space

    cleaned = re.sub(
        r"\b(appointed|appoints|names|named|elects|elected|hires|hired|nominat[oa])\s+"
        r"((?:[a-z\u00E0-\u00F6\u00F8-\u00FF]+\s+){1,4})",
        _capitalize_person_after_verb,
        cleaned,
        flags=re.IGNORECASE,
    )

    # Capitalize person surname when it directly PRECEDES an appointment verb.
    # Forward pattern above catches "appointed claudia pingue"; this reverse pattern
    # catches "Claudia pingue appointed" where the name comes first.
    # Requires a capitalized first name so we don't false-positive on fund/company names.
    cleaned = re.sub(
        r"\b([A-Z][a-z\u00C0-\u00D6\u00D8-\u00DE]{2,18})\s+"
        r"([a-z\u00E0-\u00F6\u00F8-\u00FF][a-z\u00E0-\u00F6\u00F8-\u00FF\-'']{2,20})\s+"
        r"(?=(?:appointed|appoints|names|named|elects|elected|hires|hired|nominat[oa]"
        r"|joins?|joined|promoted|leaves?|resign\w*|steps?\s+down)\b)",
        lambda m: m.group(1) + " " + m.group(2).capitalize() + " ",
        cleaned,
    )

    # Capitalize surname at start of text when followed immediately by a job-title word.
    # Pattern: "FirstName lastname managing director..." → "FirstName Lastname managing director..."
    # Safe guard: requires a known job-title word in the 3rd position.
    _JOB_TITLE_GUARD = (
        r"(?:managing\s+director|managing\s+partner|senior\s+partner|general\s+partner"
        r"|head|director|partner|chairman|president|vice\s+president|chief|principal"
        r"|associate|ceo|cfo|coo|cio|officer|responsabile|direttore)"
    )
    cleaned = re.sub(
        r"^([A-Z][a-z]{1,18})\s+([a-z][a-z\-']{2,20})\s+(?=" + _JOB_TITLE_GUARD + r"\b)",
        lambda m: m.group(1) + " " + m.group(2).capitalize() + " ",
        cleaned,
    )

    # Capitalize lowercase person names after C-suite acronyms.
    # Example: "CIO giampaolo di dio leaves" -> "CIO Giampaolo Di Dio leaves"
    def _capitalize_name_after_csuite(m: re.Match) -> str:
        role = (m.group(1) or "").upper()
        name = m.group(2) or ""
        parts = [p for p in name.split() if p]
        if not parts:
            return m.group(0)
        fixed = [p[0].upper() + p[1:] if len(p) > 1 else p.upper() for p in parts]
        return f"{role} {' '.join(fixed)}"

    cleaned = re.sub(
        r"\b(CEO|CFO|COO|CIO|CTO)\s+"
        r"([a-z\u00E0-\u00F6\u00F8-\u00FF][a-z\u00E0-\u00F6\u00F8-\u00FF'’\-]{2,}"
        r"(?:\s+(?:di|de|del|della|dello|da|van|von))?"
        r"(?:\s+[a-z\u00E0-\u00F6\u00F8-\u00FF][a-z\u00E0-\u00F6\u00F8-\u00FF'’\-]{2,}){1,2})"
        r"(?=\s+(?:leaves?|joins?|joined|steps?|stepping|appointed|named|becomes?|is|was|to|at|of|,))",
        _capitalize_name_after_csuite,
        cleaned,
        flags=re.IGNORECASE,
    )

    # Capitalize job-title words in role/appointment context.
    # These words are sentence-case lowercased by title_case_to_sentence_case but should
    # stay capitalised when used as a person's role designation.
    _ROLE_WORDS = (
        r"head|managing\s+director|managing\s+partner|senior\s+partner|general\s+partner"
        r"|director|partner|chairman|president|vice\s+president|chief\s+executive"
        r"|chief\s+investment\s+officer|chief\s+financial\s+officer|principal"
    )
    # Rule A: "as <role>" — appointment context
    cleaned = re.sub(
        r"\bas\s+(" + _ROLE_WORDS + r")\b",
        lambda m: "as " + re.sub(r"\b(\w)", lambda w: w.group(1).upper(), m.group(1)),
        cleaned,
        flags=re.IGNORECASE,
    )
    # Rule B: ", <role> of" or "and <role> of" — comma/and-separated role enumeration
    def _cap_role(m: re.Match) -> str:
        sep, role = m.group(1), m.group(2)
        return sep + re.sub(r"\b(\w)", lambda w: w.group(1).upper(), role) + " of"
    cleaned = re.sub(
        r"([,]\s+|(?<=\s)and\s+)(" + _ROLE_WORDS + r")\s+of\b",
        _cap_role,
        cleaned,
        flags=re.IGNORECASE,
    )
    # Rule C: standalone role after comma without "of" (e.g. ", Managing Director")
    # Only triggers when the role appears as the last significant phrase (end of text or before ",")
    cleaned = re.sub(
        r",\s+(" + _ROLE_WORDS + r")\s*$",
        lambda m: ", " + re.sub(r"\b(\w)", lambda w: w.group(1).upper(), m.group(1)),
        cleaned,
        flags=re.IGNORECASE,
    )

    # Lowercase articles/prepositions that were over-capitalized by title-case passes.
    # "Head Of Fund" → "Head of Fund", "CEO And General Manager" → "CEO and General Manager"
    # Only fires when the small word sits between two title-cased words, so it's safe
    # to apply even when sentence-case conversion was skipped (mixed-language titles).
    cleaned = re.sub(
        r"(?<=[A-Za-z])\s+(Of|And|Or|In|At|To|By|From|With|The)\s+(?=[A-Z])",
        lambda m: " " + m.group(1).lower() + " ",
        cleaned,
    )

    # Capitalize compound role words that sentence-case partially lowercased.
    # "General manager" → "General Manager" (common for AI-generated titles)
    cleaned = re.sub(r"\bGeneral\s+manager\b", "General Manager", cleaned)

    return cleaned


def _cdt_strip_datelines_and_navigation(text: str) -> str:
    """Strip press release datelines, navigation breadcrumbs, and trailing artifacts.

    Handles: list-number prefixes, city datelines (mixed/ALL-CAPS), Featured
    News headers, Press Release breadcrumbs, Series letter fixes, pipe-separated
    boilerplate, trailing truncated words, trailing colons.
    """
    cleaned = text

    # Strip leading list-number artifacts ("1. ", "2. ")
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned)

    # Strip "Article in [Publication]:" meta-summary prefix (enricher occasionally outputs
    # this when summarizing an article instead of its content).
    cleaned = re.sub(
        r"^Article\s+in\s+[\w\s]+:\s*",
        "", cleaned, flags=re.IGNORECASE,
    )

    # Strip "is pleased to announce" PR boilerplate wherever it appears near the start.
    # "H.I.G. Capital ("H.I.G.") is pleased to announce that an affiliate has signed..."
    # → strip up through "announce that" and keep everything after.
    cleaned = re.sub(
        r"^.{0,120}?\bis\s+pleased\s+to\s+announce\s+that\s+",
        "", cleaned, flags=re.IGNORECASE,
    )

    # Strip "Events: City, City – Month DD, YYYY –" dateline (Faro Value / event press releases)
    cleaned = re.sub(
        r"^[Ee]vents?\s*:\s*[\w,\s]+\s*[\u2013\-]\s*\w+\s+\d{1,2},?\s*\d{4}\s*[\u2013\-]\s*",
        "", cleaned,
    )

    # Strip press release dateline: "City (XX), date - "
    cleaned = re.sub(
        r"^[A-Z][a-z]+(?:\s+\([A-Z]{2,4}\))?,\s*\d{1,2}\s+\w+\s+\d{4}\s*[-\u2013\u2014]\s*",
        "", cleaned,
    )
    # Strip multi-city dateline: "City/City, Month DD, YYYY –" (e.g. "Conegliano/Rome, April 23,2025 –")
    cleaned = re.sub(
        r"^[A-Z][a-zA-Z]+(?:/[A-Z][a-zA-Z]+)?,\s*\w+\s+\d{1,2},?\s*\d{4}\s*[\u2013\-\u2014]+\s*",
        "", cleaned,
    )
    # Strip ALL-CAPS city dateline: "MILAN - November 25,2025 -"
    cleaned = re.sub(
        r"^[A-Z][A-Z\s,]+[\u2013\-\u2014]+\s*(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2})\s+\d{1,2},?\s*\d{4}\s*[\u2013\-\u2014]+\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Strip mid-text city/date dateline embedded after an ALL-CAPS headline:
    # "FUND INVESTS IN X Montecchio Maggiore (VI), December 21,2023 - rest of text"
    cleaned = re.sub(
        r"\s+[A-Z][a-zA-Z\s]+\([A-Z]{2,3}\),\s*\w+\s+\d{1,2},?\s*\d{4}\s*[-\u2013\u2014]+\s*",
        " ", cleaned,
    )

    # Strip "Featured News Press Review" header artifact
    cleaned = re.sub(r"\s*\.?\s*Featured\s+News\s+Press\s+Review\s*\.?\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^Featured\s+News\s+Press\s+Review\s*[:\-\u2013]?\s*", "", cleaned, flags=re.IGNORECASE)

    # Strip navigation breadcrumbs: "... | Press releases."
    cleaned = re.sub(r"\s*\|?\s*[Pp]ress\s+[Rr]eleases?\.?\s*$", ".", cleaned).strip()

    # Fix "Series Efinancing" -> "Series E financing" (letter concatenated to word)
    cleaned = re.sub(r"\bSeries\s+([A-G])([a-z]{3,})", r"Series \1 \2", cleaned)

    # Strip pipe-separated boilerplate fragments
    if "|" in cleaned:
        parts = [p.strip() for p in cleaned.split("|")]
        real_parts = [
            p for p in parts
            if len(p) > 3
            and not re.match(r"^(?:press\s+release|news|home|about|portfolio|team|contact)\w*\s*$", p, re.IGNORECASE)
        ]
        if real_parts:
            cleaned = " ".join(real_parts)

    # Strip trailing truncated words (single lowercase letter at end)
    cleaned = re.sub(r"\s+[a-z]\s*$", "", cleaned)

    # Strip trailing colon (interview byline artifact)
    cleaned = re.sub(r"\s*:\s*$", "", cleaned)

    return cleaned


# Actual acronyms that should be fully uppercased (not just short words)
_GEO_ACRONYMS = {"uk", "us", "usa", "emea"}


def _cdt_capitalize_proper_nouns(text: str) -> str:
    """Restore proper capitalization for geographic proper nouns."""
    cleaned = text
    for geo in _GEO_PROPER_NOUNS:
        cleaned = re.sub(
            r"\b" + re.escape(geo) + r"\b",
            geo.upper() if geo in _GEO_ACRONYMS else geo.title(),
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned


def _cdt_split_fused_words(text: str) -> str:
    """Split fused camelCase/run-on words and fix brand tokens.

    Handles: fused role/preposition words (e.g. 'chiefexecutiveofficer'),
    camelCase boundaries, uppercase acronym splits, TGCom24 brand reassembly.
    """
    cleaned = text

    # Step 1: Split known fused role/preposition words
    for pattern, replacement in _FUSED_WORD_PAIRS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    # Step 2: camelCase boundary (lowercase->uppercase)
    cleaned = re.sub(r"([a-z])([A-Z])", r"\1 \2", cleaned)

    # Step 3: uppercase acronym (2+ chars) fused with lowercase word
    # Require 2+ lowercase chars to avoid breaking plural acronyms ("SMEs" -> "SME s").
    cleaned = re.sub(r"\b([A-Z]{2,})([a-z]{2,})\b", r"\1 \2", cleaned)

    # Re-assemble known brand tokens broken by camelCase/acronym splits
    cleaned = re.sub(r"\bTGC\s+om\s*24\b", "TGCom24", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bUni\s+Credit\b", "UniCredit", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bTeam\s+System\b", "TeamSystem", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bBe\s+Beez\b", "BeBeez", cleaned, flags=re.IGNORECASE)

    # Collapse any double spaces introduced
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    return cleaned


# ---------------------------------------------------------------------------
# clean_display_text — orchestrator calling the composable stages above
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8192)
def clean_display_text(text: str, is_title: bool = False) -> str:
    """Clean a signal text field for user-facing display.

    Applied uniformly to title, what_changed, enriched_summary, diff_summary.
    The is_title flag controls minor behavioral differences (newspaper-only
    clearing, label-repair threshold, title capitalization).

    Pipeline stages:
      1. Strip boilerplate — logos, labels, AUM, templates, read-more
      2. Normalize spacing and dates — punctuation, date prefixes/suffixes, currency
      3. Repair tokens — fragmented splits, newspaper attribution, name corrections
      4. Normalize casing — ALL CAPS, title case, person names
      5. Strip datelines and navigation — press release headers, breadcrumbs
      6. Capitalize proper nouns — geographic names
      7. Split fused words — camelCase, acronym boundaries, brand reassembly
    """
    if not text:
        return text

    # For non-title fields, clear text that is just a newspaper name
    if not is_title and NEWSPAPER_ONLY_RE.match(text):
        return ""

    # Monitor-generated portfolio titles: match against original text to preserve
    # casing, then return directly (bypasses casing normalization steps).
    _raw = text.strip()
    _exited_m = re.match(
        r"^(.+?)\s+exited\s+from\s+(.+?)\s+portfolio(?:\s*\(.*?\))?\s*$",
        _raw, flags=re.IGNORECASE,
    )
    if _exited_m:
        return f"{_exited_m.group(2).strip()} exits {_exited_m.group(1).strip()}"
    _added_m = re.match(
        r"^(.+?)\s+added to\s+(.+?)\s+portfolio(?:\s*\(.*?\))?\s*$",
        _raw, flags=re.IGNORECASE,
    )
    if _added_m:
        return f"{_added_m.group(2).strip()}: new investment in {_added_m.group(1).strip()}"
    _added_it_m = re.match(
        r"^(.+?)\s+aggiunt[oa]\s+al?\s+portafoglio\s+(.+)$",
        _raw, flags=re.IGNORECASE,
    )
    if _added_it_m:
        return f"{_added_it_m.group(2).strip()}: nuovo investimento in {_added_it_m.group(1).strip()}"

    cleaned = _cdt_strip_boilerplate(text, is_title)
    cleaned = _cdt_normalize_spacing_and_dates(cleaned)
    cleaned = _cdt_repair_tokens_and_attributes(cleaned, is_title)
    cleaned = _cdt_normalize_casing(cleaned, is_title)
    cleaned = _cdt_strip_datelines_and_navigation(cleaned)
    cleaned = _cdt_capitalize_proper_nouns(cleaned)
    cleaned = _cdt_split_fused_words(cleaned)
    cleaned = re.sub(r"\bS\.?\s*P\.?\s*A\.?\b", "S.p.A.", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bS\.?\s*R\.?\s*L\.?\b", "S.r.l.", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(S\.p\.A\.|S\.r\.l\.)\.+(?=\s|[,;:)\]]|$)", r"\1", cleaned)

    # Ensure title starts with uppercase (fix scraper artifacts)
    if is_title and cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Cap excessively long titles (press release paragraph intros)
    if is_title and len(cleaned) > 160:
        cut = cleaned[:157]
        last_space = cut.rfind(" ")
        if last_space > 80:
            cleaned = cut[:last_space].rstrip(".,;:—–-") + "…"

    return cleaned.strip()


# ---------------------------------------------------------------------------
# is_garbage_summary — detect summaries that should be cleared
# ---------------------------------------------------------------------------

def is_garbage_summary(summary: str) -> bool:
    """Detect enriched_summary values that are garbage and should be cleared.

    Called by enrich_signals_openai.py after LLM generates a summary.
    When True, the enricher clears enriched_summary="" so the frontend
    falls back to the title. This prevents displaying nonsense to users.

    Patterns caught:
    - Contains pipe characters (navigation artifacts)
    - Just a proper noun with no verb (bare company/fund/newspaper name)
    - Starts lowercase (LLM formatting error)
    - Raw press release lede cut off mid-sentence
    - Boilerplate template with no specifics
    """
    if not summary or not summary.strip():
        return True

    text = summary.strip()

    # Contains pipe characters (navigation boilerplate)
    if "|" in text:
        return True

    # Placeholder summaries (scraper artifacts)
    if text.lower() in ("historical", "n/a", "none", "no data", "no summary"):
        return True

    # Very short — likely bare name with no context
    if len(text) < MIN_SUMMARY_LEN:
        return True

    # Starts with lowercase (LLM error — proper summaries start capitalized)
    if text[0].islower():
        return True

    # Boilerplate "New X involving Y" template (scraping artifact)
    if re.match(r"^New\s+(?:investment|announcement|fundraise|deal|exit)\s+involving\s+", text, re.IGNORECASE):
        return True

    # Brand name mistranslation artifacts (e.g., "Harmony" for "Armònia")
    # and LLM hallucination: "integers" used as verb instead of "acquires"
    if re.search(r"\bintegers?\b", text):
        return True

    # Fused-word detection: all-lowercase run-on tokens (≥20 chars with no spaces)
    # E.g. "appointedClaudiaPingueasheadoffondotechnologytransfer"
    # These are scraper/LLM artifacts that look extremely unprofessional
    _longest_token = max((len(w) for w in text.split()), default=0)
    if _longest_token >= MAX_SUMMARY_TOKEN_LEN:
        return True

    # Italian-language summary detection: if summary contains multiple Italian stop words
    # or content words, it's untranslated and should be cleared.
    # List includes both stop words (prepositions, articles) and content words (verbs,
    # nouns) that are uniquely Italian and won't appear in English text.
    _italian_stops = len(re.findall(
        r"\b(?:della|nella|degli|alle|sono|anche|questo|quella|stato|dopo|prima|verso|ogni|essere|avere|fatto|anno|"
        r"presentata?|girata?|"
        # Italian verbs (3rd person present, gerunds, past participles) not in English:
        r"acquista|acquisto|acquistano|investendo|controllata?|controllato|"
        r"tratta|trattano|maggioranza|venduta?|ceduta?|ceduto|"
        r"punta\s+su[ll]?|punta\s+a|lancia|nasce|avvia|"
        # Italian preposition contractions (uniquely Italian):
        r"sull[aei]?'|dell[aei]?'|nell[aei']|"
        # Italian financial terms left untranslated:
        r"partecipazione|operazione|finanziamento|raccolta|aumento\s+di\s+capitale)\b",
        text, re.IGNORECASE
    ))
    if _italian_stops >= ITALIAN_STOP_WORD_THRESHOLD:
        return True

    # No verb — just a noun phrase (bare company/fund name)
    # Check for at least one common English verb form
    has_verb = bool(re.search(
        r"\b(?:is|are|was|were|has|have|had|will|would|could|should|may|might"
        r"|acquir\w*|invest\w*|announc\w*|complet\w*|launch\w*|rais\w*|clos\w*"
        r"|appoint\w*|join\w*|sign\w*|enter\w*|exit\w*|sell\w*|sold|bought"
        r"|expand\w*|open\w*|secur\w*|report\w*|form\w*|partner\w*|back\w*"
        r"|fund\w*|lead\w*|manag\w*|reach\w*|plan\w*|target\w*|seek\w*"
        r"|negoti\w*|bid\w*|offer\w*|receiv\w*|win\w*|won|lost|creat\w*"
        r"|publish\w*|refinanc\w*|provid\w*|support\w*|build\w*|develop\w*"
        r"|consolidat\w*|strengthen\w*|present\w*|shift\w*|transition\w*"
        r"|convened?|hired?|named?|elect\w*|promot\w*|resign\w*|retir\w*)\b",
        text, re.IGNORECASE
    ))
    if not has_verb and len(text) < NO_VERB_MAX_LEN:
        return True

    return False


# ---------------------------------------------------------------------------
# capitalize_entities — restore proper-noun capitalization using NER data
# ---------------------------------------------------------------------------

def capitalize_entities(text: str, entity_names: list[str] | None) -> str:
    """Re-capitalize known entity names (companies, people, funds) in text.

    After sentence-case normalization, proper nouns like "audiotonix" or
    "burger king" may be lowercased. This function restores their correct
    capitalization using the extracted_entities list as ground truth.

    Preserves all-caps tokens (acronyms like KKR, EQT, CVC) — if the text
    already has the entity in all-caps and the replacement would downcase it,
    skip that match.
    """
    if not text or not entity_names:
        return text
    result = text
    ordered_names: list[str] = []
    seen_names: set[str] = set()
    for raw in entity_names:
        name = (raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        ordered_names.append(name)
    # Replace longer phrases first ("Mindful Capital Partners" before "Mindful Capital")
    ordered_names.sort(key=len, reverse=True)

    for name in ordered_names:
        if not name or len(name) < 2:
            continue
        # Build case-insensitive pattern for this entity name with token boundaries
        pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"

        def _preserve_acronyms(m: re.Match) -> str:
            matched = m.group(0)
            # If the matched text is already all-uppercase (2+ chars), it's a
            # correct acronym — don't replace with a title-cased version
            if len(matched) >= 2 and matched.isupper() and not name.isupper():
                return matched
            # Never downgrade an already-capitalized phrase to an all-lowercase
            # entity name coming from extracted_entities.
            if matched != matched.lower() and name == name.lower():
                return matched
            # If the matched text already equals the replacement, skip
            if matched == name:
                return matched
            return name

        result = re.sub(pattern, _preserve_acronyms, result, flags=re.IGNORECASE)
    return result


_COMPANY_SUFFIX_TOKENS = {
    "capital", "partners", "partner", "ventures", "venture", "equity", "group",
    "holdings", "holding", "management", "advisors", "advisor", "dynamics",
    "investments", "investment", "fund", "sgr", "spa", "srl", "ag", "sa", "inc", "ltd",
}


def extract_company_like_entities(*texts: str) -> list[str]:
    """Extract title-cased company/fund phrases from reference text.

    Used to restore capitalization in summaries when NER misses co-investor names.
    """
    entities: list[str] = []
    seen: set[str] = set()

    phrase_re = re.compile(
        r"\b(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+|[A-Z]{2,6})"
        r"(?:\s+(?:[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.\-]+|[A-Z]{2,6}|S\.p\.A\.|S\.r\.l\.)){1,5}\b"
    )

    for text in texts:
        if not text or not isinstance(text, str):
            continue
        for m in phrase_re.finditer(text):
            phrase = m.group(0).strip(" ,.;:()[]{}")
            phrase = re.sub(r"\s{2,}", " ", phrase)
            if len(phrase) < 4:
                continue
            tokens = [tok.strip(" ,.;:()[]{}").strip(".") for tok in phrase.split()]
            if len(tokens) < 2:
                continue
            token_l = [tok.lower() for tok in tokens if tok]
            if not token_l:
                continue
            if token_l[0] in _SENTENCE_CASE_LOWERCASE:
                continue
            if not any(tok in _COMPANY_SUFFIX_TOKENS for tok in token_l):
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            entities.append(phrase)
    return entities
