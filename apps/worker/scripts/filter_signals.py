#!/usr/bin/env python3
"""
Multi-gate signal quality filter for Fundradar.

Pipeline: garbage detection → dedup (composite key + semantic overlap) →
misattribution detection → geo-relevance gate (3-tier: italy_focused /
europe_wide / mixed_or_global) → quality scoring → reclassification.

Defense-in-depth with signalProcessing.ts (TypeScript safety net).

Usage:
    python apps/worker/scripts/filter_signals.py
"""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fundradar_worker.entity_resolver import normalize_company_name
from fundradar_worker.io_utils import safe_json_write, load_funds_by_slug as _load_funds_by_slug_shared
from fundradar_worker.slug_normalizer import get_slug_normalizer
from fundradar_worker.url_utils import extract_domain, is_same_domain

try:
    from fundradar_worker.signal_classifier import get_signal_classifier, map_type_to_signal_type
except Exception:
    get_signal_classifier = None
    map_type_to_signal_type = None

from signal_patterns import (
    BULK_TEAM_EXTRACTION_THRESHOLD,
    CORE_GEO_TYPES,
    CORE_QUALITY_TYPES,
    GENERIC_PORTFOLIO_NAME_TOKENS,
    GENERIC_PORTFOLIO_TARGET_PATTERNS,
    PORTFOLIO_DELTA_EVIDENCE_PATTERNS,
    PORTFOLIO_EXTRACTION_PATTERNS,
    _RE_ACCELERATOR_LAUNCH,
    _RE_ACCELERATOR_RESULTS,
    _RE_ACQUISITION_VERBS,
    _RE_BOARD_APPOINT as _RE_BOARD_APPOINTMENT,
    _RE_BOND_EXCLUDE,
    _RE_BOND_ISSUANCE,
    _RE_CHIUDE_FONDO,
    _RE_CHIUDE_RACCOLTA,
    _RE_CLOSE_VERBS as _RE_ROUND_CLOSED,
    _RE_COMPANY_ROUND,
    _RE_CREDIT_FACILITY,
    _RE_DEBT_FINANCING_BROAD,
    _RE_DEBT_RESTRUCTURE_CONTEXT,
    _RE_DEBT_RESTRUCTURING,
    _RE_EDITORIAL_STRATEGY,
    _RE_EVENT_ATTENDANCE,
    _RE_EVENT_INSIGHTS,
    _RE_EVENT_RECAP_ITALIAN,
    _RE_EVENT_TITLE,
    _RE_EXIT_VERBS,
    _RE_EXITED_FROM_PORTFOLIO,
    _RE_EXPLICIT_SELLER,
    _RE_FINALIZZAT,
    _RE_FUND_LAUNCH_STRICT,
    _RE_FUND_LAUNCH_VERBS,
    _RE_FUND_LEVEL_FUNDRAISE,
    _RE_FUNDRAISE_ACQUISITION,
    _RE_FUNDRAISE_CLOSED_VERBS,
    _RE_FUNDRAISE_CLOSING,
    _RE_FUNDRAISE_MILESTONE,
    _RE_FUNDRAISE_VERBS_FULL,
    _RE_HAS_ANY_PE_VERB,
    _RE_INTERNSHIP,
    _RE_INTERVIEW,
    _RE_INVEST_VERBS,
    _RE_INVESTOR_MEETING,
    _RE_JOB_POSTING_RECLASSIFY,
    _RE_JOINS_EVENT,
    _RE_JOB_SELECTION as _RE_JOB_POSTING_SHORT,
    _RE_LP_COMMITMENT,
    _RE_MERGER,
    _RE_OFFER_BID,
    _RE_OFFICE_OPENING,
    _RE_ORDINAL_INVESTMENT,
    _RE_OUTSOURCING,
    _RE_PARTNERSHIP,
    _RE_PARTNERSHIP_EXCLUDE,
    _RE_PEOPLE_TITLE,
    _RE_PORTFOLIO_CO_AS_ACQUIRER,
    _RE_PORTFOLIO_UPDATE,
    _RE_PROJECT_FINANCING,
    _RE_RACCOGLIE_EXCLUDE,
    _RE_RACCOGLIE_ROUND,
    _RE_REGULATORY_COMMUNICATION,
    _RE_REPORT,
    _RE_RESEARCH,
    _RE_REVENUE_PERFORMANCE,
    _RE_ROUND_INVEST as _RE_STARTUP_ROUND,
    _RE_STRONG_EXIT_VERBS,
    _RE_VALUE_CREATION,
    _extract_portfolio_company_name,
    _is_generic_portfolio_name,
    _strip_read_time,
    _strip_urls,
)

from signal_corrections import (
    apply_universal_demotions,
    apply_type_corrections,
    detect_all_signal_types,
)
from signal_text_utils import (
    capitalize_entities,
    clean_display_text,
    extract_company_like_entities,
    fix_spacing,
    normalize_monetary_values,
    repair_attached_connectors,
)

# Paths (shared)
from fundradar_worker.paths import PROJECT_ROOT, DATA_DIR, DB_PATH as DB_FILE, SIGNALS_FILE as INPUT_FILE, FILTERED_SIGNALS_FILE as OUTPUT_FILE

# Minimum quality score to keep (0-100)
MIN_QUALITY_SCORE = int(os.environ.get("SIGNAL_MIN_QUALITY", "80"))
# Allow exceptional signals to bypass strict gates if their quality is very high
STRICT_GATE_OVERRIDE_SCORE = int(os.environ.get("STRICT_GATE_OVERRIDE_SCORE", "90"))
ML_OVERRIDE_THRESHOLD = float(os.environ.get("SIGNAL_ML_OVERRIDE_THRESHOLD", "0.8"))
ML_USE_KEEP = os.environ.get("SIGNAL_ML_USE_KEEP", "0").strip().lower() in {"1", "true", "yes"}

# Garbage patterns to filter out completely
GARBAGE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"vai al menu",
        r"vai al contenuto",
        r"skip to",
        r"pagina successiva",
        r"pagina precedente",
        r"download pdf",
        r"read more",
        r"approfondisci$",
        r"^leggi",
        r"cookie",
        r"privacy policy",
        r"terms of use",
        r"©\s*\d{4}",
        r"all rights reserved",
        r"^menu$",
        r"^home$",
        r"^contatti?$",
        r"^contact$",
        r"footer",
        r"header",
        r"navigation",
        r"sidebar",
        r"website update",
        r"changes detected",
        r"\bpremio\b",
        r"\baward\b",
        r"news list update",
        # Award-style titles with no deal content: "Best Spanish LBO Fund", "Best PE House"
        r"^best\s+[\w\s]{1,35}\s+(?:fund|lbo|pe|vc)\b",
        # HAT SICAF / HAT SGR extractor artifact
        r"\bfeatured news press review\b",
        # LinkedIn newsletter navigation artifacts: "Title | Deals com Person Name"
        r"\|\s*deals?\s+com\s+\w",
        # Generic team page copy — no event content
        r"^the\s+management\s+team\s+is\s+composed\s+of\s+professionals",
        # Board financial-results approval signals — not PE/VC intelligence
        r"^(?:the\s+)?board\s+of\s+directors?\s+(?:approves?|examines?)\s+(?:the\s+)?(?:net\s+)?financial\s+(?:position|statements?|results?)",
    ]
]

# High-value keywords (increase score) — pre-compiled
HIGH_VALUE_KEYWORDS = [
    (re.compile(p, re.IGNORECASE), score) for p, score in [
        (r"acquis\w+", 20),           # acquisition / acquires
        (r"invest\w+ in", 20),        # investment in
        (r"completa", 15),            # Italian: completes (no English equivalent in list)
        (r"chiude", 15),              # Italian: closes — used in debt/portfolio contexts beyond "closing"
        (r"concordat\w+", 12),        # Italian legal procedure — untranslatable, no English equivalent
        (r"omologa", 10),             # Italian: court approval — no English equivalent
        (r"restructur\w+", 12),       # restructuring
        (r"€\s*\d+", 15),             # Money amount
        (r"\d+\s*(milion|mln|m€)", 15),  # Millions
        (r"operazione", 15),          # Italian: operation/deal — no standard English equivalent
        (r"fund\s*(i|ii|iii|iv|v|\d+)", 15),  # Fund numbering
        (r"(?:lancia|lancio|nasce)\s+un?\s+fondo", 12),  # Italian fund launch — untranslatable phrasing
        (r"portfolio company", 15),
        (r"\bexit\b", 15),
        (r"ipo", 20),
        (r"fundrais\w+", 15),
        (r"\bround\b", 12),
        (r"\bseries\s+[a-e]\b", 12),
        (r"\bseed\b|\bpre[-\s]?seed\b", 10),
        (r"\bfinal\s+close\b|\bfirst\s+close\b|\bclosing\b", 12),
        (r"\baumento di capitale\b", 12),  # Italian: capital increase — often left untranslated
        (r"\bfinanziamento\b", 12),        # Italian: financing — survives partial translation
        (r"\binvestimento\b", 12),         # Italian: investment noun — survives in mixed text
        (r"new partner", 15),
        (r"appoints?", 15),
        (r"join(s|ed)?", 10),
        (r"press release", 10),
    ]
]

# Low-value patterns (decrease score) — pre-compiled
LOW_VALUE_PATTERNS = [
    (re.compile(p, re.IGNORECASE), score) for p, score in [
        (r"content was removed", -20),
        (r"some content was", -15),
        (r"sections? removed", -20),
        (r"minor update", -25),
        (r"no significant", -30),
        (r"general update", -20),
        (r"updated their (home)?page", -15),
        (r"website update.*home.?page", -25),
        (r"website update.*team.?list", -20),
        (r"website update", -10),
        (r"changes detected", -10),
        (r"although spec\w+ details", -15),
        (r"likely indicating", -10),
        (r"^historical:", -20),           # Historical prefix without deal specifics
        (r"historical.*partnership", -25),
        (r"historical.*operazioni", -25),
        (r"generic.*page.*update", -20),
        (r"\bour companies\b", -25),
        (r"\bour portfolio\b", -25),
        (r"\bportfolio companies\b", -25),
        (r"\bback to top\b", -30),
        (r"\bchi siamo\b", -25),
        (r"\bgovernance\b", -20),
        (r"\buploads?\b", -20),
        (r"\bmemorandum of understanding\b", -12),
        (r"\bmou\b", -8),
        (r"\bframework\s+agreement\b", -8),
        (r"\bpress\s+coverage\b", -12),
        (r"\bin the press\b", -12),
        # Portfolio company operational articles (not PE/VC activity)
        (r"\b(?:solution|technology|platinum|gold|silver)\s+partner\b", -25),
        (r"\bhow\s+\w+\s+is\s+(?:scaling|growing|expanding|transforming)\b", -25),
        (r"\b(?:atlassian|microsoft|salesforce|oracle|sap|aws|azure)\s+(?:partner|solution|marketplace)\b", -25),
        (r"\bscaling\s+across\s+(?:europe|the\s+world|global)\b", -20),
        (r"\bmarketplace\s+vendor\b", -20),
    ]
]

# Generic site scaffolding patterns (drop if no deal/people signal)
SITE_SCAFFOLD_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\babout us\b",
        r"\bchi siamo\b",
        r"\bgovernance\b",
        r"\bcorporate governance\b",
        r"\bour (?:companies|portfolio|portfolio companies|activities)\b",
        r"\bportfolio companies\b",
        r"\bback to top\b",
        r"\bsite map\b",
        r"\bsitemap\b",
        r"\buploads?\b",
        r"\bdownloads?\b",
        r"\bnewsletter\b",
        r"\bsubscribe\b",
        r"\bfollow us\b",
    ]
]

# Portfolio list noise patterns (drop if no deal/people evidence)
PORTFOLIO_LIST_NOISE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bpartecipata\b",
        r"\bportfolio\b",
        r"\bportafoglio\b",
        r"\bour companies\b",
        r"\bcurrent portfolio\b",
        r"\bportfolio companies\b",
        r"\binvestimenti\s+portfolio\b",
    ]
]


# PORTFOLIO_EXTRACTION_PATTERNS — imported from signal_patterns
# PORTFOLIO_DELTA_EVIDENCE_PATTERNS — imported from signal_patterns


# Sector-only portfolio listings (usually static list noise)
SECTOR_ONLY_LISTING_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bin\s+[a-z0-9 &/\-]+ sector\b",
        r"\bin\s+[a-z0-9 &/\-]+ industry\b",
        r"\bnel settore\b",
        r"\bsettore\b",
        r"\bprivate debt\b",
        r"\bbusiness services\b",
        r"\bconsumer\b",
        r"\bhealthcare\b",
        r"\btechnology\b",
        r"\bindustrial\b",
    ]
]

# Portfolio URL hints (list pages)
PORTFOLIO_URL_HINTS = [
    "/portfolio",
    "/investments",
    "/investimenti",
    "/funds",
    "/fondi",
    "/companies",
    "/our-companies",
    "/partecipazioni",
    "/progetti",
]

# URLs that indicate misclassified portfolio items (about/team pages)
PORTFOLIO_MISPLACED_URL_HINTS = [
    "/about",
    "/about-us",
    "/team",
    "/management",
    "/people",
]

# Team extraction noise (bulk lists)
TEAM_EXTRACTION_RE = re.compile(r"(\d+)\s+new team members via extraction", re.IGNORECASE)
# BULK_TEAM_EXTRACTION_THRESHOLD — imported from signal_patterns
SMALL_TEAM_EXTRACTION_THRESHOLD = 5
MID_TEAM_EXTRACTION_THRESHOLD = 20
TEAM_EXTRACTION_ALLOW_THRESHOLD = 20
TEAM_EXTRACTION_ONLY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"via extraction",
    ]
]

# Static role/profile titles misclassified as people moves.
# These are not personnel transitions unless explicit move verbs are present.
TEAM_ROLE_PROFILE_TITLE_RE = re.compile(
    r"^[a-zà-öø-ÿ][a-zà-öø-ÿ'’.\-]+(?:\s+[a-zà-öø-ÿ][a-zà-öø-ÿ'’.\-]+){1,3}\s+"
    r"(?:(?:managing|senior|junior|lead|principal|chief)\s+)?"
    r"(?:head|director|manager|partner|officer|counsel|analyst|associate|specialist"
    r"|investor\s+relations"
    r"|legal\s*(?:&|and)\s*corporate\s+affairs(?:\s+(?:specialist|manager|head|director))?)\b",
    re.IGNORECASE,
)
ROLE_OPENING_TITLE_RE = re.compile(
    r"^\s*(?:senior|junior|lead|principal|chief|head|managing)?\s*"
    r"(?:investment\s+)?(?:associate|analyst|manager|specialist|advisor|officer|counsel|director)\b",
    re.IGNORECASE,
)
TEAM_STATIC_CORP_DESC_RE = re.compile(
    r"\b(?:is|acts?\s+as)\s+the\s+(?:parent|holding)\s+company\b"
    r"|\b(?:parent|holding)\s+company\s+of\b"
    r"|\bsociet[aà]\s+capogruppo\b",
    re.IGNORECASE,
)
PEOPLE_TRANSITION_VERBS_RE = re.compile(
    r"\b(?:appoint\w+|nomin\w+|joins?|joined|hired?|promot\w+"
    r"|named?\s+as|new\s+(?:hire|appointment)"
    r"|steps?\s+down|stepping\s+down|leaves?|left|resign\w*|depart\w*"
    r"|dimission\w*|lascia|lasciat\w+|abbandona)\b",
    re.IGNORECASE,
)

# CORE_GEO_TYPES — imported from signal_patterns
# CORE_QUALITY_TYPES — imported from signal_patterns

# Low-value announcements (reports, awards, events, interviews)
LOW_VALUE_ANNOUNCEMENT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\byear in review\b",
        r"\bcredit check\b",
        r"\bmarket update\b",
        r"\binsight[s]?\b",
        r"\binterview\b",
        r"\bpodcast\b",
        r"\bwebinar\b",
        r"\bconference\b",
        r"\bsummit\b",
        r"\bevent\b",
        r"\bawards?\b",
        r"\bbest .* fund\b",
        r"\bnewsletter\b",
        r"\bwhite paper\b",
        r"\bpress review\b",
        r"\bin the press\b",
        r"\bpress coverage\b",
        r"\bmission committee report\b",
    ]
]

# GENERIC_PORTFOLIO_TARGET_PATTERNS — imported from signal_patterns

# Generic portfolio headings (non-company items)
GENERIC_PORTFOLIO_TITLES = {
    "investments",
    "investment",
    "portfolio",
    "portafoglio",
    "our portfolio",
    "current portfolio",
    "prior investments",
    "our companies",
    "soluzioni di investimento",
    "strategie d’investimento",
    "strategie di investimento",
    "strategia di investimento",
    "strategia d’investimento",
}

# GENERIC_PORTFOLIO_NAME_TOKENS — imported from signal_patterns

# Deal/people hints to avoid dropping real signals when scaffold words appear
DEAL_OR_PEOPLE_HINTS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bacquis\w+\b",
        r"\binvest\w+\b",
        r"\bexit\b",
        r"\bmerg\w+\b",
        r"\btransaction\b",
        r"\bdeal\b",
        r"\bipo\b",
        r"\bquotazion\w+\b",
        r"\bfundrais\w+\b",
        r"\bcloses?\b",
        r"\bclosing\b",
        r"\bround\b",
        r"\bseries\b",
        r"\baumento di capitale\b",
        r"\bfinanziamento\b",
        r"\binvestimento\b",
        r"\bristrutturazion\w+\b",
        r"\bconcordat\w+\b",
        r"\bomologa\b",
        r"\brestructur\w+\b",
        r"\baccordo di ristrutturazione\b",
        r"\bentra nel capitale\b",
        r"\bentra in\b",
        r"\brileva\b",
        r"\bacquisizione\b",
        r"\bappoint\w+\b",
        r"\bjoins?\b",
        r"\bhired?\b",
        r"\bpromot\w+\b",
        r"\bnomin(?:a|at\w+)\b",  # nomina (present), nominato/a (past participle)
        r"\bpartner\b",
        r"\bceo\b",
        r"\bcfo\b",
        r"\bcoo\b",
        r"\bcio\b",
        r"\b(?:lancia|lancio|nasce|launch(?:es|ed)?|new)\b.*\b(?:fondo|fund)\b",
        r"\bfund\s+(?:i|ii|iii|iv|v|vi|vii|viii|\d+)\b",
        r"\bfondo\s+(?:i|ii|iii|iv|v|vi|vii|viii|\d+)\b",
        # Additional deal hints
        r"\bcarve[\-\s]?out\b",
        r"\bjoint\s+venture\b",
        r"\bm&a\b",
        r"\btakeover\b",
        r"\bbuyout\b",
        r"\blbo\b",
        r"\boperazione\b",
        r"\bvendita\b",
        r"\bdivest\w+\b",
        r"\bcessione\b",
        r"\badd-on\b",
        r"\bbolt[\-\s]?on\b",
        r"\boversubscribed\b",
        r"\bcapital\s+raise\b",
        # Additional people hints
        r"\bnamed\b",
        r"\bnew\s+hire\b",
        r"\bnuovo\s+ingresso\b",
    ]
]

DEAL_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bacquir\w*\b",      # acquire, acquires, acquiring, acquired
        r"\bacquisition\w*\b", # acquisition, acquisitions
        r"\bacquis\w+\b",      # Italian: acquisisce, acquisita, acquisizione
        r"\binvest(?:s|ed|ing|ment)?\s+(?:in|nel)\b",  # invests in, invested in, investing in
        r"\binvest\w+\s+(?:in|nel|nella|nei|nelle|nell[''])\b", # Italian conjugations
        r"\binvest\w+\b.{0,40}\b(?:in|nel|nella|nei|nelle|nell[''])\b", # allow short span between verb and preposition
        r"\bentra nel capitale\b",
        r"\bentra in\b",
        r"\brileva\b",
        r"\bcompra\b",
        r"\bstake\b",
        r"\bmajority\b",
        r"\bminority\b",
        r"\bbuyout\b",
        r"\blbo\b",
        r"\bportfolio company\b",
        r"\bnew investment\b",
        r"\bristrutturazion\w+\b",
        r"\bconcordat\w+\b",
        r"\bomologa\b",
        r"\brestructur\w+\b",
        r"\baccordo di ristrutturazione\b",
        r"\bmerg(?:er|e|ed|ing|ers)\b",  # merger, merge, merged, merging
        r"\bfusion[ei]\b",              # Italian: fusione/fusioni (merger/mergers)
        r"\bincorporazion\w+\b",        # Italian: incorporazione (merger by incorporation)
        r"\bcarve[\-\s]?out\b",
        r"\bjoint\s+venture\b",
        r"\bm&a\b",
        r"\btransaction\b",
        r"\btakeover\b",
        r"\bquotazion\w+\b",    # Italian: quotazione (IPO/listing)
        r"\bipo\b",
        r"\blisting\b",
        r"\boperazione\b",      # Italian: operation/deal
        r"\brilevazione\b",     # Italian: takeover
        r"\bpartecipazione\b",  # Italian: equity stake
        r"\bingresso\b.*\b(?:capital|societ|azionari)\b",  # Italian: entry into capital/company
        r"\bnuovo investimento\b",  # Italian: new investment
        r"\bseries\s+[a-g]\b",    # Series A/B/C/D/E/F/G round
        r"\b(?:seed|pre-seed)\s+(?:round|funding)\b",
        r"\bfunding\s+round\b",
        r"\bround\s+(?:di\s+)?(?:finanziamento|investimento)\b",  # Italian: funding round
        r"\b(?:€|\$|£)\s*\d+\s*(?:m(?:illion|ln)?|b(?:illion|n)?)\s+(?:round|investment|funding)\b",
        r"\b(?:primo|secondo|terz[oa]|quart[oa]|quint[oa]|sest[oa]|settim[oa]|ottav[oa]|non[oa]|decim[oa]|\d+[°ºª]?)\s+investiment[oi]\b",  # Italian: ordinal investment
        r"\bportfolio addition\b",
        r"\badd-on\b",
        r"\bbolt[\-\s]?on\b",
        r"\binvestiment[oi]\s+da\s",  # Italian: "investimento da [amount]" = specific deal
        r"\binveste\b",            # Italian: invests (verb, no preposition needed)
        r"\binvestono\b",          # Italian: they invest (plural)
        r"\b\d+\s*(?:milion\w*|mln)\b.*\binvestiment[oi]\b",  # Amount + investimento/i
        r"\benters?\b.*\bcapital\b",  # English: enters capital / enters share capital
        r"\bclosing\b.*\b(?:facility|loan|credit|lending)\b",  # Debt deal closings
        r"\baccordo\b.*\b(?:milion\w*|mln|€|eur)\b",  # Italian: agreement with amount = deal
        r"\baffianca\b",           # Italian: supports/backs (in PE context = co-invest)
        r"\bsottoscri\w+\b.*\baccordo\b",  # Italian: "sottoscrive un accordo" (signs a deal)
        r"\bfinalizzat\w+\b",             # Italian: finalizzata/finalizzato (completed/finalized deal)
        r"\bconcessi\w+\b",               # concession/concessione (infrastructure deals)
        r"\bsostiene\b",                  # Italian: supports (in PE = backs/invests in)
        r"\bsecures?\s+(?:€|\$|£)?\s*\d+",  # English: "secures €21.5M" = funding/deal
        r"\bsecur(?:es?|ing)\b.{0,40}\b(?:investment|funding|financing)\b",
        r"\binvestitore\s+unic\w*\s+al\s+fianco\s+di\b",  # Italian: sole investor backing
        r"\bsole\s+investor\s+(?:backing|alongside)\b",
        r"\binvest\s+(?:€|\$|£|over\s+|circa\s+)?[\d.,]+\s*[MBmb]\w*\b",  # invest 260M, invest €5.1M
        r"\b[\d.,]+\s*[Mm]\w*\s+investment\w*\b",  # 20.5M investment from...
    ]
]

PARTNERSHIP_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bpartnership\b",                 # English: partnership
        r"\bpartners?\s+(?:with|to\s+deliver)\b",  # "partners with X", "partner to deliver"
        r"\bjoint\s+venture\b",             # joint venture
        r"\bjv\b",                          # JV abbreviation
        r"\bdistribution\s+agreement\b",    # distribution agreement
        r"\bstrategic\s+alliance\b",        # strategic alliance
        r"\bcollaborazione\s+strategica\b", # Italian: strategic collaboration
        r"\baccordo\s+(?:di\s+)?(?:collaborazione|distribuzione|partnership)\b",  # Italian: agreement
        r"\balleanza\s+strategica\b",       # Italian: strategic alliance
        r"\bintesa\s+(?:strategica|commerciale)\b",  # Italian: strategic/commercial agreement
    ]
]

# Negative patterns: if any of these match, it's a deal, NOT a partnership
PARTNERSHIP_EXCLUDE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bacqui\w+\b",
        r"\brileva\b",
        r"\bbuyout\b",
        r"\bmajority\b",
        r"\bminority\s+stake\b",
        r"\bentra\s+nel\s+capitale\b",
    ]
]

EXIT_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bexit\b",
        r"\bdivest\w+\b",
        r"\bsells?\b",
        r"\bselling\b",          # English: selling (present participle)
        r"\bsold\b",
        r"\bsale\b",
        r"\bcessione\b",
        r"\bcede\b",
        r"\bcedut[oa]\b",        # Italian: ceduto/ceduta (transferred/sold)
        r"\bdismissione\b",
        r"\brealisat(?:ion|ions)\b",
        r"\brealizat(?:ion|ions)\b",
        r"\brealis(?:ed|ing)\b",
        r"\brealiz(?:ed|ing)\b",
        r"\bdispos(?:al|ed|ing)\b",
        r"\bvendita\b",          # Italian: sale
        r"\bvend(?:e|ere|ono)\b", # Italian: sells/to sell/they sell
        r"\bvendut[oa]\b",       # Italian: sold (past participle)
        r"\ba\s+vendere\b",      # Italian: "a vendere è ..." (selling is ...)
        r"\buscita\b",           # Italian: exit
        r"\bdismette\b",         # Italian: divests
        r"\bdismettono\b",       # Italian: they divest (plural)
        r"\bdismission[ei]\b",   # Italian: divestiture(s)
        r"\bcessato\b",          # Italian: ceased/terminated
        r"\bwrite[\-\s]?off\b",
        r"\btrade\s+sale\b",
        r"\bsecondary\s+(?:sale|buyout)\b",
    ]
]

FUNDRAISE_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bfundrais\w+\b",
        r"\bfirst close\b",
        r"\bfinal close\b",
        r"\bhard cap\b",
        r"\braccolta\b",
        r"\bround\b",
        r"\bseries\b",
        r"\bseed\b",
        r"\bpre[-\s]?seed\b",
        r"\bbridge\b",
        r"\bfinancing\b",
        r"\bfinanziamento\b",
        r"\baumento di capitale\b",
        r"\bcommitments?\s+(?:of|di|from)\b",  # More specific commitment patterns
        r"\btarget size\b",
        r"\braises?\b",  # raises, raised
        r"\braised\s+\d",  # raised 100M, raised €50m
        r"\bcapital\s+raise\b",
        r"\bcapital\s+raising\b",
        r"\bcommitted\s+capital\b",
        r"\boversubscribed\b",
        r"\bchiusura\b",           # Italian: closing
        r"\bchiude\b",            # Italian: closes (verb)
        r"\bsottoscrizione\b",    # Italian: subscription
        r"\bimpegni?\b.*\b(?:milion\w*|mln|€)\b",  # Italian: commitments + amount
        r"\bprimo closing\b",     # Italian: first close
        r"\bfirst\s+closing\b",   # English: first closing (variant of first close)
        r"\b(?:additional|interim)\s+closing\b",  # Additional/interim close
        r"\b(?:secondo|terzo|second|third|final|successful)\s+clos(?:e|ing)\b",  # Subsequent/final closes
        r"\bclosing\b.*\b(?:million|mln|milion\w*|€|eur)\b",  # Closing with amount
        r"\braccog\w+\b",         # Italian: raccoglie, raccogliere (to raise/collect)
        r"\barriva\s+a\b.*\b(?:milion\w*|mln|€|eur|miliard\w*)\b",  # Italian: "arriva a [amount]" = reaches target size
        r"\bsupera\b.*\b(?:milion\w*|mln|€|eur|miliard\w*)\b",  # Italian: "supera [amount]" = exceeds target
        r"\b(?:revolving\s+)?credit\s+facilit(?:y|ies)\b",  # RCF / credit facility (upsizing, extending)
        r"\bupsize[sd]?\b",  # upsizes, upsized (increasing facility size)
        # LP/subscription language for existing funds
        r"\b(?:new|additional)\s+contributions?\s+to\s+(?:the\s+)?(?:[a-z0-9&'’\-]+\s+){0,6}(?:fund|fondo)\b",
        r"\b(?:nuov[oi]|ulteriori)\s+contribut\w+\s+(?:al|nel)\s+(?:[a-z0-9&'’\-]+\s+){0,6}(?:fondo|fund)\b",
    ]
]

FUND_LAUNCH_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        # NOTE: accelerat* and polo REMOVED — accelerators/programs are NOT fund launches
        # Use bounded .{0,80} instead of .* to prevent false matches across sentences
        # e.g. "launches partnership ... News: Fondo" or "New announcement: ... nel fondo"
        # "avvia" = starts/initiates (Italian), "al via" = is underway
        r"\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b.{0,80}\b(?:fondo|fund|comparto|veicolo|vehicle)\b",
        r"\bfund\s+(?:i|ii|iii|iv|v|vi|vii|viii|\d+)\b",
        r"\bfondo\s+(?:i|ii|iii|iv|v|vi|vii|viii|\d+)\b",
        r"\bnew\s+fund\b",
        r"\bnuovo\s+fondo\b",     # Italian: new fund
        r"\bfund\s+formation\b",
        r"\bvehicle\s+launch\b",
        r"\bfund\s+(?:launch|inception|creation)\b",
        r"\bcomparto\b.{0,50}\b(?:operativo|attivo|avviato)\b",  # "comparto operativo" = new fund compartment
        # NOTE: NO fund-first pattern (e.g. "fondo.{0,50}launches") — too many false positives
        # from fund names containing "Fondo" (e.g. "Fondo Italiano d'Investimento launches partnership")
    ]
]

# Accelerator/program launch detection → other (fund's strategic initiative, NOT a fund vehicle)
# If there's actual collaboration language, PARTNERSHIP_CLASSIFY_PATTERNS catches it first
ACCELERATOR_LAUNCH_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b"
        r".*\b(?:accelerator(?:e)?|incubator(?:e)?|polo|programma|program|hub)\b",
        r"\b(?:accelerator(?:e)?|incubator(?:e)?|polo|programma|program|hub)\b"
        r".*\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b",
    ]
]

PEOPLE_CLASSIFY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bappoint\w+\b",
        r"\bappointed\b",
        r"\bjoins?\b",
        r"\bjoined\b",
        r"\bnomin(?:a|e|at\w+)\b",  # nomina (present), nomine (plural), nominato/a (past participle)
        r"\bnew partner\b",
        r"\bnew ceo\b",
        r"\bnew cfo\b",
        r"\bnew coo\b",
        r"\bnew cio\b",
        r"\bboard\b",
        r"\bmanaging director\b",
        r"\bpartner\b",
        r"\bceo\b",
        r"\bcfo\b",
        r"\bcoo\b",
        r"\bcio\b",
        r"\bpromot\w+\b",        # promoted, promotion
        r"\bhired?\b",
        r"\bnamed?\s+(?:as\s+)?(?:ceo|cfo|coo|cio|partner|director|head|president|chairman)\b",
        r"\bnames\b.*\b(?:as\s+)?(?:incoming\s+)?(?:head|chief|officer|partner|director|managing|president|chairman)\b",
        r"\bnew\s+(?:hire|hiring|appointment|team\s+member|head|director|managing\s+director|president|chairman)\b",
        r"\bstrengthens?\b.*\bteam\b",
        r"\bassume\s+(?:il\s+)?(?:ruolo|incarico)\b",  # Italian: takes on role
        r"\b(?:resign\w*|dimission\w*|dimette|si\s+dimette|lascia\s+(?:il\s+)?(?:ruolo|incarico|carica))\b",  # Resignations/departures
        r"\b(?:steps?\s+down|leaves?|left|depart\w*|succeed\w*|successor|successore)\b",  # Leadership transitions
        r"\bnuov[oa]\s+(?:ceo|cfo|coo|cio|direttore|amministratore|presidente)\b",  # Italian: new C-suite
        r"\bentra\s+(?:nel\s+)?(?:team|consiglio|cda)\b",  # Italian: joins team/board
        r"\bnuovo\s+(?:ingresso|membro)\b",  # Italian: new entry/member
    ]
]

JOB_POSTING_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bwe (?:are|re) hiring\b",
        r"\bjob\s+description\b",
        r"\bopen\s+position\b",
        r"\bvacancy\b",
        r"\bcareer\s+(?:opportunit|opening|role)\b",
        r"\bapply\s+(?:now|here|today)\b",
        r"\bresponsibilities\b",
        r"\bqualifications?\b",
        r"\brequirements?\b",
        # Italian job posting patterns
        r"\bprocedura\s+di\s+selezione\b",    # selection procedure
        r"\bricerca\s+(?:una?\s+)?risors[ae]\b",  # seeking a resource
        r"\bavvia\s+(?:la\s+)?selezione\b",    # starts selection
        r"\bselezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)\b",  # selection for role
        r"\bricerca\s+(?:una?\s+)?(?:figura|profilo)\b",  # seeking a figure/profile
        r"\btempo\s+(?:pieno|indeterminato|determinato)\b",  # full-time/permanent/fixed-term
    ]
]

INTERNSHIP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\bintern(ship)?\b",
        r"\btrainee\b",
        r"\bstagiaire\b",
        r"\bstage\b(?!\s+(?:of|investment|fund|deal|growth|early|late|seed))",
        r"\bstagista\b",
        r"\btirocin\w+\b",
        r"\bapprentice(ship)?\b",
        r"\bgraduate\s+program\b",
    ]
]

# Career page job posting indicators (used in _is_job_posting_signal)
_CAREERS_JOB_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bwe are seeking\b',
        r'\bwe.re looking\b',
        r'\bjob\s+description\b',
        r'\bresponsibilities\b',
        r'\bqualifications?\b',
        r'\brequirements?\b',
        r'\bapply\s+(now|here|today)\b',
        r'\bcandidates?\s+(should|must|will)\b',
        r'\bsalary\b',
        r'\bcompensation\b',
        r'\bjoin\s+our\s+team\b',
        r'\bcareer\s+(?:update|opportunit)',
        r'\bopen\s+position\b',
        r'\bvacancy\b',
        r'\bsmooth\s+operation\b',
        r'\bfacilities\s+manage',
    ]
]


def _is_low_value_job_posting(text: str) -> bool:
    """Drop support/admin/intern job postings."""
    if not text:
        return False
    text_lower = text.lower()
    if _is_support_role(text):
        return True
    if _matches_any(INTERNSHIP_PATTERNS, text_lower):
        return True
    return False


def _has_deal_or_people_hints(text: str) -> bool:
    return any(p.search(text) for p in DEAL_OR_PEOPLE_HINTS)


def _matches_any(patterns: list[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def _is_sector_only_listing_text(text_lower: str) -> bool:
    return any(p.search(text_lower) for p in SECTOR_ONLY_LISTING_PATTERNS)


def _is_portfolio_extraction_only(signal: dict, text: str) -> bool:
    """Detect portfolio items that are just static list extraction (not true events)."""
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "PORTFOLIO":
        return False
    diff_summary = (signal.get("diff_summary") or "").lower()
    if not any(p.search(diff_summary) for p in PORTFOLIO_EXTRACTION_PATTERNS):
        return False
    summary = signal.get("enriched_summary") or signal.get("what_changed") or ""
    title = signal.get("title") or ""
    text_full = f"{title} {summary}".lower()
    # Keep if it looks like a real portfolio addition (company + evidence)
    if _looks_like_portfolio_delta(signal, text_full, summary, title):
        return False
    # Otherwise treat as extraction-only list noise
    return True


def _is_portfolio_list_item(signal: dict, text: str, summary: str, title: str) -> bool:
    """Detect low-value portfolio list items without clear deal evidence."""
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "PORTFOLIO":
        return False
    # Explicit "New investment/exit" labels with a real company name are useful signals
    explicit_new = re.match(r"^new\s+(?:portfolio\s+)?(?:investment|exit):\s*(.+)$", title or "", re.IGNORECASE)
    if explicit_new:
        candidate = explicit_new.group(1).strip()
        if candidate and not _is_generic_portfolio_name(candidate):
            return False
    if (title or "").lower().strip() in GENERIC_PORTFOLIO_TITLES:
        return True
    if _looks_like_portfolio_delta(signal, text, summary, title):
        return False
    company_name = _extract_portfolio_company_name(signal, summary, title)
    if company_name and _is_generic_portfolio_name(company_name):
        return True
    source_url = (signal.get("source_url") or "").lower()
    if any(hint in source_url for hint in PORTFOLIO_MISPLACED_URL_HINTS):
        if _has_amount(text) or any(p.search(text) for p in PORTFOLIO_DELTA_EVIDENCE_PATTERNS):
            return False
        if _has_strong_deal_evidence(text):
            return False
        return True
    text_lower = (text or "").lower()
    if _is_sector_only_listing_text(text_lower) and not (_has_deal_or_people_hints(text_lower) or _has_amount(text_lower)):
        return True
    if _has_deal_or_people_hints(text_lower) or _has_amount(text_lower):
        return False
    if signal.get("published_at") or signal.get("enriched_date"):
        return False
    what_changed = (signal.get("what_changed") or "").lower()
    if _has_deal_or_people_hints(what_changed) or _has_amount(what_changed):
        return False
    source_url = (signal.get("source_url") or "").lower()
    if any(hint in source_url for hint in PORTFOLIO_URL_HINTS):
        return True
    if len((title or "").split()) <= 4:
        return True
    if len((summary or "").split()) <= 6 and len((summary or "")) < 60:
        return True
    return False


def _looks_like_portfolio_delta(signal: dict, text: str, summary: str, title: str) -> bool:
    """Keep only true portfolio additions/exits (not static list dumps)."""
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "PORTFOLIO":
        return False
    diff_summary = (signal.get("diff_summary") or "").lower()
    if not any(p.search(diff_summary) for p in PORTFOLIO_EXTRACTION_PATTERNS):
        return False
    company_name = _extract_portfolio_company_name(signal, summary, title)
    source_url = (signal.get("source_url") or "").lower()

    # Explicit "New investment/exit" label with a real company name is enough
    explicit_new = re.match(r"^new\s+(?:portfolio\s+)?(?:investment|exit):\s*(.+)$", title or "", re.IGNORECASE)
    if explicit_new:
        candidate = explicit_new.group(1).strip()
        if candidate and not _is_generic_portfolio_name(candidate):
            return True

    if any(hint in source_url for hint in PORTFOLIO_MISPLACED_URL_HINTS):
        if _has_amount(text) or any(p.search(text) for p in PORTFOLIO_DELTA_EVIDENCE_PATTERNS):
            return True
        if _has_strong_deal_evidence(text) and company_name and not _is_generic_portfolio_name(company_name):
            return True
        return False
    # Evidence: amounts, investment dates, or a clear company entity
    if _has_amount(text):
        return True
    if any(p.search(text) for p in PORTFOLIO_DELTA_EVIDENCE_PATTERNS):
        return True
    return False


def _is_bulk_team_extraction(signal: dict, text: str) -> bool:
    """Detect large team list extractions that are likely static roster dumps."""
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "TEAM":
        return False
    diff_summary = signal.get("diff_summary") or ""
    match = TEAM_EXTRACTION_RE.search(diff_summary)
    if not match:
        return False
    try:
        count = int(match.group(1))
    except ValueError:
        return False
    if count < BULK_TEAM_EXTRACTION_THRESHOLD:
        return False
    # Keep if explicit appointment language appears
    if _RE_PEOPLE_TITLE.search(text):
        return False
    return True


def _is_team_extraction_only(signal: dict) -> bool:
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "TEAM":
        return False
    diff_summary = (signal.get("diff_summary") or "").lower()
    if not any(p.search(diff_summary) for p in TEAM_EXTRACTION_ONLY_PATTERNS):
        return False
    match = TEAM_EXTRACTION_RE.search(diff_summary)
    count = int(match.group(1)) if match else None
    text = f"{signal.get('title','')} {signal.get('what_changed','')}".strip()
    # Keep small to mid team deltas if we can see real names or senior roles
    if count is not None and count <= TEAM_EXTRACTION_ALLOW_THRESHOLD:
        if (
            _is_senior_title(text)
            or _has_named_people(text)
            or _RE_PEOPLE_TITLE.search(text)
        ):
            return False
        entities = signal.get("extracted_entities") or {}
        if entities.get("people"):
            return False
    # If count is unknown but we have strong people evidence, keep it
    if count is None:
        if _is_senior_title(text) or _has_named_people(text):
            return False
    return True


def _reclassify_signal_type(signal: dict, text: str, fund: dict | None = None) -> str:
    """Reclassify generic signals into more useful categories."""
    current = signal.get("signal_type") or ""
    if current in {"news", "announcement", "press_release", "press"}:
        current = "other"
    if current not in {
        "fundraise_announced",
        "fundraise_closed",
        "fundraise",
        "fund_launch",
        "deal_announced",
        "exit_announced",
        "debt_financing",
        "portfolio_update",
        "report",
        "people_move",
        "job_posting",
        "partnership",
        "website_change",
        "other",
        "",
    }:
        current = "other"
    page_category = (signal.get("page_category") or "").upper()
    text_lower = text.lower()
    title_lower = (signal.get("title") or "").lower()

    if page_category == "CAREERS":
        if _matches_any(JOB_POSTING_PATTERNS, text_lower) or _is_careers_job_posting(signal):
            return "job_posting"

    # Detect job postings from NEWS pages with hiring language
    if page_category == "NEWS" and _matches_any(JOB_POSTING_PATTERNS, text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
            return "job_posting"

    # Strong exit verbs override all other checks — "Fund cede X" is ALWAYS an exit
    # But don't override if text also contains deal acquisition verbs (to avoid
    # "A acquires B from C" being wrongly classified as exit)
    if _RE_STRONG_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
        return "exit_announced"

    # Event/conference attendance → demote to 'other' (low value, not investment signal)
    if _RE_EVENT_ATTENDANCE.search(text_lower):
        return "other"

    # Pure event/conference title signals (no deal content) → other
    # Matches titles that are just event names: "M&A Congress 2026", "PE Forum Milano"
    if _RE_EVENT_TITLE.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
        return "other"

    # "Joins forum/conference" → other (event attendance, not investment)
    if _RE_JOINS_EVENT.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
        return "other"

    # Investor/LP meetings → other (not a deal, fundraise, or any transaction)
    if _RE_INVESTOR_MEETING.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
            return "other"

    # Interview/editorial without PE transaction verbs → other
    # Catches founder interviews, CEO profiles, magazine articles with no deal content
    if _RE_INTERVIEW.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower) and not _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
            return "other"

    # Event insights/recaps → other (e.g. "Insights from Blackstone's CEO Conference")
    # Must come before deal/people hint checks since these often contain "CEO", "investment" etc.
    if _RE_EVENT_INSIGHTS.search(text_lower) or _RE_EVENT_RECAP_ITALIAN.search(text_lower):
        return "other"

    # Marketing/thought-leadership pieces → other (e.g. "Sustainability as a value creation driver")
    # Unconditional — "value creation driver" is marketing framing, never in real deal titles
    if _RE_VALUE_CREATION.search(text_lower):
        return "other"

    # Internship/stage offers → job_posting (regardless of current type)
    if _RE_INTERNSHIP.search(text_lower):
        return "job_posting"

    # Investor meetings / AGMs → other (not deals)
    if _RE_INVESTOR_MEETING.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
        return "other"

    # Pure editorial "investment strategy" / "investment approach" content → other
    # Allow demotion even when deal patterns match, if there's no monetary amount
    # (catches "Investire in Innovazione" which matches deal pattern "investire in" but has no amount)
    if _RE_EDITORIAL_STRATEGY.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) or not _has_amount(text_lower):
            return "other"

    # Financial results/annual report/sustainability report → report
    # Must run BEFORE revenue_performance check (which sends to "other")
    # But DON'T reclassify to report if the text has explicit fund launch/deal language
    if _RE_REPORT.search(text_lower):
        if not _RE_FUND_LAUNCH_VERBS.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
            return "report"

    # Portfolio company revenue/performance articles → other (not fund_launch or deal)
    # e.g. "hlpy raggiunge ricavi ricorrenti per circa 60 mln euro"
    if _RE_REVENUE_PERFORMANCE.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
            return "other"

    # Bond issuance / refinancing → debt_financing
    if _RE_BOND_ISSUANCE.search(text_lower):
        if not _RE_BOND_EXCLUDE.search(text_lower):
            return "debt_financing"

    # Revolving credit facility / corporate debt facility → debt_financing
    if _RE_CREDIT_FACILITY.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
            return "debt_financing"

    # Broader debt financing: bank loans, private debt, securitization → debt_financing
    if _RE_DEBT_FINANCING_BROAD.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
            return "debt_financing"

    # Regulatory/internal dealing communications → other
    if _RE_REGULATORY_COMMUNICATION.search(text_lower):
        return "other"

    # Research/publication/whitepaper → other (not deal or fundraise)
    if _RE_RESEARCH.search(text_lower):
        if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
            return "other"

    if current in {"deal_announced", "exit_announced", "fundraise_announced", "fundraise_closed", "fund_launch", "people_move"}:
        # exit_announced with acquisition verbs (no exit verbs) → fund is acquiring, not exiting
        # e.g. "Permira acquires 40% of K-Way" should be deal, not exit
        if current == "exit_announced":
            # Job posting misclassified as exit (e.g. "procedura di selezione per responsabile")
            if _RE_JOB_POSTING_RECLASSIFY.search(text_lower):
                return "job_posting"
            # Partnership/agreement signals → partnership (not exit)
            # e.g. "waste-to-energy plants, agreement between Region and Invitalia"
            if re.search(r"\b(?:agreement|accordo|intesa|convenzione)\b", text_lower) and not _RE_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
                if re.search(r"\b(?:partnership|collaborazione|gestione|manage|management|tenders?|bando)\b", text_lower):
                    return "partnership"
            # Buyer-perspective signals → deal_announced (fund is BUYING, not selling)
            # "in lizza" (bidding/competing), "potrebbe essere interessat" (might be interested)
            buyer_cues = r"\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b|\bpotrebbero\s+essere\s+interessat\w*\b|\bvaluta\s+l[''\u2019]acqui\w+\b"
            has_explicit_seller = bool(_RE_EXPLICIT_SELLER.search(text_lower) or _RE_EXITED_FROM_PORTFOLIO.search(text_lower))
            if re.search(buyer_cues, title_lower):
                if not has_explicit_seller:
                    return "deal_announced"
            if re.search(buyer_cues, text_lower):
                if not _RE_EXIT_VERBS.search(text_lower):
                    return "deal_announced"
            # "offerta da X mln per" / "offer for" = acquisition bid → deal
            if _RE_OFFER_BID.search(text_lower):
                if not _RE_EXIT_VERBS.search(text_lower):
                    return "deal_announced"
            if _RE_ACQUISITION_VERBS.search(text_lower):
                if not _RE_EXIT_VERBS.search(text_lower):
                    return "deal_announced"
            # "exited from portfolio" → keep as exit
            if _RE_EXITED_FROM_PORTFOLIO.search(text_lower):
                pass  # confirmed exit
            # "launch/lancia fund" explicitly on an exit is clearly wrong → fund_launch
            elif _RE_FUND_LAUNCH_VERBS.search(text_lower):
                return "fund_launch"
            # Safety net: exit_announced with ZERO PE-related verbs is likely misclassified
            # Real exits always mention selling, exiting, or at minimum deal-related language
            elif page_category != "PORTFOLIO" and not _RE_HAS_ANY_PE_VERB.search(text_lower):
                return "other"

        # deal_announced with "portfolio company" subject → portfolio_update
        # e.g. "CDP VC portfolio company Vite Sicure closes a €2M bridge round"
        if current == "deal_announced":
            if re.search(r"\bportfolio\s+compan(?:y|ies)\b", text_lower):
                return "portfolio_update"

        # deal_announced false positives
        if current == "deal_announced":
            # "exited from portfolio" / "uscita dal portafoglio" → exit, not deal
            if _RE_EXITED_FROM_PORTFOLIO.search(text_lower):
                return "exit_announced"
            # Explicit seller indicators → exit even when acquisition verbs also present
            # e.g. "Chequers rileva GIF. A vendere è Alcedo SGR e FVS SGR"
            if _RE_EXPLICIT_SELLER.search(text_lower):
                return "exit_announced"
            # Strong exit verbs in deal signal → exit (e.g. "Permira exits Golden Goose",
            # "Successful Realisation Of Investment", "sale of its stake")
            if _RE_STRONG_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
                if not (re.search(r"\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b|\bpotrebbero\s+essere\s+interessat\w*\b|\bvaluta\s+l[''\u2019]acqui\w+\b", title_lower) and not _RE_EXPLICIT_SELLER.search(text_lower)):
                    return "exit_announced"
            # Outsourcing/procurement → other (not a deal)
            if _RE_OUTSOURCING.search(text_lower):
                return "other"
            # Internship offer → job_posting (not deal)
            if _RE_INTERNSHIP.search(text_lower):
                return "job_posting"
            # Job posting language → job_posting
            if _RE_JOB_POSTING_SHORT.search(text_lower):
                return "job_posting"
            # "Strengthens team" / "senior appointments" → people_move
            if re.search(r"\bstrengthens?\b.*\bteam\b|\bsenior\s+appointments?\b|\bseries\s+of\s+(?:senior\s+)?appointments?\b", text_lower):
                if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                    return "people_move"
            # Partnership signals misclassified as deal
            # "accordo di collaborazione", "enters network", "coalition launched"
            if _matches_any(PARTNERSHIP_CLASSIFY_PATTERNS, text_lower):
                if not _matches_any(PARTNERSHIP_EXCLUDE_PATTERNS, text_lower):
                    return "partnership"
            # Fund itself being acquired by another entity → other (corporate M&A of the PE firm)
            # e.g. "Capza Is Thrilled To Announce Its Full Acquisition By Axa Im Alts"
            if re.search(r"\b(?:acquisition|acquisizione)\s+(?:by|da\s+parte\s+di)\b", text_lower):
                return "other"
            # Concordato/restructuring of portfolio company → other
            if _RE_DEBT_RESTRUCTURING.search(text_lower):
                if _RE_DEBT_RESTRUCTURE_CONTEXT.search(text_lower) and _mentions_tagged_fund(signal, text_lower):
                    return "debt_financing"
                if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) or re.search(r"\bconcordato\b", text_lower):
                    return "other"
            # Government concession award → other (not a PE equity deal)
            if re.search(r"\b(?:concession[ei]?|concession\s+(?:for|per|del|della))\b|\baggiudicazion[ei]\b|\bconcessione\s+(?:per|del|della|di)\b", text_lower):
                if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                    return "other"
            # Bond/debt financing misclassified as deal
            if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
                return "debt_financing"
            if _RE_CREDIT_FACILITY.search(text_lower):
                return "debt_financing"
            if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
                return "debt_financing"
            if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
                return "debt_financing"
            # Fundraise closing misclassified as deal: "closing del fondo" / "closing of oversubscribed"
            if re.search(r"\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|oversubscribed)\b", text_lower):
                return "fundraise_closed"

        # "[Other entity] acquires [target] from [fund]" → exit (fund is selling)
        # e.g. "TPG to Acquire Sabre Industries from Blackstone" on blackstone.com
        # Also catches signals typed as 'other' (e.g. "Calzedonia acquisisce X (portafoglio Y)")
        if current in {"deal_announced", "other"}:
            fund_name = (signal.get("source_name") or "").lower().strip()
            if not fund_name:
                fund_name = (signal.get("fund_slug") or "").replace("-", " ")
            if fund_name and len(fund_name) >= 3 and re.search(
                r"\b(?:acquir\w+|buy\w*|purchas\w+)\b.{0,80}\bfrom\s+" + re.escape(fund_name) + r"\b",
                text_lower,
            ):
                return "exit_announced"
            # Fund's own website posts "Other Entity acquires/completed acquisition of X":
            # From the fund's perspective, this is an exit (they're the seller).
            # The fund name must NOT be the subject of the acquisition verb.
            source_url = (signal.get("source_url") or "").lower()
            if fund_name and source_url and fund:
                fund_website = (fund.get("website") or "").lower()
                if fund_website and is_same_domain(fund_website, source_url):
                        # Signal is from the fund's own domain
                        if re.search(r"^[A-Za-z][\w\s]{2,30}\b(?:has\s+completed|completes?|acquir\w+)\b", (signal.get("title") or ""), re.IGNORECASE):
                            first_entity = re.match(r"^([A-Za-z][\w\s]{2,30}?)\s+(?:has\s+completed|completes?|acquir)", (signal.get("title") or ""), re.IGNORECASE)
                            if first_entity:
                                acquirer_name = first_entity.group(1).lower().strip()
                                if fund_name not in acquirer_name:
                                    return "exit_announced"

        # fund_launch false positives: "Xth investimento per Fund N" or "nuovo investimento per il fondo" → deal
        if current == "fund_launch":
            # Fund-level raise language takes priority over debt patterns for debt funds.
            if _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                if _RE_FUNDRAISE_CLOSING.search(text_lower) or _RE_CHIUDE_FONDO.search(text_lower):
                    return "fundraise_closed"
                return "fundraise_announced"
            # Bond issuance / refinancing → debt_financing (not a fund launch)
            if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "debt_financing"
            # Credit facility → debt_financing
            if _RE_CREDIT_FACILITY.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "debt_financing"
            # Accelerator/program launch → other (strategic initiative, not a fund vehicle)
            # Only reclassify if it's NOT also a genuine fund launch (e.g. "lancia fondo + acceleratore")
            if _matches_any(ACCELERATOR_LAUNCH_PATTERNS, text_lower) and not _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower):
                return "other"
            # Accelerator batch results / graduates → other (not a fund launch)
            # e.g. "5 startup selezionate dall'acceleratore", "risultati del programma di accelerazione"
            if _RE_ACCELERATOR_RESULTS.search(text_lower) and not _RE_FUND_LAUNCH_VERBS.search(text_lower):
                return "other"
            # Outsourcing/procurement notices → other (not a deal or fund launch)
            if _RE_OUTSOURCING.search(text_lower):
                return "other"
            # Job posting language → job_posting (not fund launch)
            if _RE_JOB_POSTING_SHORT.search(text_lower):
                return "job_posting"
            # Ordinal investment for existing fund → deal (not fund launch)
            if _RE_ORDINAL_INVESTMENT.search(text_lower):
                return "deal_announced"
            # Board/appointment language → people_move (not fund launch)
            if _RE_BOARD_APPOINTMENT.search(text_lower):
                if not _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower):
                    return "people_move"
            # Office opening / footprint expansion → people_move
            if _RE_OFFICE_OPENING.search(text_lower):
                if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                    return "people_move"
            # "offerta da X mln" = acquisition bid → deal
            if _RE_OFFER_BID.search(text_lower):
                return "deal_announced"
            # "sottoscritto project financing" / "finanziamento da X" = debt_financing
            if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "debt_financing"
            # "accordo tra creditori" / debt restructuring → other
            if _RE_DEBT_RESTRUCTURING.search(text_lower):
                if _RE_DEBT_RESTRUCTURE_CONTEXT.search(text_lower) and _mentions_tagged_fund(signal, text_lower):
                    return "debt_financing"
                if not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                    return "other"
            # "surpasses X in raised capital" / "supera X di raccolta" → fundraise
            if _RE_FUNDRAISE_MILESTONE.search(text_lower):
                return "fundraise_closed"
            # LP committing to existing fund → fundraise (not fund_launch)
            # e.g. "Enpaia Gestione Separata e Fon.Te nel fondo Linfa"
            if _RE_LP_COMMITMENT.search(text_lower):
                return "fundraise_announced"
            # Regulatory/internal dealing → other
            if _RE_REGULATORY_COMMUNICATION.search(text_lower):
                return "other"
            # "prende il controllo" / "acquisisce" → deal (not fund_launch)
            if _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                return "deal_announced"
            if _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
                return "exit_announced"
            # Safety net: fund_launch with NO actual fund launch language → other
            # Catches ML putting "fund_launch" on editorial/think-piece content
            # e.g. "search fund as a model", "investire in innovazione"
            if not _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower):
                return "other"
        # fundraise_announced corrections: acquisition verbs → deal, closing verbs → fundraise_closed
        if current == "fundraise_announced":
            if _RE_FUNDRAISE_ACQUISITION.search(text_lower):
                return "deal_announced"
            if _RE_FUNDRAISE_CLOSING.search(text_lower):
                return "fundraise_closed"
            if _RE_FUNDRAISE_MILESTONE.search(text_lower):
                return "fundraise_closed"
            # "closing of oversubscribed fund" → fundraise_closed
            if re.search(r"\bclosing\s+of\s+(?:oversubscribed|the)\b", text_lower):
                return "fundraise_closed"
            # Portfolio company debt financing → debt_financing (not fund fundraise)
            # e.g. "Bianalisi strengthens capital structure with EUR 470M financing"
            if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "debt_financing"
            if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "debt_financing"
            if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
                return "debt_financing"
            # Thought leadership / editorial content → other
            if _RE_EDITORIAL_STRATEGY.search(text_lower):
                return "other"
            # Serialized editorial articles: "Part X of Y" → other (not a deal)
            if re.search(r"\bPart\s+\d+\s+of\s+\d+\b", text_lower, re.IGNORECASE):
                return "other"
            # "could be interested in" / "are rumored to be" = potential deal (not portfolio_update)
            if current == "portfolio_update" and re.search(r"\bcould\s+be\s+interest|are\s+rumor|potential\s+(?:acquir|buyer)", text_lower):
                return "deal_announced"
            # Financial results → report
            if _RE_REPORT.search(text_lower):
                return "report"
        # Portfolio company rounds: fundraise → deal_announced
        # When a fund's portfolio company raises a round, it's the fund's investment (not a fund-level fundraise)
        if current in {"fundraise_announced", "fundraise_closed"}:
            if _RE_COMPANY_ROUND.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
                return "deal_announced"
            # Other fund/SGR raising money on THIS fund's newsroom → deal_announced (LP investment)
            # e.g. "Sofinnova Partners raccoglie 165M" on CDP VC newsroom
            fund_slug = signal.get("fund_slug", "")
            fund_name_lower = (signal.get("fund_name") or fund_slug.replace("-", " ")).lower()
            title_lower_check = (signal.get("title") or "").lower()
            if re.search(r"\b(?:sgr|partners?|capital|ventures?)\b.*\b(?:raccog\w+|raises?|chiude|closing)\b", title_lower_check):
                # Title subject is a fund/SGR — check if it's THIS fund
                if fund_name_lower and fund_name_lower not in title_lower_check[:60]:
                    return "deal_announced"
        # "Chiude la raccolta a X" → fundraise_closed
        if current in {"fund_launch", "fundraise_announced", "deal_announced"}:
            if _RE_CHIUDE_RACCOLTA.search(text_lower):
                return "fundraise_closed"
        # deal_announced false positive: fundraise round → fundraise
        # BUT don't reclassify company-level rounds (startup raising money = deal from fund's perspective)
        if current == "deal_announced":
            if _RE_RACCOGLIE_ROUND.search(text_lower):
                if not _RE_RACCOGLIE_EXCLUDE.search(text_lower) and not _RE_COMPANY_ROUND.search(text_lower):
                    return "fundraise_announced"
        if current in {"fundraise_announced", "deal_announced", "other"}:
            if _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                if not _RE_FUNDRAISE_VERBS_FULL.search(text_lower):
                    return "fund_launch"
        if current == "people_move":
            # Advisory board formation (clinical, scientific, etc.) → other (not a hire/appointment)
            if re.search(r"\b(?:advisory\s+board|comitato\s+(?:scientifico|consultivo))\b", text_lower):
                if not re.search(r"\b(?:appoint\w+|nomin\w+|joins?|entra)\b", text_lower):
                    return "other"
            if _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
                return "exit_announced"
            has_team_strengthening = bool(re.search(r"\bstrengthens?\b.*\bteam\b|\bsenior\s+appointments?\b|\bseries\s+of\s+(?:senior\s+)?appointments?\b", text_lower))
            has_explicit_deal = bool(_RE_ACQUISITION_VERBS.search(text_lower) or _RE_INVEST_VERBS.search(text_lower) or _RE_OFFER_BID.search(text_lower) or _RE_COMPANY_ROUND.search(text_lower))
            if has_team_strengthening and not has_explicit_deal:
                return "people_move"
            if _RE_REPORT.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                return "report"
            if _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
                return "deal_announced"
            if _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
                if _RE_FUNDRAISE_CLOSED_VERBS.search(text_lower):
                    return "fundraise_closed"
                return "fundraise_announced"
            # Safety net: people_move with NO actual people-related language → other
            # Catches ML setting "people_move" on signals with no personnel content
            if not _matches_any(PEOPLE_CLASSIFY_PATTERNS, text_lower):
                return "other"
        # report corrections: some signals tagged as report are actually exits/deals/fund_launches
        if current == "report":
            # "completes the sale of its stake" → exit, not report
            if _RE_STRONG_EXIT_VERBS.search(text_lower) or _RE_EXPLICIT_SELLER.search(text_lower):
                return "exit_announced"
            # Accelerator/program launch → other (fund's strategic initiative, not fund_launch)
            if _matches_any(ACCELERATOR_LAUNCH_PATTERNS, text_lower):
                return "other"
            # "operativo il comparto" = fund compartment becomes operational → fund_launch
            if re.search(r"\boperativ[oa]\s+(?:il\s+)?comparto\b|\bcomparto\b.*\boperativ[oa]\b", text_lower):
                return "fund_launch"
            # "nasce fondo" / "lancia fund" → fund_launch (NOT accelerator — that's above)
            if _RE_FUND_LAUNCH_VERBS.search(text_lower) and _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower):
                return "fund_launch"
            # Event recap → other (not a report)
            if re.search(r"\b(?:partner\s+coinvolti|startup\s+accelerate|rete\s+nazionale)\b", text_lower):
                return "other"
            # Portfolio company profile/scaling article → other
            if re.search(r"\b(?:scaling|how\s+\w+\s+is\s+scaling|transforms?\s+\w+\s+with)\b", text_lower):
                if not _RE_REPORT.search(text_lower):
                    return "other"
            # "investe €3.5M in X" → deal, not report
            if _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _RE_REPORT.search(text_lower):
                return "deal_announced"
        return current

    # Demote portfolio list items that lack deal evidence
    if page_category == "PORTFOLIO":
        if _looks_like_portfolio_delta(signal, text_lower, signal.get("what_changed") or "", signal.get("title") or ""):
            if _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
                return "exit_announced"
            return "deal_announced"
        if not _has_deal_or_people_hints(text_lower) and not _has_amount(text_lower):
            return "other"

    # Exit signals (check first - most specific)
    if _matches_any(EXIT_CLASSIFY_PATTERNS, text_lower):
        return "exit_announced"

    # Partnership signals (check before deal — partnerships are NOT acquisitions)
    # Accelerator/program launches are NOT partnerships even if they have "partnership" language
    if _matches_any(PARTNERSHIP_CLASSIFY_PATTERNS, text_lower):
        if not _matches_any(PARTNERSHIP_EXCLUDE_PATTERNS, text_lower):
            if not _matches_any(ACCELERATOR_LAUNCH_PATTERNS, text_lower):
                return "partnership"

    # Debt financing signals (check before deal — debt is NOT equity)
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"
    if _RE_CREDIT_FACILITY.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
        return "debt_financing"
    if _RE_PROJECT_FINANCING.search(text_lower) and not _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"
    if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"

    # Deal signals (check before fundraise - "invests in X" is a deal, not a fundraise)
    if _matches_any(DEAL_CLASSIFY_PATTERNS, text_lower):
        return "deal_announced"

    # Accelerator/program launches → other (fund's strategic initiative, NOT fund_launch)
    if _matches_any(ACCELERATOR_LAUNCH_PATTERNS, text_lower):
        return "other"

    # Fund launch signals (new fund announcements — strictly fund vehicles, NOT accelerators)
    if _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_lower):
        if not _RE_FUNDRAISE_VERBS_FULL.search(text_lower):
            return "fund_launch"

    # Fundraise signals (require specific fundraise context)
    if _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, text_lower):
        # Company-level rounds (startup raising money) = deal from fund perspective
        if _RE_COMPANY_ROUND.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
            return "deal_announced"
        if _RE_FUNDRAISE_CLOSED_VERBS.search(text_lower) or _RE_FUNDRAISE_MILESTONE.search(text_lower):
            return "fundraise_closed"
        return "fundraise_announced"

    # People moves
    if _matches_any(PEOPLE_CLASSIFY_PATTERNS, text_lower) or page_category == "TEAM":
        return "people_move"

    return current or "other"

# Senior titles — always relevant regardless of geography
SENIOR_TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bpartner\b',
        r'\bmanaging\s+director\b',
        r'\bdirector\b',
        r'\bfounder\b',
        r'\bco[-\s]?founder\b',
        r'\bchair(man|woman|person)?\b',
        r'\bpresident\b',
        r'\bcfo\b', r'\bchief\s+financial\s+officer\b',
        r'\bceo\b', r'\bchief\s+executive\s+officer\b',
        r'\bcio\b', r'\bchief\s+invest\w+\s+officer\b',
        r'\bcoo\b', r'\bchief\s+operat\w+\s+officer\b',
        r'\bcto\b', r'\bchief\s+technol\w+\s+officer\b',
        r'\bhead\s+of\b',
        r'\bvice\s+president\b', r'\bvp\b',
        r'\bprincipal\b',
        r'\bgeneral\s+manager\b',
        r'\bgeneral\s+counsel\b',
        r'\bmanaging\s+partner\b',
        r'\bboard\b',
    ]
]

# Junior titles — only relevant if Italy-specific
JUNIOR_TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\banalyst\b',
        r'\bassociate\b',
        r'\bintern\b',
        r'\btrainee\b',
        r'\bstagiaire\b',
    ]
]

# Italian geography mentions — used to keep junior hires that are Italy-relevant
ITALY_MENTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bitaly\b', r'\bitalia\b', r'\bitalian[aeo]?\b',
        r'\bmilano?\b', r'\brome?\b', r'\broma\b', r'\btorino\b', r'\bturin\b',
        r'\bnapoli\b', r'\bnaples\b', r'\bbologna\b', r'\bfirenze\b', r'\bflorence\b',
        r'\bgenova\b', r'\bgenoa\b', r'\bvenezia\b', r'\bvenice\b', r'\bpalermo\b',
        r'\bpadova\b', r'\bverona\b', r'\btrieste\b', r'\bbari\b', r'\bbergamo\b',
        r'\bbrescia\b', r'\bmodena\b', r'\bparma\b', r'\bvicenza\b', r'\btreviso\b',
        r'\breggio\b', r'\bcatania\b', r'\bmessina\b', r'\bpavia\b', r'\bperugia\b',
        r'\bcagliari\b', r'\bsassari\b', r'\bpescara\b', r'\blecce\b', r'\bancona\b',
        # Italian company legal suffixes — require at least one dot to avoid matching wellness "spa"
        r'\bS\.p\.A\.?\b', r'\bS\.\s*p\.\s*A\b', r'\bS\.r\.l\.?\b', r'\bS\.\s*r\.\s*l\b',
        r'\bS\.a\.s\.?\b', r'\bS\.\s*a\.\s*s\b', r'\bS\.n\.c\.?\b', r'\bS\.\s*n\.\s*c\b',
    ]
]

# Europe geography mentions — used to keep signals that are Europe-relevant
EUROPE_KEYWORDS = [
    "europe", "european", "eu", "eurozone", "euro area", "emea",
    "benelux", "dach", "nordic", "nordics", "cee", "balkans",
]

EUROPE_COUNTRIES = [
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czech republic",
    "czechia", "denmark", "estonia", "finland", "france", "germany", "greece",
    "hungary", "ireland", "italy", "latvia", "lithuania", "luxembourg",
    "malta", "netherlands", "poland", "portugal", "romania", "slovakia",
    "slovenia", "spain", "sweden", "switzerland", "united kingdom", "uk",
    "england", "scotland", "wales", "northern ireland", "norway", "iceland",
    "liechtenstein", "monaco", "andorra", "san marino", "serbia",
]

EUROPE_CITIES = [
    "london", "paris", "berlin", "munich", "frankfurt", "zurich", "geneva",
    "madrid", "barcelona", "amsterdam", "rotterdam", "brussels", "vienna",
    "stockholm", "copenhagen", "oslo", "helsinki", "dublin", "warsaw",
    "prague", "lisbon", "porto", "athens", "milan", "rome", "milano", "roma",
]

_EUROPE_MENTION_RE = re.compile(
    r"(?i)\b(" +
    "|".join(re.escape(x) for x in (EUROPE_KEYWORDS + EUROPE_COUNTRIES + EUROPE_CITIES)) +
    r")\b"
)

# Geography scope heuristics based on fund geographies (AIFI/manual)
ITALIAN_REGIONS = [
    "lombardia", "lombardy", "veneto", "emilia-romagna", "emilia romagna",
    "piemonte", "piedmont", "toscana", "tuscany", "lazio", "campania",
    "puglia", "sicilia", "sicily", "sardegna", "sardinia", "liguria",
    "marche", "friuli-venezia giulia", "friuli venezia giulia", "abruzzo",
    "calabria", "umbria", "basilicata", "molise", "trentino-alto adige",
    "trentino alto adige", "valle d'aosta", "friuli", "veneto",
]

EUROPE_GEO_SET = {
    "europe", "italy", "france", "germany", "spain", "switzerland",
    "united kingdom", "uk", "benelux", "serbia",
    *ITALIAN_REGIONS,
}

NON_EU_GEO_SET = {
    "worldwide", "north america", "south america", "latin america", "usa",
    "canada", "asia", "asia pacific", "asia-pacific", "australia",
    "middle east", "brazil", "egypt", "morocco", "vietnam",
}

# Non-Italy EU countries/cities — used to prevent boost for clearly non-Italian deals
# from funds that technically have 'Italy' in geographies (e.g. CAPZA, Triton)
_NON_ITALY_EU_COUNTRIES_RE = re.compile(
    r"\b(?:France|French|Fran[cç]ais[e]?|Paris|Lyon|Marseille|"
    r"Germany|German|Deutschland|Berlin|Munich|Frankfurt|Bavaria|Bavarian|Hamburg|"
    r"Spain|Spanish|Madrid|Barcelona|"
    r"UK|United Kingdom|British|London|Manchester|"
    r"Netherlands|Dutch|Amsterdam|"
    r"Sweden|Swedish|Stockholm|"
    r"Denmark|Danish|Copenhagen|"
    r"Norway|Norwegian|Oslo|"
    r"Finland|Finnish|Helsinki|"
    r"Belgium|Belgian|Brussels|"
    r"Portugal|Portuguese|Lisbon|"
    r"Austria|Austrian|Vienna|"
    r"Ireland|Irish|Dublin)\b", re.IGNORECASE
)

NON_EU_TEXT_PATTERNS = [
    re.compile(r"\bUnited States\b", re.IGNORECASE),
    re.compile(r"\bU\.S\.A\.?\b", re.IGNORECASE),
    re.compile(r"\bU\.S\.\b", re.IGNORECASE),
    re.compile(r"\bUSA\b", re.IGNORECASE),
    re.compile(r"\bCanada\b", re.IGNORECASE),
    re.compile(r"\bChina\b", re.IGNORECASE),
    re.compile(r"\bIndia\b", re.IGNORECASE),
    re.compile(r"\bJapan\b", re.IGNORECASE),
    re.compile(r"\bSingapore\b", re.IGNORECASE),
    re.compile(r"\bAustralia\b", re.IGNORECASE),
    re.compile(r"\bNew Zealand\b", re.IGNORECASE),
    re.compile(r"\bBrazil\b", re.IGNORECASE),
    re.compile(r"\bMexico\b", re.IGNORECASE),
    re.compile(r"\bArgentina\b", re.IGNORECASE),
    re.compile(r"\bChile\b", re.IGNORECASE),
    re.compile(r"\bColombia\b", re.IGNORECASE),
    re.compile(r"\bPeru\b", re.IGNORECASE),
    re.compile(r"\bUnited Arab Emirates\b", re.IGNORECASE),
    re.compile(r"\bUAE\b", re.IGNORECASE),
    re.compile(r"\bSaudi Arabia\b", re.IGNORECASE),
    re.compile(r"\bQatar\b", re.IGNORECASE),
    re.compile(r"\bSouth Korea\b", re.IGNORECASE),
    re.compile(r"\bKorea\b", re.IGNORECASE),
]

# ── All regex patterns now imported from signal_patterns ──
# Shared patterns: _RE_INTERVIEW, _RE_REVENUE_PERFORMANCE, _RE_OFFER_BID,
# _RE_REGULATORY_COMMUNICATION, _RE_JOB_POSTING_RECLASSIFY, _RE_ACQUISITION_VERBS,
# _RE_INTERNSHIP, _RE_OFFICE_OPENING, _RE_FUNDRAISE_ACQUISITION, _RE_RACCOGLIE_ROUND,
# _RE_RACCOGLIE_EXCLUDE, _RE_FUNDRAISE_VERBS_FULL, _RE_FUNDRAISE_CLOSED_VERBS,
# _RE_DEBT_RESTRUCTURE_CONTEXT, _RE_EDITORIAL_STRATEGY, _RE_ACCELERATOR_RESULTS,
# _RE_FUND_LAUNCH_VERBS, _RE_STARTUP_ROUND (aliased from _RE_ROUND_INVEST),
# _RE_ROUND_CLOSED (aliased from _RE_CLOSE_VERBS)

# Filter-specific patterns (not in signal_patterns)
_RE_INVESTIMENTI_PORTFOLIO = re.compile(r"\binvestimenti\s+portfolio\b")
_RE_HAS_AMOUNT = re.compile(r"€\s*\d+(?:[.,]\d+)?|\$\s*\d+(?:[.,]\d+)?|\b\d+(\.\d+)?\s*(milion|million|mln|m€|bn|billion|miliardi|milioni)\b", re.IGNORECASE)
# Extracts the first compact currency amount from a text string for deal_amount backfill.
# Matches: €1.3B, $28M, €460M, €7M, £150M, €3B, €2.9B, $500M etc.
_RE_EXTRACT_AMOUNT = re.compile(
    r"[€$£]\s*\d+(?:[.,]\d+)?\s*(?:B|M|K|T|bn|mn|mln|mld)\b"
    r"|[€$£]\s*\d{1,3}(?:[.,]\d{3})+(?:\s*(?:B|M|K))?"
    r"|\b\d+(?:[.,]\d+)?\s*(?:billion|miliard[io]?|million|milion[ei]?|mln|mld)\s*(?:di\s+)?(?:euro[s]?|EUR|dollars?)?\b",
    re.IGNORECASE,
)
_RE_HAS_DEAL_KEYWORD = re.compile(r"\bacquis\w+|\binvest\w+|\bexit\b|\bipo\b|\bfundrais\w+|\bclosing\b|\bround\b|\bseries\b|\bmerg\w+|\bsell\b|\bsold\b|\bsale\b|\bdivest\w+|\baumento di capitale\b|\bfinanziamento\b|\bentra nel capitale\b|\bentra in\b|\brileva\b|\bristrutturazion\w+|\bconcordat\w+|\bomologa\b|\brestructur\w+|\baccordo di ristrutturazione\b|\bcarve[\-\s]?out\b|\bjoint\s+venture\b|\bm&a\b|\btakeover\b|\bbuyout\b|\blbo\b|\boperazione\b|\bvendita\b|\bcessione\b|\boversubscribed\b|\bcapital\s+raise\b|\bquotazion\w+\b|\badd-on\b|\bbolt[\-\s]?on\b", re.IGNORECASE)
_RE_STRONG_DEAL_EVIDENCE = re.compile(r"\bacquis\w+|\bcompra\b|\brileva\b|\bentra nel capitale\b|\bentra in\b|\binvest(?:s|ed|ing)?\s+(?:in|nel)\b|\binvest\w+\s+(?:in|nel|nella|nei|nelle|nell[''])\b|\binvest\w+\b.{0,40}\b(?:in|nel|nella|nei|nelle|nell[''])\b|\bround\b|\bseries\b|\bfinanziamento\b|\baumento di capitale\b|\bclosing\b|\bfundrais\w+\b|\bristrutturazion\w+|\bconcordat\w+|\bomologa\b|\brestructur\w+|\baccordo di ristrutturazione\b|\bmerg(?:er|e|ed|ing)\b|\bcarve[\-\s]?out\b|\bjoint\s+venture\b|\btakeover\b|\bbuyout\b|\blbo\b|\boversubscribed\b|\bsecur(?:es?|ing)\b.{0,40}\b(?:investment|funding|financing)\b|\binvestitore\s+unic\w*\s+al\s+fianco\s+di\b|\bsole\s+investor\s+(?:backing|alongside)\b", re.IGNORECASE)
_RE_COMPANY_LEGAL_SUFFIX = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:S\.?r\.?l\.?|S\.?p\.?A\.?|S\.?A\.?|SAS|SARL|Ltd|Inc|LLC|GmbH|AG|AB|BV|NV|SGR)")
_RE_WEBSITE_UPDATE_PAGE = re.compile(r"website update.*(?:home|team.?list)\s*page", re.IGNORECASE)
_RE_HISTORICAL_DEAL_KEYWORDS = re.compile(r"acquis|invest|exit|ipo|fundrais|chiude|completa|€|\d+\s*mil", re.IGNORECASE)
_RE_NAMED_PEOPLE = re.compile(r"\b[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+(?:\s+[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+){1,2}\b")

# MONTHS, MONTHS_PATTERN, DATE_*_RE, PRESS_RELEASE_PREFIX_RE, LEADING_LABEL_RE,
# FRAGMENTED_PHRASES, NEWSPAPER_ONLY_RE — now imported from signal_text_utils

# Maximum people in a single signal before we consider it a bulk team-page scrape
MAX_PEOPLE_PER_SIGNAL = 100

# Support/admin role titles - signals mentioning only these are not useful
# for PE/VC business intelligence
SUPPORT_ROLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\bassistant\b(?!.*\b(?:invest|portfolio|fund manager|vice president|vp)\b)',
        r'\bexecutive\s+assistant\b',
        r'\bteam\s+assistant\b',
        r'\bpersonal\s+assistant\b',
        r'\boffice\s+manager\b',
        r'\boffice\s+coordinator\b',
        r'\breceptionist\b',
        r'\bfront\s+desk\b',
        r'\bsecretar(?:y|ial)\b',
        r'\badministrat(?:ive|ion)\b(?!.*\b(?:partner|director|board|fund)\b)',
        r'\baccountant\b',
        r'\bbookkeeper\b',
        r'\b(?:it|system)\s+(?:support|admin|helpdesk|technician)\b',
        r'\bhuman\s+resources?\b(?!.*\bdirector\b)',
        r'\bhr\s+(?:coordinator|assistant|officer|specialist|admin)\b',
        r'\bfacilities\b',
        r'\bdriver\b',
        r'\bcleaning\b',
        r'\bmailroom\b',
        r'\bjunior\s+(?:financial\s+)?controller\b',
        r'\bsupport\s+staff\b',
        r'\boffice\s+&\s+events\b',
    ]
]


# External counterparty names not tracked in db.json but common in Italian PE news.
# These supplement the auto-generated list from db.json fund names.
_EXTERNAL_COUNTERPARTY_NAMES = [
    "tpg", "johnson & johnson", "j&j", "warburg", "cinven",
    "deep ocean", "p 101", "360 capital", "xenon", "mandarin",
    # Common external PE/VC firms not in db.json that appear in Italian deal flow
    "orienta capital partners", "orienta capital", "kharis capital",
    "sphere group", "bc partners", "montagu", "bridgepoint",
    "cerberus", "oaktree", "adia", "mubadala", "coller capital",
    "hamilton lane", "tikehau", "intermediate capital", "icg",
]

# Populated at startup by _build_known_fund_names() from db.json + external list.
KNOWN_FUND_NAMES: list[str] = []


def _build_known_fund_names(funds_by_slug: dict) -> list[str]:
    """Build misattribution detection list from db.json fund names + external counterparties."""
    names: set[str] = set()
    for fund in funds_by_slug.values():
        name = (fund.get("name") or "").strip().lower()
        if not name:
            continue
        names.add(name)
        # Add first word as brand shorthand (e.g. "Blackstone" from "Blackstone Group")
        words = name.split()
        if len(words) > 1 and len(words[0]) > 2:
            names.add(words[0])
    names.update(_EXTERNAL_COUNTERPARTY_NAMES)
    return sorted(names)


def _is_misattributed_signal(signal: dict, fund: dict | None = None) -> bool:
    """Detect signals where the title names a different fund than the one it's tagged to.

    Exception: signals from the fund's own website are never misattributed — if a fund
    posts about "X acquires Y" on their own newsroom, it means the fund is the seller (exit).
    """
    fund_slug = (signal.get("fund_slug") or "").strip()
    if not fund_slug:
        return False
    fund_name_lower = fund_slug.replace("-", " ").lower()
    title_lower = (signal.get("title") or "").lower().strip()
    if not title_lower:
        return False

    # Ecosystem newsroom check — applies to ALL signal sources (not just
    # fund-website-domain signals).  These funds' newsrooms cover the whole
    # market, so any signal attributed to them must explicitly mention the fund
    # name in the text.  Without this, RSS aggregators (BeBeez, etc.) that
    # publish general market news get wrongly attributed to the fund.
    # Ecosystem funds are flagged via "is_ecosystem_newsroom": true in db.json.

    if fund and fund.get("is_ecosystem_newsroom"):
        combined_text = (
            (signal.get("title") or "") + " " + (signal.get("what_changed") or "")
        ).lower()
        # Extract meaningful words from slug (e.g. "cdp-venture-capital" → ["cdp"])
        slug_keywords = [w for w in fund_slug.split("-") if len(w) >= 3 and w not in ("sgr", "sicaf", "sim", "spa", "srl", "capital", "partners", "group", "venture")]
        if not slug_keywords:
            slug_keywords = [fund_slug.split("-")[0]]
        if not any(kw in combined_text for kw in slug_keywords):
            return True  # ecosystem news not about this fund

    # Skip remaining misattribution checks for signals from the fund's own website
    source_url = (signal.get("source_url") or "").lower()
    if fund and source_url:
        fund_website = (fund.get("website") or "").lower().rstrip("/")
        if fund_website and is_same_domain(fund_website, source_url):
            return False

    # Build a set of words from the fund name for matching.
    # Exclude generic Italian/English words that appear in many fund names and are
    # therefore not distinctive enough to confirm that the tagged fund is mentioned.
    # Example: "fondo" and "italiano" appear in both "Fondo Italiano d'Investimento"
    # and "Fondo Italiano per l'Efficienza Energetica (FIEE)" — using them as
    # co-investment evidence causes false negatives in misattribution detection.
    _NON_DISTINCTIVE = {
        "sgr", "sicaf", "sim", "spa", "srl", "capital", "partners", "group",
        # Common Italian words that appear in multiple fund names
        "fondo", "italiano", "italiana", "italiane", "italiani",
        "fondi", "investimento", "investimenti",
    }
    fund_words = set(fund_name_lower.split()) - _NON_DISTINCTIVE

    combined = title_lower + " " + (signal.get("what_changed") or "").lower()

    def _tagged_fund_distinctly_mentioned(text: str) -> bool:
        """Return True only if a DISTINCTIVE word from the tagged fund name appears in text."""
        return any(fw in text for fw in fund_words if len(fw) >= 4)

    # Check if title starts with a different known fund name
    for known in KNOWN_FUND_NAMES:
        if title_lower.startswith(known + " ") or title_lower.startswith(known + ":"):
            known_norm = known.replace(" ", "-").replace("&", "")
            fund_first = fund_name_lower.split()[0] if fund_name_lower else ""
            if known_norm.replace("-", " ") not in fund_name_lower and fund_first not in known_norm.replace("-", " "):
                # Before flagging: check if the tagged fund is ALSO mentioned (co-investment).
                # Require a DISTINCTIVE word (len >= 4, not a common Italian placeholder)
                # to avoid false co-investment guards on shared vocabulary like "fondo"/"italiano".
                if _tagged_fund_distinctly_mentioned(title_lower):
                    continue  # tagged fund mentioned too — co-investment, not misattribution
                return True

    # High-confidence parenthetical attribution near the start:
    # "Company (Macquarie) ..." / "Company (Bain Capital-...) ..."
    lead_parenthetical = re.search(r"^[^()]{0,120}\(([^)]+)\)", title_lower)
    if lead_parenthetical:
        parenthetical = lead_parenthetical.group(1)
        for known in KNOWN_FUND_NAMES:
            known_pattern = re.escape(known).replace(r"\ ", r"\s+")
            if re.search(rf"\b{known_pattern}\b", parenthetical):
                known_norm = known.replace(" ", "-").replace("&", "")
                fund_first = fund_name_lower.split()[0] if fund_name_lower else ""
                if known_norm.replace("-", " ") in fund_name_lower or (fund_first and fund_first in known_norm.replace("-", " ")):
                    continue
                if _tagged_fund_distinctly_mentioned(combined):
                    continue  # tagged fund also mentioned — co-investment
                return True

    # Check for "X SGR" mention where X is not the tagged fund
    sgr_matches = re.finditer(r"\b((?:[a-z]{2,}\s+){0,3}[a-z]{2,})\s+sgr\b", combined)
    for sgr_match in sgr_matches:
        mentioned_phrase = sgr_match.group(1).lower().strip()
        mentioned_words = mentioned_phrase.split()
        generic_prefixes = {
            "capital", "alternative", "investimenti", "equity", "asset", "real",
            "venture", "private", "infra", "infrastructure", "la", "il", "lo",
        }
        # Skip if all words are generic
        non_generic = [w for w in mentioned_words if w not in generic_prefixes]
        if not non_generic:
            continue
        # Check if any significant word from the mentioned SGR matches the tagged fund
        fund_first = fund_name_lower.split()[0] if fund_name_lower else ""
        mentioned_matches_fund = any(
            w in fund_name_lower or fund_first in w
            for w in non_generic if len(w) >= 2
        )
        if not mentioned_matches_fund:
            # Different SGR mentioned — but check if tagged fund is also mentioned (co-investment)
            if _tagged_fund_distinctly_mentioned(combined):
                continue  # tagged fund also mentioned — co-investment
            return True

    return False


def _is_support_role(title: str) -> bool:
    """Return True if the title indicates non-investment support staff."""
    return any(pat.search(title) for pat in SUPPORT_ROLE_PATTERNS)


def _is_careers_job_posting(signal: dict) -> bool:
    """Return True if this signal is a job posting from a CAREERS page."""
    page_category = (signal.get("page_category") or "").upper()
    if page_category != "CAREERS":
        return False

    text = f"{signal.get('title', '')} {signal.get('what_changed', '')}".lower()

    return any(p.search(text) for p in _CAREERS_JOB_PATTERNS)


def _filter_support_roles_from_signal(signal: dict) -> dict | None:
    """
    For people_move signals, remove support-staff names from the signal.
    For CAREERS signals, check if it's a support-role job posting.
    Returns None if the signal should be dropped.
    """
    # Drop CAREERS job postings for support/admin roles
    page_category = (signal.get("page_category") or "").upper()
    if page_category == "CAREERS":
        text = f"{signal.get('title', '')} {signal.get('what_changed', '')}".lower()
        if _is_low_value_job_posting(text):
            return None

    if signal.get("signal_type") != "people_move":
        return signal

    what_changed = signal.get("what_changed", "")
    if not what_changed:
        return signal

    # Parse "Name (Title)" entries from what_changed text
    # Format: "New team member(s): Name1 (Title1), Name2 (Title2) (+N more)"
    entries = re.findall(r'([^,(]+?)\s*\(([^)]+)\)', what_changed)
    if not entries:
        return signal

    # Filter out support roles
    kept = []
    removed = []
    for name, title in entries:
        name = name.strip().lstrip(': ')
        if _is_support_role(title):
            removed.append(f"{name} ({title})")
        else:
            kept.append(f"{name} ({title})")

    if not kept:
        # All people are support staff - drop this signal
        return None

    if not removed:
        # Nothing to filter
        return signal

    # Rebuild the signal with only relevant people
    signal = dict(signal)  # shallow copy
    prefix = "New team members: " if len(kept) > 1 else "New team member: "
    signal["what_changed"] = prefix + ", ".join(kept)
    signal["title"] = prefix + kept[0]
    if len(kept) > 1:
        signal["title"] = f"New team members: {kept[0].split('(')[0].strip()} (+{len(kept) - 1} more)"

    # Update extracted people list
    entities = signal.get("extracted_entities", {})
    if entities.get("people"):
        kept_names = {e.split("(")[0].strip().lower() for e in kept}
        entities["people"] = [p for p in entities["people"] if p.lower().strip() in kept_names]
        signal["extracted_entities"] = entities

    return signal


def _has_named_people(text: str) -> bool:
    """Return True if the text contains at least one likely full name."""
    if not text:
        return False
    return bool(_RE_NAMED_PEOPLE.search(text))


def _is_senior_title(title: str) -> bool:
    """Return True if the title indicates a senior role."""
    return any(pat.search(title) for pat in SENIOR_TITLE_PATTERNS)


def _has_people_transition_verb(text: str) -> bool:
    """Return True if text has explicit hire/appointment/departure language."""
    return bool(PEOPLE_TRANSITION_VERBS_RE.search(text or ""))


def _normalize_profile_title(title: str) -> str:
    """Normalize title for TEAM/profile pattern checks."""
    if not title:
        return ""
    # Repair joined tokens like "NoèLegal" -> "Noè Legal" before role matching.
    repaired = re.sub(r"([a-zà-öø-ÿ])([A-Z])", r"\1 \2", title)
    return repaired.strip().lower()


def _is_team_role_profile_line(title: str, page_category: str) -> bool:
    """Detect static TEAM profile lines like 'Name Head of X'."""
    if page_category != "TEAM":
        return False
    title_lower = _normalize_profile_title(title)
    if not title_lower:
        return False
    if _has_people_transition_verb(title_lower):
        return False
    return bool(TEAM_ROLE_PROFILE_TITLE_RE.search(title_lower))


def _is_role_opening_title(title: str) -> bool:
    """Detect role-opening/job-style titles misclassified as people moves."""
    title_lower = _normalize_profile_title(title)
    if not title_lower:
        return False
    if _has_people_transition_verb(title_lower):
        return False
    return bool(ROLE_OPENING_TITLE_RE.search(title_lower))


def _is_team_static_description(title: str, text: str, page_category: str) -> bool:
    """Detect static TEAM/company description blurbs (not a real signal)."""
    if page_category != "TEAM":
        return False
    combined = _normalize_profile_title(f"{title or ''} {text or ''}")
    if not combined:
        return False
    if _has_people_transition_verb(combined):
        return False
    if (
        _matches_any(DEAL_CLASSIFY_PATTERNS, combined)
        or _matches_any(EXIT_CLASSIFY_PATTERNS, combined)
        or _matches_any(FUNDRAISE_CLASSIFY_PATTERNS, combined)
    ):
        return False
    return bool(TEAM_STATIC_CORP_DESC_RE.search(combined))


def _is_junior_title(title: str) -> bool:
    """Return True if the title indicates a junior role."""
    return any(pat.search(title) for pat in JUNIOR_TITLE_PATTERNS)


def _mentions_italy(text: str) -> bool:
    """Return True if the text mentions Italy or an Italian city."""
    return any(pat.search(text) for pat in ITALY_MENTION_PATTERNS)


def _mentions_europe(text: str) -> bool:
    """Return True if the text mentions Europe or a European country/city."""
    return bool(_EUROPE_MENTION_RE.search(text))


# ── Italian name detection for people_move signals ──────────────────────────
# Distinctive Italian first names (male + female).  In PE/VC context the
# false-positive risk is very low, so we include names like "Marco" and "Laura"
# that are common across Romance languages but still strongly signal Italian.
_ITALIAN_FIRST_NAMES: set[str] = {
    # Male
    "giuseppe", "giovanni", "francesco", "antonio", "alessandro", "andrea",
    "matteo", "stefano", "paolo", "massimo", "gianluca", "fabio", "enrico",
    "claudio", "riccardo", "alberto", "davide", "simone", "lorenzo", "federico",
    "michele", "nicola", "filippo", "daniele", "gabriele", "vincenzo", "giorgio",
    "mario", "pietro", "salvatore", "carlo", "angelo", "raffaele", "emanuele",
    "sergio", "domenico", "tommaso", "giacomo", "diego", "leonardo", "edoardo",
    "vittorio", "giuliano", "gianfranco", "gianni", "pierluigi", "giancarlo",
    "umberto", "maurizio", "alfredo", "luciano", "renato", "aldo", "franco",
    "silvio", "dario", "flavio", "danilo", "ernesto", "guido", "marcello",
    "piero", "sandro", "tullio", "ugo", "valerio", "cesare", "corrado",
    "donato", "eugenio", "fabrizio", "gennaro", "luigi", "pasquale", "luca",
    "roberto", "mauro", "armando", "agostino", "adriano", "beniamino",
    "giampaolo", "giampiero", "gianmaria", "ottavio", "ruggero", "tiziano",
    "marco", "bruno", "alessio", "mirko", "ivano", "nino", "renzo", "enzo",
    "lamberto", "italo", "benito", "fausto", "gino", "livio", "manlio",
    "nunzio", "orazio", "primo", "rocco", "tancredi", "tiberio", "virgilio",
    # Female
    "giulia", "francesca", "chiara", "valentina", "alessandra", "federica",
    "silvia", "martina", "paola", "roberta", "simona", "barbara", "daniela",
    "elena", "monica", "claudia", "cristina", "elisabetta", "ilaria", "lucia",
    "marta", "patrizia", "stefania", "arianna", "beatrice", "carlotta",
    "caterina", "eleonora", "emanuela", "irene", "isabella", "margherita",
    "michela", "nicoletta", "serena", "veronica", "viviana", "grazia",
    "concetta", "ornella", "rossella", "antonella", "donatella", "graziella",
    "laura", "anna", "maria", "giovanna", "rosa", "carmela", "teresa",
    "luisa", "giuseppina", "carla", "franca", "silvana", "renata", "bruna",
    "milena", "mirella", "lorella", "cinzia", "marilena", "loredana",
}

# Top Italian surnames (high confidence — these are distinctively Italian).
_ITALIAN_SURNAMES: set[str] = {
    "rossi", "russo", "ferrari", "esposito", "bianchi", "romano", "colombo",
    "ricci", "marino", "greco", "gallo", "conti", "costa", "giordano",
    "mancini", "rizzo", "lombardi", "moretti", "barbieri", "fontana",
    "santoro", "mariani", "rinaldi", "caruso", "ferrara", "santini",
    "fabbri", "marchetti", "leone", "longo", "gentile", "martinelli",
    "vitale", "lombardo", "serra", "coppola", "parisi", "villa", "conte",
    "ferraro", "ferri", "farina", "bianco", "marini", "grasso", "valentini",
    "messina", "sala", "galli", "pellegrini", "palumbo", "sanna", "rizzi",
    "cattaneo", "monti", "silvestri", "testa", "grassi", "mazza", "pagano",
    "bernardi", "giuliani", "benedetti", "barone", "ruggiero", "piras",
    "carbone", "orlando", "piazza", "montanari", "battaglia", "sorrentino",
    "riva", "donati", "poli", "amato", "neri", "basile", "bellini", "bruni",
    "martini", "gatti", "morandi", "fiore", "marchese", "moro", "giorgi",
    "valli", "palmieri", "pozzi", "berardi", "landi", "ceccarelli",
    "caputo", "ferrero", "petrini", "colombini", "molinari", "mazzoni",
    "baldi", "bianchini", "cavallaro", "damiani", "garofalo", "iannone",
    "pastore", "piccolo", "sartori", "mazzola", "palermo", "napolitano",
    "cataldi", "vitali", "castellani", "martello", "ravelli", "cimmino",
    "perrone", "lucchese", "ventura", "proietti", "locatelli", "mantovani",
    "zanetti", "pecoraro", "ferraris", "gargiulo", "carotenuto", "scognamiglio",
    "pisani", "mauro", "mura", "furlan", "tommasini", "capasso", "accardi",
    "baldini", "cecchini", "corsi", "delvecchio", "falcone", "innocenti",
    "lupo", "milani", "nardi", "paolini", "pepe", "ruggeri", "sarti", "tosi",
    "villani", "zanella", "zucchi", "agostini", "albanese", "arcieri",
    "baroni", "bonetti", "borghi", "canevari", "capelli", "casali", "cipriani",
    "corti", "dini", "fiorentino", "franchi", "gaeta", "giannini", "grandi",
    "lazzari", "lorusso", "magnani", "mattioli", "mazzi", "montagna", "moroni",
    "oliva", "panetta", "peretti", "petrucci", "pinto", "poggi", "raimondi",
    "rota", "ruocco", "sabbatini", "scalise", "taverna", "trevisan", "trotta",
    "zampieri", "zani",
    # Less common but distinctively Italian surnames (Venetian, Sicilian, etc.)
    "bragadin", "riulini", "veronesi", "padovani", "bergamaschi", "cremonesi",
    "vicentini", "bresciani", "bolognesi", "modenese", "parmigiani", "reggiani",
    "ferrarese", "ravennate", "romagnoli", "trentini", "friulano", "istriano",
    "catanese", "palermitano", "siracusano", "messinese", "agrigentino",
    "trapanese", "ragusano", "ennese", "nisseno", "sardegna",
    "buonanno", "cannavaro", "cassano", "chiellini", "buffon", "pirlo",
    "totti", "barella", "insigne", "immobile", "bonucci", "verratti",
    "acerbi", "bastoni", "dimarco", "frattesi", "pellegrino", "scamacca",
    "tonali", "raspadori", "zaccagni", "politano", "berardi", "castrovilli",
    "sensi", "cristante", "mancino", "calabresi", "pugliese", "campano",
    "abruzzese", "marchigiano", "molisano", "laziale", "ligure", "piemontese",
    "valdostano", "briatore", "berlusconi", "benetton", "barilla", "ferragamo",
    "versace", "armani", "gucci", "prada", "bulgari", "zegna", "missoni",
    "borsellino", "falconi", "ferretti", "gamberini", "giacomelli", "landini",
    "lucchini", "maestri", "marangoni", "matarrese", "melandri", "menarini",
    "menichetti", "olivetti", "paganini", "pagliuca", "pancaldi", "pandolfi",
    "pasquali", "pederzoli", "pellicano", "pennacchi", "pietrobon", "poletti",
    "pontecorvo", "rampini", "rossetti", "salimbeni", "santagata", "santarelli",
    "sartorelli", "scarpelli", "sgambati", "tagliaferri", "trombetti",
    "valsecchi", "visconti", "zambon", "zardini",
}

# Italian compound surname prefixes
_ITALIAN_SURNAME_PREFIX_RE = re.compile(
    r"\b(?:De|Di|Del|Della|Dello|Dell['\u2019]|D['\u2019]|Lo|La)\s+[A-Z][a-zà-ü]",
)


def _has_italian_name(text: str) -> bool:
    """Detect Italian personal names in signal text.

    Checks three layers:
    1. Italian compound surname prefixes (De Giorgi, Di Marco, Dell'Aquila, ...)
    2. Known Italian first names followed by a capitalized word (likely surname)
    3. Known Italian surnames preceded by a capitalized word (likely first name)
    """
    if not text:
        return False
    # Layer 1: compound prefixes (cheapest check)
    if _ITALIAN_SURNAME_PREFIX_RE.search(text):
        return True
    # Tokenise for layers 2 & 3
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'\u2019]+", text)
    lower_words = [w.lower() for w in words]
    for i, lw in enumerate(lower_words):
        # Layer 2: Italian first name followed by a capitalized word
        if lw in _ITALIAN_FIRST_NAMES and i + 1 < len(words) and words[i + 1][0].isupper():
            return True
        # Layer 3: Italian surname preceded by a capitalized word
        if lw in _ITALIAN_SURNAMES and i > 0 and words[i - 1][0].isupper():
            return True
    return False


def _mentions_non_eu_geo(text: str) -> bool:
    """Return True if the text explicitly mentions a non-Europe geography."""
    if not text:
        return False
    return any(pat.search(text) for pat in NON_EU_TEXT_PATTERNS)

# _strip_read_time, _strip_urls — imported from signal_patterns
# _ATTACHED_CONNECTORS, _repair_attached_connectors, _iter_company_compacts,
# _fix_spacing, _repair_common_splits, _clean_signal_title, _clean_signal_text,
# _normalize_monetary_values, NEWSPAPER_ONLY_RE — now in signal_text_utils


def _normalize_for_compare(text: str) -> str:
    if not text:
        return ""
    cleaned = text.lower()
    cleaned = re.sub(r"[^a-z0-9à-öø-ÿ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _company_candidates_from_signal(signal: dict) -> list[str]:
    """Collect company-name candidates from extracted entities and portfolio hints."""
    entities = signal.get("extracted_entities") or {}
    companies: list[str] = []

    for company in entities.get("companies") or []:
        value = str(company or "").strip()
        if value:
            companies.append(value)

    portfolio_guess = _extract_portfolio_company_name(
        signal,
        signal.get("what_changed") or "",
        signal.get("title") or "",
    )
    if portfolio_guess and not _is_generic_portfolio_name(portfolio_guess):
        companies.append(portfolio_guess)

    for tc in signal.get("target_companies") or []:
        if not isinstance(tc, dict):
            continue
        value = str(tc.get("name") or "").strip()
        if value:
            companies.append(value)

    return companies


def _clean_signal_fields(signal: dict) -> dict:
    """Strip read-time noise and concatenation artifacts from text fields.

    Uses shared clean_display_text() from signal_text_utils for uniform cleaning
    of all text fields (title, what_changed, diff_summary, enriched_summary).
    """
    if not signal:
        return signal
    signal = dict(signal)
    company_candidates = _company_candidates_from_signal(signal)
    # Unified display cleaning for all text fields
    if signal.get("title"):
        signal["title"] = clean_display_text(signal["title"], is_title=True)
    for key in ("what_changed", "diff_summary", "enriched_summary"):
        if signal.get(key):
            signal[key] = clean_display_text(signal[key])
    # Remove duplicate summary when it matches title
    title_norm = _normalize_for_compare(signal.get("title", ""))
    what_norm = _normalize_for_compare(signal.get("what_changed", ""))
    if title_norm and title_norm == what_norm:
        signal["what_changed"] = ""
    # Normalize monetary values then do a single entity-aware connector repair pass
    for key in ("title", "what_changed", "diff_summary", "enriched_summary"):
        if signal.get(key):
            signal[key] = normalize_monetary_values(signal[key])
            signal[key] = repair_attached_connectors(
                signal[key],
                company_candidates=company_candidates,
            )
    # Re-capitalize known entity names (companies, people, funds)
    # After sentence-case normalization, proper nouns may be lowercased
    entities = signal.get("extracted_entities") or {}
    entity_names = list(entities.get("companies") or []) + list(entities.get("people") or [])
    for tc in signal.get("target_companies") or []:
        if not isinstance(tc, dict):
            continue
        name = str(tc.get("name") or "").strip()
        if name:
            entity_names.append(name)
    # Also add fund name from slug as a capitalization source
    fund_slug = signal.get("fund_slug") or ""
    if fund_slug:
        # Smart slug-to-display: short tokens (≤4 chars) are likely acronyms (KKR, EQT, CVC)
        # Exception: common English words that happen to be ≤4 chars should be title-cased
        _NOT_ACRONYMS = {"bain", "real", "blue", "next", "tree", "open", "true", "fair", "iron", "wise", "gold", "star"}
        parts = fund_slug.split("-")
        display_parts = [p.upper() if len(p) <= 4 and p.lower() not in _NOT_ACRONYMS else p.title() for p in parts]
        fund_display = " ".join(display_parts)
        entity_names.append(fund_display)
    # Add related fund names as capitalization hints (co-investors often appear in summaries).
    for related_slug in signal.get("related_fund_slugs") or []:
        if not isinstance(related_slug, str) or not related_slug.strip():
            continue
        _NOT_ACRONYMS = {"bain", "real", "blue", "next", "tree", "open", "true", "fair", "iron", "wise", "gold", "star"}
        parts = related_slug.strip().split("-")
        display_parts = [p.upper() if len(p) <= 4 and p.lower() not in _NOT_ACRONYMS else p.title() for p in parts]
        entity_names.append(" ".join(display_parts))
    # Extract company/fund-like title-cased phrases from nearby fields (e.g. "Miura Partners").
    entity_names.extend(
        extract_company_like_entities(
            signal.get("title") or "",
            signal.get("what_changed") or "",
            signal.get("title_original") or "",
            signal.get("what_changed_original") or "",
        )
    )
    if entity_names:
        for key in ("title", "what_changed", "enriched_summary"):
            if signal.get(key):
                signal[key] = capitalize_entities(signal[key], entity_names)
        # Capitalization hints can occasionally re-introduce token-split artifacts
        # from raw text. Apply focused repairs without re-running full cleaning.
        for key in ("title", "what_changed", "enriched_summary"):
            if signal.get(key):
                signal[key] = re.sub(r"\bberar\s+di\b", "Berardi", signal[key], flags=re.IGNORECASE)
                signal[key] = re.sub(r"\buni\s+credit\b", "UniCredit", signal[key], flags=re.IGNORECASE)
    # Final brand/acronym casing corrections independent of NER hints.
    for key in ("title", "what_changed", "enriched_summary"):
        if signal.get(key):
            signal[key] = re.sub(r"\bteamsystem\b", "TeamSystem", signal[key], flags=re.IGNORECASE)
            signal[key] = re.sub(r"\bbanco\s+bpm\b", "Banco BPM", signal[key], flags=re.IGNORECASE)
    # Normalize date fields to ISO format
    for date_key in ("published_at", "enriched_date"):
        raw_date = signal.get(date_key)
        if raw_date and isinstance(raw_date, str):
            normalized = _normalize_date_string(raw_date)
            if normalized:
                signal[date_key] = normalized
    # Humanize source_name: convert slug-format names to display names
    signal["source_name"] = _humanize_source_name(signal.get("source_name", ""))
    # Normalize deal_amount field to consistent currency format
    if signal.get("deal_amount"):
        signal["deal_amount"] = normalize_monetary_values(signal["deal_amount"])
    # Backfill deal_amount from title/what_changed when field is empty.
    # Many news-type and seed signals have amounts in their text but no structured field.
    if not signal.get("deal_amount"):
        _amount_source = signal.get("title") or signal.get("what_changed") or ""
        if _amount_source:
            _amount_match = _RE_EXTRACT_AMOUNT.search(_amount_source)
            if _amount_match:
                _raw_amount = _amount_match.group(0).strip()
                _normalized = normalize_monetary_values(_raw_amount)
                if _normalized and _normalized != _raw_amount:
                    signal["deal_amount"] = _normalized
                elif _normalized:
                    signal["deal_amount"] = _normalized
    return signal


# Source name overrides for non-obvious slug → display name mappings
_SOURCE_NAME_OVERRIDES = {
    "manual-192": "CVC DIF",
    "manual_192": "CVC DIF",
}


def _humanize_source_name(name: str) -> str:
    """Convert slug-format source names to human-readable display names.

    Handles: 'alcedo-sgr' → 'Alcedo SGR', 'fondo-italiano-d-investimento-sgr' → "Fondo Italiano d'Investimento SGR"
    Passes through names that already look human-readable (contain spaces or uppercase).
    """
    if not name or not name.strip():
        return name
    name = name.strip()
    # Strip embedded newlines
    name = name.replace("\n", " ").replace("\r", " ")
    # Check overrides first
    if name in _SOURCE_NAME_OVERRIDES:
        return _SOURCE_NAME_OVERRIDES[name]
    # If it already has spaces AND mixed case, it's probably already human-readable
    # But fix known acronym capitalization issues first
    name = re.sub(r"\bCdp\b", "CDP", name)
    name = re.sub(r"\bFvs\b", "FVS", name)
    name = re.sub(r"\bIgi\b", "IGI", name)
    # Fix common legal suffixes with wrong case (e.g. "Sgr" → "SGR")
    name = re.sub(r"\bSgr\b", "SGR", name)
    name = re.sub(r"\bSicaf\b", "SICAF", name)
    name = re.sub(r"\bSim\b", "SIM", name)
    name = re.sub(r"\bAifm\b", "AIFM", name)
    if " " in name and not name.islower():
        return name
    # If it's a slug (lowercase with hyphens), humanize it
    if "-" in name and name == name.lower():
        parts = name.split("-")
        # Italian suffixes that stay uppercase
        _UPPER_SUFFIXES = {"sgr", "sicaf", "sim", "spa", "srl", "aifm", "cdp", "fvs", "igi"}
        # Re-join "d" + next word with apostrophe (Italian contraction)
        humanized = []
        i = 0
        while i < len(parts):
            part = parts[i]
            if part == "d" and i + 1 < len(parts):
                humanized.append(f"d'{parts[i+1].title()}")
                i += 2
                continue
            if part in _UPPER_SUFFIXES:
                humanized.append(part.upper())
            else:
                humanized.append(part.title())
            i += 1
        return " ".join(humanized)
    # If it's a single lowercase word, title-case it
    if name == name.lower() and " " not in name:
        return name.title()
    return name


def _normalize_for_dedupe(text: str) -> str:
    """Normalize text for dedup comparison: lowercase, strip non-alphanumeric."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9\u00e0-\u00f9 ]", "", text.lower()).strip()


def _signal_dedupe_key(signal: dict) -> str:
    """Composite key for duplicate suppression in filtered output.

    Uses normalized title for fuzzy-match dedup (catches minor formatting differences).
    fund_slug + first 80 chars of normalized title is enough to deduplicate —
    published_at is excluded because the same news item often appears with and without a date.
    """
    fund_slug = (signal.get("fund_slug") or "").strip()
    title = _normalize_for_dedupe(signal.get("title") or "")
    return f"{fund_slug}::{title[:80]}"


def _ensure_unique_signal_id(signal: dict, dedupe_key: str, seen_ids: set[str]) -> tuple[dict, bool]:
    """Ensure every signal has a unique id, even when upstream IDs collide."""
    if not signal:
        return signal, False
    signal = dict(signal)
    base_id = (signal.get("id") or "").strip()
    if not base_id:
        base_id = f"signal-{hashlib.blake2s(dedupe_key.encode(), digest_size=4).hexdigest()}"
        signal["id"] = base_id
        seen_ids.add(base_id)
        return signal, True

    if base_id not in seen_ids:
        seen_ids.add(base_id)
        return signal, False

    suffix = hashlib.blake2s(dedupe_key.encode(), digest_size=4).hexdigest()
    candidate = f"{base_id}-{suffix}"
    if candidate in seen_ids:
        counter = 2
        while f"{candidate}-{counter}" in seen_ids:
            counter += 1
        candidate = f"{candidate}-{counter}"
    signal["id"] = candidate
    seen_ids.add(candidate)
    return signal, True


# Italian legal form markers — funds with these in their name are Italian-domiciled
_ITALIAN_FUND_MARKER = re.compile(r"\b(sgr|sicaf|sicav|sim)\b", re.IGNORECASE)


def _fund_geo_scope(fund: dict | None, fund_slug: str) -> str:
    """
    Determine a fund's geography scope.
    Returns: "italy_focused", "europe_wide", "mixed_or_global", or "unknown".

    - italy_focused: geographies includes 'Italy', or fund has Italian legal form (SGR/SICAF/SIM)
    - europe_wide: EU-only geographies but no 'Italy' and no Italian legal form
    - mixed_or_global: geographies includes non-EU regions (USA, Asia, Worldwide, etc.)
    """
    if fund:
        geos = [g.lower().strip() for g in (fund.get("geographies") or []) if g]
        fund_name = fund.get("name") or ""
        is_italian_entity = bool(_ITALIAN_FUND_MARKER.search(fund_name))

        if geos:
            has_non_eu = any(g in NON_EU_GEO_SET for g in geos)
            has_italy = "italy" in geos
            # Italian regional geographies (Veneto, Friuli, Lombardia, etc.) = Italy
            has_italian_region = any(g in ITALIAN_REGIONS for g in geos)

            if has_non_eu:
                return "mixed_or_global"
            if (has_italy or has_italian_region) and is_italian_entity:
                return "italy_focused"
            if has_italian_region and not has_italy:
                # Regional Italian geo (e.g. 'Veneto', 'Friuli') = italy_focused
                return "italy_focused"
            if has_italy and not is_italian_entity:
                # Fund has 'Italy' in geos but no Italian legal form (SGR/SICAF/SIM)
                # These are typically pan-European funds with Italian AIFI membership
                # Only classify as italy_focused if Italy is the SOLE geography
                if len(geos) == 1:
                    return "italy_focused"
                return "europe_wide"
            if is_italian_entity:
                return "italy_focused"
            # EU geographies but no Italy and no Italian legal form → pan-European
            if any(g in EUROPE_GEO_SET for g in geos):
                return "europe_wide"
            return "mixed_or_global"

        # No geographies — fall back to HQ + legal form
        hq_region = (fund.get("hq_region") or "").lower().strip()
        if hq_region in ITALIAN_REGIONS or hq_region == "italy":
            if is_italian_entity:
                return "italy_focused"
            return "europe_wide"  # Italian office but no Italian legal form
        if hq_region in EUROPE_GEO_SET:
            return "europe_wide"

    slug = (fund_slug or "").lower()
    if "sgr" in slug or "italy" in slug or "italia" in slug:
        return "italy_focused"
    if "europe" in slug:
        return "europe_wide"

    return "unknown"


def _is_geo_relevant_signal(signal: dict, fund_geo_scope: str, fund: dict | None = None) -> bool:
    """
    Keep signals that are Italy/Europe-relevant.

    Geography filtering varies by fund scope:
    - italy_focused: core types always pass; non-core allowed unless explicitly non-EU
    - europe_wide: core types always pass; non-core need Italy/Europe evidence
    - mixed_or_global: ALL signals need Italy/Europe evidence (no free pass for core types)
    """
    signal_type = signal.get("signal_type", "")
    text = " ".join([
        signal.get("title", ""),
        signal.get("what_changed", ""),
        signal.get("diff_summary", ""),
    ])
    reasons = [str(r) for r in (signal.get("relevance_reasons") or []) if r]
    extracted = signal.get("extracted_entities") or {}
    locations = extracted.get("locations") or []
    location_text = " ".join(str(x) for x in locations if x)

    # Explicit Italy evidence must come from text/reasons/entities, not just a
    # defaulted italy_relevant=true flag.
    explicit_italy_evidence = (
        _mentions_italy(text)
        or _mentions_italy(" ".join(reasons))
        or _mentions_italy(location_text)
    )

    # Sanity-check: score=0 with no reasons means the flag was set as a default
    # upstream (or carried through), not from deterministic evidence.
    _score = signal.get("relevance_score") or 0
    _unreliable_italy_flag = (_score == 0 and not reasons)
    italy_flag_reliable = bool(signal.get("italy_relevant") is True and not _unreliable_italy_flag)

    if explicit_italy_evidence:
        return True

    # Team/people signals from Italian legal entities (SGR/SICAF/SIM) are inherently Italy-relevant
    page_category = (signal.get("page_category") or "").upper()
    if page_category == "TEAM" and fund:
        fund_name = (fund.get("name") or fund.get("legal_name") or "").upper()
        if any(suffix in fund_name for suffix in ("SGR", "SICAF", "SIM")):
            return True

    # Italy-focused funds: core types always pass; non-core unless explicitly non-EU
    if fund_geo_scope == "italy_focused":
        if italy_flag_reliable:
            return True
        if signal_type in CORE_GEO_TYPES:
            return True
        if _mentions_non_eu_geo(text):
            return False
        return True

    # Europe-wide funds: two sub-tiers based on whether Italy is in their geographies.
    #
    # Funds WITH 'Italy' in geos (Investindustrial, Ibla Capital, Charme Capital, etc.):
    #   core types pass (like italy_focused), non-core need Europe evidence.
    #   These are Italian-active PE firms classified europe_wide only because they
    #   also have 'Europe' in geos without SGR/SICAF suffix.
    #
    # Funds WITHOUT 'Italy' in geos (L Catterton, BC Partners, Oakley Capital, etc.):
    #   ALL types require Italy mention or pan-European context in the text.
    #   A French PE deal by CAPZA (no Italy in geos) is not relevant.
    if fund_geo_scope == "europe_wide":
        fund_geos = (fund.get("geographies") or []) if fund else []
        fund_has_italy_geo = "Italy" in fund_geos

        if explicit_italy_evidence:
            return True

        if fund_has_italy_geo:
            # Italy-geo funds still require explicit Italy evidence in main feed.
            return False

        # Non-Italy-geo europe-wide funds: strict mode requires explicit Italy.
        return False

    # Mixed/global funds: strict main feed requires explicit Italy evidence.
    if fund_geo_scope == "mixed_or_global":
        return False

    return bool(italy_flag_reliable and signal_type in CORE_GEO_TYPES)


def _boost_italy_relevance(signal: dict, fund_geo_scope: str) -> dict:
    """
    Promote Italy relevance for Italian-focused funds to reduce false negatives.
    Only applies to italy_focused funds (Italian SGRs, funds with 'Italy' in geographies).
    Pan-European and global funds do NOT get the boost — their signals must have
    natural Italy/Europe evidence from the relevance scorer.
    """
    if signal.get("italy_relevant") is True:
        return signal
    if fund_geo_scope != "italy_focused":
        return signal

    text = " ".join([
        signal.get("title", ""),
        signal.get("what_changed", ""),
        signal.get("diff_summary", ""),
    ])
    if _mentions_non_eu_geo(text) and not (_mentions_italy(text) or _mentions_europe(text)):
        return signal

    # Don't boost if text explicitly mentions non-Italy EU countries without Italy
    # This prevents CAPZA (French), Triton (Nordic) etc. from having all signals boosted
    if _NON_ITALY_EU_COUNTRIES_RE.search(text) and not _mentions_italy(text):
        return signal

    signal_type = signal.get("signal_type", "")
    page_category = (signal.get("page_category") or "").upper()
    core_categories = {"NEWS", "PORTFOLIO", "TEAM", "CAREERS", "ABOUT"}

    # Boost if signal has a meaningful type AND either a known page category or no page category
    # (signals from deprecated generators may have page_category=None but are still valid)
    if signal_type in CORE_QUALITY_TYPES and (page_category in core_categories or not page_category):
        signal = dict(signal)
        signal["italy_relevant"] = True
        score = signal.get("relevance_score")
        if isinstance(score, (int, float)):
            signal["relevance_score"] = max(score, 0.35)
        else:
            signal["relevance_score"] = 0.35
        reasons = list(signal.get("relevance_reasons") or [])
        if "Fund geography: Europe/Italy" not in reasons:
            reasons.append("Fund geography: Europe/Italy")
        signal["relevance_reasons"] = reasons

    return signal


def _filter_junior_non_italy_people(signal: dict) -> dict | None:
    """
    For people_move signals, remove junior (Analyst/Associate/Intern) hires
    that have no Italy connection. Also drop signals with >100 people
    (bulk team-page scrapes).
    Returns None if the signal should be dropped entirely.
    """
    if signal.get("signal_type") != "people_move":
        return signal

    what_changed = signal.get("what_changed", "")
    if not what_changed:
        return signal

    # Parse "Name (Title)" entries
    entries = re.findall(r'([^,(]+?)\s*\(([^)]+)\)', what_changed)
    if not entries:
        # No parseable "(Title)" entries — check for bulk scrape via "+N more"
        more_match = re.search(r'\+(\d+)\s+more', what_changed)
        extra = int(more_match.group(1)) if more_match else 0
        # Count comma-separated names as a rough people count
        name_count = len([n for n in what_changed.split(',') if n.strip()])
        if name_count + extra > MAX_PEOPLE_PER_SIGNAL:
            return None
        return signal

    # Drop bulk team-page scrapes (count parsed entries + "+N more")
    more_match = re.search(r'\+(\d+)\s+more', what_changed)
    extra = int(more_match.group(1)) if more_match else 0
    if len(entries) + extra > MAX_PEOPLE_PER_SIGNAL:
        return None

    # Filter junior non-Italy people
    kept = []
    removed = []
    for name, title in entries:
        name = name.strip().lstrip(': ')
        # Strip leading prefixes like "New team member(s):"
        name = re.sub(r'^New team members?:\s*', '', name, flags=re.IGNORECASE)
        full_text = f"{name} ({title})"

        if _is_junior_title(title) and not _is_senior_title(title):
            # Junior title — only keep if Italy is mentioned in title
            if _mentions_italy(title):
                kept.append(full_text)
            else:
                removed.append(full_text)
        else:
            # Senior, mid-level, or unknown — keep
            kept.append(full_text)

    if not kept:
        return None

    if not removed:
        return signal

    # Rebuild the signal with only relevant people
    signal = dict(signal)  # shallow copy
    prefix = "New team members: " if len(kept) > 1 else "New team member: "
    signal["what_changed"] = prefix + ", ".join(kept)
    signal["title"] = prefix + kept[0]
    if len(kept) > 1:
        signal["title"] = f"New team members: {kept[0].split('(')[0].strip()} (+{len(kept) - 1} more)"

    # Update extracted people list
    entities = signal.get("extracted_entities", {})
    if entities.get("people"):
        kept_names = {e.split("(")[0].strip().lower() for e in kept}
        entities["people"] = [p for p in entities["people"] if p.lower().strip() in kept_names]
        signal["extracted_entities"] = entities

    return signal


ITALIAN_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}
ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
ALL_MONTHS = {**ITALIAN_MONTHS, **ENGLISH_MONTHS}


def _normalize_date_string(value: str) -> str | None:
    """Try to normalize a human-readable date string to ISO format (YYYY-MM-DD)."""
    if not value:
        return None
    value = value.strip()

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value

    # "DD.MM.YYYY" or "DD/MM/YYYY" (European dotted/slash format, 4-digit year)
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", value)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Disambiguate: if a > 12 it must be day, if b > 12 it must be day
        if a > 12 and b <= 12:
            day, month = a, b  # DD.MM.YYYY
        elif b > 12 and a <= 12:
            day, month = b, a  # MM.DD.YYYY
        else:
            day, month = a, b  # Default to DD.MM.YYYY (European convention)
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # "DD.MM.YY" or "MM.DD.YY" (2-digit year)
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2})$", value)
    if m:
        a, b, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy
        if a > 12 and b <= 12:
            day, month = a, b
        elif b > 12 and a <= 12:
            day, month = b, a
        else:
            day, month = a, b  # European convention: DD.MM.YY
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year:04d}-{month:02d}-{day:02d}"

    # "DD Month YYYY" or "D Month YYYY" (Italian or English)
    m = re.match(r"^(\d{1,2})\s+([A-Za-zÀ-ú]+)\s+(\d{4})$", value)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month_num = ALL_MONTHS.get(month_name)
        if month_num:
            return f"{year:04d}-{month_num:02d}-{day:02d}"

    # "Month DD, YYYY" or "Month DD YYYY" (Italian or English)
    m = re.match(r"^([A-Za-zÀ-ú]+)\s+(\d{1,2}),?\s+(\d{4})$", value)
    if m:
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month_num = ALL_MONTHS.get(month_name)
        if month_num:
            return f"{year:04d}-{month_num:02d}-{day:02d}"

    return None


def _parse_signal_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) >= 19 and "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if len(value) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        # Try normalizing non-ISO date strings
        normalized = _normalize_date_string(value)
        if normalized and len(normalized) >= 10:
            return datetime.strptime(normalized[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _has_amount(text: str) -> bool:
    if not text:
        return False
    return bool(_RE_HAS_AMOUNT.search(text))


def _has_deal_keyword(text: str) -> bool:
    if not text:
        return False
    return bool(_RE_HAS_DEAL_KEYWORD.search(text))


def _has_strong_deal_evidence(text: str) -> bool:
    if not text:
        return False
    return bool(_RE_STRONG_DEAL_EVIDENCE.search(text))


def _has_entity(signal: dict, summary: str) -> bool:
    entities = signal.get("extracted_entities") or {}
    companies = entities.get("companies") or []
    if companies:
        return True
    if _RE_COMPANY_LEGAL_SUFFIX.search(summary):
        return True
    # Fallback: detect multi-word capitalized company names (avoid generic words)
    generic = {"New", "Press", "Release", "Comunicato", "Stampa", "News", "Update", "Portfolio", "Fund", "Fondo"}
    matches = re.findall(r"\b([A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+){1,3})\b", summary)
    for m in matches:
        tokens = [t for t in re.split(r"\s+", m) if t]
        if any(t in generic for t in tokens):
            continue
        return True
    return False


def _mentions_tagged_fund(signal: dict, text: str) -> bool:
    """Return True if text contains meaningful tokens from the tagged fund identity."""
    if not text:
        return False

    stop_tokens = {
        "sgr", "sim", "sicaf", "spa", "srl", "sa", "sas", "ltd", "inc", "llc",
        "capital", "partners", "group", "asset", "management", "fund", "fondo",
        "investment", "investments", "investimento", "investimenti",
    }
    candidates: set[str] = set()
    for raw_name in (signal.get("fund_slug"), signal.get("fund_name"), signal.get("source_name")):
        value = str(raw_name or "").lower().replace("-", " ")
        for tok in re.findall(r"[a-z0-9&']+", value):
            if len(tok) < 4 or tok in stop_tokens:
                continue
            candidates.add(tok)

    return any(re.search(rf"\b{re.escape(tok)}\b", text, re.IGNORECASE) for tok in candidates)


# _extract_portfolio_company_name, _is_generic_portfolio_name — imported from signal_patterns


def _looks_like_company_name(text: str) -> bool:
    if not text:
        return False
    if _RE_COMPANY_LEGAL_SUFFIX.search(text):
        return True
    generic = {"New", "Press", "Release", "Comunicato", "Stampa", "News", "Update", "Portfolio", "Fund", "Fondo"}
    matches = re.findall(r"\b([A-Z][\w’'-]+(?:\s+[A-Z][\w’'-]+){1,3})\b", text)
    for m in matches:
        tokens = [t for t in re.split(r"\s+", m) if t]
        if any(t in generic for t in tokens):
            continue
        return True
    return False


def _news_evidence_score(signal: dict, text: str, summary: str) -> int:
    score = 0
    if _has_entity(signal, summary):
        score += 1
    if _has_amount(text):
        score += 1
    if signal.get("enriched_date") or signal.get("published_at"):
        score += 1
    if _has_deal_keyword(text):
        score += 1
    if _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text.lower()):
        score += 1
    if signal.get("signal_type") in {"deal_announced", "exit_announced", "fundraise_announced", "fundraise_closed", "fund_launch"}:
        score += 1
    return score


def _quality_confidence(signal: dict, text: str, summary: str, score: int, evidence_score: int) -> str:
    """Return high/medium/low confidence based on evidence and signal type."""
    signal_type = signal.get("signal_type", "")
    title = signal.get("title", "") or summary

    if signal_type == "people_move":
        if _is_senior_title(summary) or _is_senior_title(title):
            if signal.get("italy_relevant") is True or _mentions_italy(text) or _mentions_europe(text):
                return "high"
            return "medium"
        return "low"

    if evidence_score >= 4:
        return "high"
    if evidence_score >= 3 and (_has_amount(text) or _has_entity(signal, summary)):
        return "high"
    if evidence_score >= 2:
        return "medium"
    if score >= 90:
        return "medium"
    return "low"


def _passes_strict_quality_gates(
    signal: dict,
    text: str,
    summary: str,
    pre_score: int | None = None,
    evidence_score: int | None = None,
) -> bool:
    signal_type = signal.get("signal_type", "")
    page_category = (signal.get("page_category") or "").upper()
    title = signal.get("title") or summary
    role_noise = _is_role_opening_title(title) or _is_team_role_profile_line(title, page_category)
    static_team_noise = _is_team_static_description(title, text, page_category)

    if static_team_noise:
        return False

    override = False
    if pre_score is not None and pre_score >= STRICT_GATE_OVERRIDE_SCORE:
        if not role_noise:
            override = True
    # Lower threshold for italy_focused funds with italy_relevant=True (prefer false positive over false negative)
    if pre_score is not None and pre_score >= 85 and signal.get("italy_relevant") is True and signal.get("_fund_geo_scope") == "italy_focused":
        if signal_type not in {"other", "website_change"} and not role_noise:
            override = True
    if evidence_score is not None and evidence_score >= 3 and signal_type in {
        "deal_announced",
        "exit_announced",
        "fundraise_announced",
        "fundraise_closed",
        "fund_launch",
    } and (_has_deal_keyword(text) or _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text.lower())):
        override = True
    # High-score signals with deal keywords pass regardless of signal_type (catches "other" with empty page_category)
    if pre_score is not None and pre_score >= 90 and _has_deal_keyword(text):
        if signal_type not in {"other", "website_change"} and not role_noise:
            override = True

    # Non-overridable noise gates — run before any fund-scope early return
    if _is_portfolio_extraction_only(signal, text):
        return False
    if _is_portfolio_list_item(signal, text, summary, title):
        return False

    # Portfolio change signals from italy_focused funds with core types are valuable
    # (e.g. "New investment: Sa.No." from B4 Investimenti SGR)
    fund_scope = signal.get("_fund_geo_scope", "")
    _core_types = {
        "deal_announced", "exit_announced", "fundraise_announced",
        "fundraise_closed", "fund_launch",
    }
    if page_category == "PORTFOLIO" and signal_type in _core_types:
        if fund_scope == "italy_focused":
            return True
        # Europe-wide funds: allow when company name has Italian markers (S.p.A., S.r.l., etc.)
        if fund_scope == "europe_wide" and (
            signal.get("italy_relevant") is True or _mentions_italy(text)
        ):
            return True
    if page_category == "PORTFOLIO" and _is_sector_only_listing_text(text.lower()) and not (_has_deal_keyword(text) or _has_amount(text)):
        return False
    if _is_team_extraction_only(signal):
        return False
    if _is_bulk_team_extraction(signal, text):
        return False

    if override:
        return True

    # 1) Hard drop generic website/other unless strong evidence
    if signal_type in {"website_change", "other"}:
        role_noise_news = False
        if page_category == "NEWS":
            # NEWS "other" from italy_focused funds: allow with deal keyword OR amount/entity
            fund_scope = signal.get("_fund_geo_scope", "")
            title_for_gate = signal.get("title") or summary
            role_noise_news = _is_role_opening_title(title_for_gate) or _is_team_role_profile_line(title_for_gate, page_category)
            if fund_scope == "italy_focused":
                if (_has_deal_keyword(text) or _has_amount(text)) and not role_noise_news:
                    return True
                if _has_entity(signal, summary) and not role_noise_news:
                    return True
            if (_has_amount(text) or _has_entity(signal, summary)) and not role_noise_news and (
                signal.get("italy_relevant") is True or _mentions_italy(text) or _mentions_europe(text)
            ):
                return True
        if role_noise_news or not (_has_deal_keyword(text) and (_has_amount(text) or _has_entity(signal, summary))):
            return False
    if signal_type == "fund_launch":
        if not _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text.lower()):
            return False

    # 2) People moves must be senior or explicitly Italy/EU relevant
    if signal_type == "people_move":
        if role_noise:
            return False
        if _is_senior_title(summary) or _is_senior_title(signal.get("title", "")):
            pass
        elif signal.get("italy_relevant") is True or _mentions_italy(text) or _mentions_europe(text):
            pass
        else:
            return False

    # 3) News items require evidence — but lower bar for classified deal/exit/fundraise types
    if page_category == "NEWS":
        ev_score = _news_evidence_score(signal, text, summary)
        if ev_score < 2:
            # Classified deal/exit/fundraise with at least 1 evidence signal → keep
            if signal_type in {"deal_announced", "exit_announced", "fundraise_announced", "fundraise_closed", "fund_launch"}:
                if ev_score >= 1:
                    pass  # keep — has some evidence + a meaningful type
                elif _has_deal_keyword(text) or _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text.lower()):
                    pass  # keep — has deal language even without evidence signals
                elif fund_scope == "italy_focused":
                    pass  # trust core type classification for Italian funds
                else:
                    return False
            else:
                return False

    return True


def _ml_override_keep(signal: dict) -> bool:
    if not ML_USE_KEEP:
        return False
    if signal.get("ml_keep") is not True:
        return False
    keep_confidence = signal.get("ml_keep_confidence") or 0.0
    keep_prob = signal.get("ml_keep_prob") or 0.0
    return keep_confidence >= ML_OVERRIDE_THRESHOLD and keep_prob >= ML_OVERRIDE_THRESHOLD


def is_garbage(text: str) -> bool:
    """Check if text matches garbage patterns."""
    text_lower = text.lower().strip()

    # Too short
    if len(text_lower) < 20:
        return True

    # Matches garbage pattern
    for pattern in GARBAGE_PATTERNS:
        if pattern.search(text_lower):
            return True

    # Generic scaffold content without deal/people hints
    if any(p.search(text_lower) for p in SITE_SCAFFOLD_PATTERNS):
        if not _has_deal_or_people_hints(text_lower):
            return True

    # Portfolio list noise (company lists without any deal/people evidence)
    if any(p.search(text_lower) for p in PORTFOLIO_LIST_NOISE_PATTERNS):
        if not _has_deal_or_people_hints(text_lower) and not _has_amount(text_lower):
            # Short or list-style entries are not actionable signals
            if "|" in text_lower or len(text_lower) < 90 or _RE_INVESTIMENTI_PORTFOLIO.search(text_lower):
                return True

    # Low-value announcements (reports, awards, events, interviews) without deal/people hints
    if any(p.search(text_lower) for p in LOW_VALUE_ANNOUNCEMENT_PATTERNS):
        if not _has_deal_or_people_hints(text_lower):
            return True

    # Portfolio section headers (fund-internal identifiers, not company names)
    # e.g. "INVESTIMENTI GAPEF 3 TFM Automotive&Industry", "REALIZZATE FONDO Q2 Fine Sounds"
    if re.match(
        r"^(?:investimenti|realizzate|realizzati|operazioni|partecipazioni)\s+(?:fondo|del\s+fondo|gapef|[a-z]+\s+\d)",
        text_lower,
    ):
        return True

    # Generic portfolio placeholders in deal/exit slots
    m = re.search(r"\bnew (?:portfolio )?(?:investment|exit):?\s*(.+)$", text_lower, re.IGNORECASE)
    if m:
        target = m.group(1).strip()
        if any(p.search(target) for p in GENERIC_PORTFOLIO_TARGET_PATTERNS):
            return True

    return False


def calculate_quality_score(
    signal: dict,
    raw_title: str | None = None,
    raw_summary: str | None = None,
    raw_text: str | None = None,
) -> int:
    """Calculate a quality score (0-100) for a signal."""
    score = 50  # Base score

    # Get text to analyze
    summary = raw_summary if raw_summary is not None else (signal.get("enriched_summary") or signal.get("what_changed") or signal.get("title") or "")
    title = raw_title if raw_title is not None else (signal.get("title") or summary)
    text = raw_text if raw_text is not None else f"{title} {summary}".lower()

    # Drop extraction-only portfolio list items early
    # But trust portfolio changes from italy_focused funds with core signal types
    if _is_portfolio_extraction_only(signal, text):
        fund_scope = signal.get("_fund_geo_scope", "")
        signal_type = signal.get("signal_type", "")
        # Even for trusted Italian funds, reject section headers and generic names
        company_name = _extract_portfolio_company_name(signal, summary, title)
        if company_name and _is_generic_portfolio_name(company_name):
            return 0
        # Also reject portfolio section headers via is_garbage
        if is_garbage(text):
            return 0
        _core_portfolio_types = {
            "deal_announced", "exit_announced", "fundraise_announced",
            "fundraise_closed", "fund_launch",
        }
        if fund_scope == "italy_focused" and signal_type in _core_portfolio_types:
            return 88  # Trust portfolio changes from Italian funds (confirmed transactions)
        # Europe-wide funds: trust portfolio changes when company name has Italian markers
        if fund_scope == "europe_wide" and signal_type in _core_portfolio_types:
            name_text = f"{company_name or ''} {title}".lower()
            if _mentions_italy(name_text):
                return 88
        return 0
    # Drop extraction-only team lists early
    if _is_team_extraction_only(signal):
        return 0

    # Check for garbage
    if is_garbage(text):
        return 0

    # Signal type bonuses
    signal_type = signal.get("signal_type", "")
    type_scores = {
        "deal_announced": 15,
        "exit_announced": 15,
        "fundraise_announced": 10,
        "fundraise_closed": 15,
        "fund_launch": 10,
        "people_move": 10,
        "partnership": 8,
        "report": 5,
        "portfolio_update": 8,
        "job_posting": 8,
        "website_change": -5,
        "other": -10,
    }
    score += type_scores.get(signal_type, 0)

    # CAREERS page signals can be valuable (esp. investment roles)
    page_category = (signal.get("page_category") or "").upper()
    if page_category == "CAREERS":
        if signal_type == "job_posting":
            score += 5
        else:
            score -= 10
    if page_category == "NEWS" and signal_type == "other":
        score -= 10
    if page_category == "NEWS":
        score += 5
    if page_category == "TEAM" and signal_type == "people_move":
        score += 5
        if _is_bulk_team_extraction(signal, text):
            score -= 30
        match = TEAM_EXTRACTION_RE.search(signal.get("diff_summary") or "")
        if match:
            try:
                count = int(match.group(1))
            except ValueError:
                count = None
            if count is not None and count <= MID_TEAM_EXTRACTION_THRESHOLD:
                if (
                    _is_senior_title(summary)
                    or _is_senior_title(title)
                    or _has_named_people(summary)
                    or _has_named_people(title)
                    or _RE_PEOPLE_TITLE.search(text)
                ):
                    score += 10
    if page_category == "PORTFOLIO":
        if _has_deal_or_people_hints(text) or _has_amount(text):
            if signal_type in {"deal_announced", "exit_announced"}:
                score += 5
        else:
            score -= 20
        if re.search(r"new portfolio company detected via extraction", (signal.get("diff_summary") or ""), re.IGNORECASE):
            score += 12

    # Penalize low-evidence portfolio list items (static lists)
    if _is_portfolio_list_item(signal, text, summary, title):
        score -= 35
    if _is_sector_only_listing_text(text):
        if not (_has_deal_or_people_hints(text) or _has_amount(text)):
            if page_category == "PORTFOLIO":
                score -= 30
            elif page_category != "NEWS":
                score -= 15  # lighter penalty for non-portfolio, non-news pages

    # High-value keywords
    for pattern, bonus in HIGH_VALUE_KEYWORDS:
        if pattern.search(text):
            score += bonus

    # Low-value patterns
    for pattern, penalty in LOW_VALUE_PATTERNS:
        if pattern.search(text):
            score += penalty  # penalty is negative

    # Has specific company name (capitalized words that aren't common)
    if _RE_COMPANY_LEGAL_SUFFIX.search(summary):
        score += 20

    # Extracted entities boost
    entities = signal.get("extracted_entities") or {}
    companies = entities.get("companies") or []
    people = entities.get("people") or []
    if companies:
        score += min(10, 5 + len(companies))
        if page_category == "PORTFOLIO":
            score += 6
    if people and signal_type == "people_move":
        score += 5

    # Has date — reward real published_at more than just observed_at
    if signal.get("enriched_date") or signal.get("published_at"):
        score += 10
    elif signal.get("observed_at"):
        # Only observed_at (no published date) — less reliable timestamp
        score += 3

    # Confidence bonus
    confidence = signal.get("enrichment_confidence", "")
    if confidence == "high":
        score += 10
    elif confidence == "low":
        score -= 10

    # Source bonus - fund-specific sources are better than generic
    source = signal.get("source_name", "")
    if source != "Website Monitor" and "SGR" in source:
        score += 5
    source_url = signal.get("source_url", "") or ""
    if source_url:
        if source_url.lower().endswith(".pdf"):
            score += 3
        if any(tok in source_url.lower() for tok in ("/news", "/press", "comunicato", "press")):
            score += 3

    # Relevance score boost (0.35 baseline)
    relevance = signal.get("relevance_score")
    if isinstance(relevance, (int, float)):
        score += max(0, min(10, int((relevance - 0.35) * 20)))

    # Italy/EU relevance boost
    if signal.get("italy_relevant") is True:
        score += 5
    elif _mentions_italy(text) or _mentions_europe(text):
        score += 3

    # Evidence boosts (deal strength)
    if _has_amount(text):
        score += 10
    if _has_deal_keyword(text) and _has_entity(signal, summary):
        score += 10
    elif _has_deal_keyword(text):
        score += 5
    if _news_evidence_score(signal, text, summary) >= 3:
        score += 8

    # People move relevance
    if signal_type == "people_move":
        if _is_senior_title(summary) or _is_senior_title(title):
            score += 10
        else:
            score -= 5

    # Penalize thin summaries without deal/people hints
    if len(summary.strip()) < 35 and not _has_deal_or_people_hints(text):
        score -= 15

    # Historical signals without concrete deal info get extra penalty
    title = signal.get("title", "")
    if title.startswith("Historical:"):
        has_deal_keywords = _RE_HISTORICAL_DEAL_KEYWORDS.search(text)
        if not has_deal_keywords:
            score -= 20

    # Generic page updates with no specific content
    if _RE_WEBSITE_UPDATE_PAGE.search(title):
        score -= 15

    # Portfolio company operational news (portfolio_update) should cap at 85
    # These are lower-value than fund-level transactions
    if signal_type == "portfolio_update":
        score = min(score, 85)

    # Job postings for non-senior roles cap at 82
    if signal_type == "job_posting":
        if not _is_senior_title(summary) and not _is_senior_title(title):
            score = min(score, 82)

    # Stale signal penalty — signals older than 24 months are always filtered out.
    # A signal re-detected in 2026 with published_at=2023 is stale regardless of its
    # evidence quality: the deal is real but it's historical record, not fresh news.
    # Evidence score does NOT grant a softer penalty — there is no "soft" path.
    # Root cause of stale re-detection: CMS URL reorganisation (e.g. Odoo regenerating
    # /web/content/{id}/ paths) makes the monitor treat historical articles as new.
    _pub_date = signal.get("published_at") or signal.get("enriched_date")
    if _pub_date and isinstance(_pub_date, str):
        try:
            from datetime import datetime, timezone as _tz
            _pub_dt = datetime.fromisoformat(_pub_date.replace("Z", "+00:00"))
            if _pub_dt.tzinfo is None:
                _pub_dt = _pub_dt.replace(tzinfo=_tz.utc)
            _age_months = (datetime.now(_tz.utc) - _pub_dt).days / 30.4
            if _age_months > 24:
                score -= 25  # Hard penalty: always push below MIN_QUALITY_SCORE threshold
        except (ValueError, TypeError):
            pass

    # Italian title penalty — signal title appears untranslated (title_original is absent/empty,
    # meaning translation was never attempted or the translator skipped it). Signals with 2+
    # Italian-specific content words in a short title (≤15 words) are likely untranslated Italian.
    # Push them below the quality threshold so they don't surface to end users.
    # Note: this is a fallback for translation failures. The primary fix is in translate_signals.py.
    _title_for_it_check = signal.get("title") or ""
    if not signal.get("title_original") and len(_title_for_it_check.split()) <= 15:
        _it_word_count = len(re.findall(
            r"\b(?:tratta|trattano|acquista|acquisto|acquistano|investendo|"
            r"controllata|controllato|controllati|controllate|"
            r"maggioranza|venduta|venduto|ceduta|ceduto|"
            r"sull[aei]?'?|nella\b|nell[aei']|punta\s+su[ll]?[aei]?|"
            r"lanc[ia]|nasce|avvia|avviano|avviate)\b",
            _title_for_it_check, re.IGNORECASE,
        ))
        if _it_word_count >= 2:
            score -= 30

    # Cap score
    return max(0, min(100, score))


def _load_funds_by_slug() -> dict:
    """Load fund records from db.json keyed by slug."""
    return _load_funds_by_slug_shared(DB_FILE)


# Cross-language equivalence for common PE terms (Italian → English canonical)
_CROSS_LANG_EQUIV: dict[str, str] = {
    "investe": "invests", "investimento": "investment", "investimenti": "investments",
    "rileva": "acquires", "acquisisce": "acquires", "acquisizione": "acquisition",
    "cede": "sells", "vendita": "sale", "venduto": "sold", "venduta": "sold",
    "chiude": "closes", "raccolta": "fundraising", "raccoglie": "raises",
    "lancio": "launch", "nasce": "launches", "lancia": "launches",
    "fondo": "fund", "fondi": "funds",
    "nuovo": "new", "nuova": "new", "nuovi": "new",
    "operazione": "deal", "accordo": "agreement",
    "milioni": "million", "miliardi": "billion",
}


def _normalize_words_cross_lang(words: set[str]) -> set[str]:
    """Normalize word set through cross-language equivalence mapping."""
    return {_CROSS_LANG_EQUIV.get(w, w) for w in words}


# Common PE/VC structural words stripped from titles before dedup overlap calculation.
# These inflate overlap between titles from the same fund (e.g. "IGI Private Equity"
# appearing in every title makes different deals look like duplicates).
# Includes common Italian PE verbs and function words that appear in every deal title
# (e.g. "rileva la maggioranza di X" vs "rileva la maggioranza di Y").
_DEDUP_STRUCTURAL_WORDS = {
    # Fund type words
    "sgr", "capital", "partners", "group", "investimenti", "investment",
    "private", "venture", "fondo", "fund", "equity",
    # Italian PE transaction verbs (appear in every deal title from same fund)
    "rileva", "rilevano", "acquisisce", "acquisizione", "investe", "investimento",
    "maggioranza", "controllo", "entra", "quota", "nuovo", "nuova", "nuovi",
    # Italian function words
    "la", "il", "lo", "di", "del", "della", "dello", "dei", "degli", "delle",
    "da", "per", "con", "un", "una", "uno", "in", "nel", "nella", "nel",
    "al", "alla", "allo", "ai", "e",
    # English function words
    "the", "of", "in", "for", "and", "to", "a", "an", "its", "with", "from",
    "new", "announces", "announcement",
}


def _semantic_dedup(signals: list[dict]) -> list[dict]:
    """Suppress near-duplicate signals about the same deal from different news sources.

    Within the same fund, if two signals share >=50% of title words (or >=40% within 3 days)
    and are within 7 days of each other, keep only the one with the higher quality score.
    Cross-language equivalence is applied to catch IT/EN duplicates.
    Fund name words and common PE/VC structural words are stripped before computing
    overlap to prevent false dedup of different deals from the same fund.
    """
    # Group signals by fund_slug
    by_fund: dict[str, list[dict]] = {}
    for s in signals:
        slug = s.get("fund_slug", "")
        by_fund.setdefault(slug, []).append(s)

    result = []
    suppressed_ids: set[str] = set()

    for slug, fund_signals in by_fund.items():
        if len(fund_signals) <= 1:
            result.extend(fund_signals)
            continue

        # Words to strip from titles before overlap: fund name words + structural PE/VC terms.
        # This prevents fund names like "IGI Private Equity" from inflating overlap between
        # completely different deals.
        fund_name_words = (
            set(slug.replace("-", " ").split()) | _DEDUP_STRUCTURAL_WORDS
            if slug
            else _DEDUP_STRUCTURAL_WORDS
        )

        # Sort by quality score descending — keep highest quality version
        fund_signals.sort(key=lambda s: s.get("quality_score", 0), reverse=True)
        # Each entry: (signal, words_nf, words_nf_xl, date) — pre-computed for O(1) access
        kept: list[tuple[dict, set, set, object]] = []

        for sig in fund_signals:
            sig_id = sig.get("id", "")
            if sig_id in suppressed_ids:
                continue

            title_norm = _normalize_for_dedupe(sig.get("title") or "")
            title_words = set(title_norm.split())
            if len(title_words) < 3:
                kept.append((sig, set(), set(), None))
                continue

            # Strip fund name / structural words for overlap calculation
            title_words_nf = title_words - fund_name_words
            title_words_nf_xl = _normalize_words_cross_lang(title_words_nf)

            sig_date = _parse_signal_date(
                sig.get("published_at") or sig.get("observed_at") or sig.get("created_at")
            )

            is_dup = False
            for _, ex_words_nf, ex_words_nf_xl, ex_date in kept:
                if len(ex_words_nf) == 0:
                    continue

                # Check word overlap using fund-name-stripped versions to avoid
                # false dedup of different deals from the same fund
                overlap_native = len(title_words_nf & ex_words_nf)
                overlap_xl = len(title_words_nf_xl & ex_words_nf_xl)
                overlap = max(overlap_native, overlap_xl)
                shorter_len = min(len(title_words_nf), len(ex_words_nf))
                if shorter_len == 0:
                    continue
                overlap_ratio = overlap / shorter_len

                # Check date proximity
                day_diff = None
                if sig_date and ex_date:
                    day_diff = abs((sig_date - ex_date).days)

                # Tighter threshold for close dates (within 3 days): 40% overlap
                if day_diff is not None and day_diff <= 3 and overlap_ratio >= 0.4:
                    is_dup = True
                    suppressed_ids.add(sig_id)
                    break

                # Standard threshold: 50% overlap within 7 days
                if overlap_ratio >= 0.5:
                    if day_diff is not None and day_diff <= 7:
                        is_dup = True
                        suppressed_ids.add(sig_id)
                        break
                    elif day_diff is None:
                        # No date to compare — still suppress if overlap is high
                        if overlap_ratio >= 0.6:
                            is_dup = True
                            suppressed_ids.add(sig_id)
                            break

            if not is_dup:
                kept.append((sig, title_words_nf, title_words_nf_xl, sig_date))

        result.extend(sig for sig, _, _, _ in kept)

    return result


def _cross_fund_url_dedup(signals: list[dict]) -> list[dict]:
    """Suppress cross-fund duplicate signals sourced from the exact same URL.

    When the same article is matched to multiple funds (e.g. a round covered by two
    co-investing funds), keep only the highest-quality signal. The winning signal gets a
    `co_fund_slugs` list with the slugs that were merged in, so context is preserved.

    Exact source_url match only — title-similarity dedup is handled by _semantic_dedup.
    """
    from collections import defaultdict
    by_url: dict[str, list[dict]] = defaultdict(list)
    no_url: list[dict] = []

    for s in signals:
        url = (s.get("source_url") or "").strip().lower()
        if url:
            by_url[url].append(s)
        else:
            no_url.append(s)

    result = list(no_url)
    suppressed = 0

    for url, group in by_url.items():
        if len(group) == 1:
            result.append(group[0])
            continue
        # Keep the signal with highest quality_score; tie-break by deal type priority
        _TYPE_PRIORITY = {"exit_announced": 5, "deal_announced": 4, "fund_launch": 3,
                          "fundraise_closed": 3, "fundraise_announced": 2, "people_move": 1}
        group.sort(
            key=lambda s: (s.get("quality_score", 0), _TYPE_PRIORITY.get(s.get("signal_type", ""), 0)),
            reverse=True,
        )
        winner = group[0]
        losers = group[1:]
        # Attach co-investor fund slugs to the winner so the UI can reference all funds
        co_slugs = [s.get("fund_slug") for s in losers if s.get("fund_slug") and s.get("fund_slug") != winner.get("fund_slug")]
        if co_slugs:
            existing = winner.get("co_fund_slugs") or []
            winner["co_fund_slugs"] = list({*existing, *co_slugs})
        result.append(winner)
        suppressed += len(losers)

    if suppressed:
        print(f"  Cross-fund URL dedup: suppressed {suppressed} duplicate signals (same source URL, different funds)")
    return result


def _cross_page_dedup(signals: list[dict]) -> list[dict]:
    """Suppress PORTFOLIO signals when a NEWS signal covers the same company for the same fund."""
    # Build index: fund_slug → set of normalized company names from NEWS signals
    news_companies: dict[str, set[str]] = {}
    for s in signals:
        if (s.get("page_category") or "").upper() != "NEWS":
            continue
        fund = s.get("fund_slug", "")
        entities = s.get("extracted_entities") or {}
        for company in entities.get("companies", []):
            news_companies.setdefault(fund, set()).add(normalize_company_name(company))
        # Also check title for company names in deal/exit signals
        if s.get("signal_type") in ("deal_announced", "exit_announced"):
            title = s.get("title", "")
            if title:
                news_companies.setdefault(fund, set()).add(normalize_company_name(title))

    # Filter: suppress PORTFOLIO signals that match NEWS companies
    result = []
    suppressed = 0
    for s in signals:
        if (s.get("page_category") or "").upper() == "PORTFOLIO":
            fund = s.get("fund_slug", "")
            fund_news = news_companies.get(fund, set())
            if fund_news:
                entities = s.get("extracted_entities") or {}
                portfolio_companies = entities.get("companies", [])
                if any(normalize_company_name(c) in fund_news for c in portfolio_companies):
                    suppressed += 1
                    continue  # Drop this PORTFOLIO signal
        result.append(s)

    if suppressed:
        print(f"  Cross-page dedup: suppressed {suppressed} PORTFOLIO signals covered by NEWS")
    return result


def main():
    print("Signal Quality Filter")
    print("=" * 50)

    # Load valid fund slugs from database
    slug_normalizer = get_slug_normalizer()
    valid_slugs = slug_normalizer.canonical_slugs
    print(f"Valid funds in database: {len(valid_slugs)}")
    if slug_normalizer.invalid_slugs:
        print(f"Invalid fund slugs (excluded): {len(slug_normalizer.invalid_slugs)}")
    if slug_normalizer.alias_map:
        print(f"Fund slug aliases loaded: {len(slug_normalizer.alias_map)}")

    funds_by_slug = _load_funds_by_slug()

    # Build misattribution detection list from db.json (auto-updates when funds change)
    global KNOWN_FUND_NAMES
    KNOWN_FUND_NAMES = _build_known_fund_names(funds_by_slug)

    classifier = get_signal_classifier() if get_signal_classifier else None
    if classifier is None:
        print("ML classifier: not available (using rules only)")
    else:
        print(f"ML classifier: enabled (keep decisions={'on' if ML_USE_KEEP else 'off'})")

    # Load signals
    if not INPUT_FILE.exists():
        print(f"Error: No signal file found at {INPUT_FILE}")
        return

    print(f"Loading from: {INPUT_FILE.name}")

    with open(INPUT_FILE) as f:
        data = json.load(f)

    signals = data.get("signals", [])
    print(f"Total signals: {len(signals)}")

    # Score and filter
    filtered = []
    removed_duplicates = 0
    resolved_duplicate_ids = 0
    removed_garbage = 0
    removed_low_quality = 0
    removed_support_only = 0
    removed_junior_non_italy = 0
    removed_geo_irrelevant = 0
    removed_misattributed = 0
    removed_orphan_fund = 0
    removed_strict_gate = 0
    removed_invalid_fund = 0
    removed_ml = 0
    kept_ml_override = 0
    ml_type_overrides = 0
    orphan_slugs: set[str] = set()
    score_distribution = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    confidence_distribution = {"high": 0, "medium": 0, "low": 0}
    seen_keys: set[str] = set()
    seen_ids: set[str] = set()
    seen_fund_urls: set[str] = set()  # fund_slug::source_url — catches title-variant duplicates

    # Prefer the most recent version when suppressing duplicates
    signals = sorted(
        signals,
        key=lambda s: s.get("observed_at") or s.get("created_at") or "",
        reverse=True,
    )

    for signal in signals:
        original_slug = (signal.get("fund_slug") or "").strip()
        normalization = slug_normalizer.normalize(
            slug=signal.get("fund_slug"),
            fund_id=signal.get("fund_id"),
            name=signal.get("fund_name") or signal.get("source_name"),
            source_url=signal.get("source_url"),
        )
        fund_slug = normalization.slug or ""
        if normalization.reason == "invalid":
            removed_invalid_fund += 1
            continue
        if not fund_slug:
            removed_orphan_fund += 1
            if original_slug:
                orphan_slugs.add(original_slug)
            continue
        if fund_slug != original_slug:
            signal = dict(signal)
            signal["fund_slug"] = fund_slug

        # Reject signals for funds not in the database
        if valid_slugs and fund_slug and fund_slug not in valid_slugs:
            removed_orphan_fund += 1
            orphan_slugs.add(fund_slug)
            continue

        # Look up fund object from db.json (used by reclassifier + misattribution)
        fund = funds_by_slug.get(fund_slug) if fund_slug else None

        # Preserve raw text for scoring before we clean labels/spacing
        raw_title = (signal.get("title") or "").strip()
        raw_summary = (
            signal.get("enriched_summary")
            or signal.get("what_changed")
            or raw_title
            or ""
        )
        raw_text = f"{raw_title} {raw_summary}".lower().strip()

        # Reclassify generic signals into useful categories (use raw text)
        signal["signal_type"] = _reclassify_signal_type(signal, f"{raw_title} {raw_summary}", fund=fund)

        # Apply shared corrections (fashion campaigns, editorial format, outsourcing,
        # restructuring, "sells stake" → exit, etc.) — single source of truth
        _corr_text = f"{raw_title} {raw_summary}".lower()
        _corr_title = raw_title.lower()
        was_universal_other_demotion = False
        _corr_demotion = apply_universal_demotions(_corr_text, _corr_title)
        if _corr_demotion is not None:
            signal["signal_type"] = _corr_demotion
            if _corr_demotion == "other":
                was_universal_other_demotion = True
        else:
            _corr_type = apply_type_corrections(
                signal["signal_type"], _corr_text, _corr_title,
                (signal.get("page_category") or "").upper(),
                (signal.get("diff_summary") or "").lower(),
            )
            if _corr_type != signal["signal_type"]:
                signal["signal_type"] = _corr_type

        # Clean read-time artifacts and other low-signal noise
        signal = _clean_signal_fields(signal)

        # Suppress exact duplicates after cleaning
        dedupe_key = _signal_dedupe_key(signal)
        if dedupe_key in seen_keys:
            removed_duplicates += 1
            continue
        seen_keys.add(dedupe_key)

        # Suppress same-URL duplicates within a fund (catches title-variant dupes)
        # Only for article-like URLs — skip listing pages where many signals share one URL
        source_url = (signal.get("source_url") or "").strip().rstrip("/")
        if source_url and fund_slug:
            url_path = urlparse(source_url).path.strip("/")
            last_segment = url_path.rsplit("/", 1)[-1].lower() if url_path else ""
            listing_pages = {"news", "newsroom", "newsroom.page", "news-insights", "portfolio",
                             "investment", "investments", "team", "people", "press", "media", "blog"}
            is_listing = last_segment in listing_pages or not last_segment
            if not is_listing:
                fund_url_key = f"{fund_slug}::{source_url}"
                if fund_url_key in seen_fund_urls:
                    removed_duplicates += 1
                    continue
                seen_fund_urls.add(fund_url_key)

        signal, id_changed = _ensure_unique_signal_id(signal, dedupe_key, seen_ids)
        if id_changed:
            resolved_duplicate_ids += 1

        # Reject misattributed signals (title names a different fund)
        if _is_misattributed_signal(signal, fund=fund):
            removed_misattributed += 1
            continue

        # Reject signals with titles too short to be useful
        clean_title = (signal.get("title") or "").strip()
        if len(clean_title) < 15:
            removed_garbage += 1
            continue

        # Reject truncated titles ending with dangling prepositions
        # BUT if what_changed has much richer content, use that instead
        if re.search(r"\s(?:with|in|of|for|and|to|the|a|an|di|del|della|con|per|che|un|una)\s*$", clean_title, re.IGNORECASE):
            what_changed = (signal.get("what_changed") or "").strip()
            if len(what_changed) > len(clean_title) * 2 and len(what_changed) > 40:
                # Title is truncated but what_changed has full text — fix the title
                signal["title"] = what_changed[:220]
            else:
                removed_garbage += 1
                continue

        # Reject generic/useless titles that provide no information
        title_lower = clean_title.lower()
        if title_lower in {
            "committed to a sustainable future",
            "our team", "our portfolio", "our investments",
            "about us", "contact", "home", "news",
        } or re.match(r"^(new team members?|team update|people move):\s*$", title_lower):
            removed_garbage += 1
            continue

        # Reject team baseline signals: TEAM page listing existing members (not actual moves)
        page_type = ((signal.get("page_type") or signal.get("page_category") or "")).upper()
        sig_type = signal.get("signal_type") or ""
        if page_type in ("TEAM", "TEAM_LIST"):
            what = signal.get("what_changed") or ""
            paren_count = len(re.findall(r"\([^)]+\)", what))
            # Pattern 1: multiple people with roles in parentheses (people_move only)
            if sig_type == "people_move" and paren_count >= 2:
                removed_garbage += 1
                continue
            # Pattern 2: title ends with "(+N more)" — team listing from baseline scrape
            # Check regardless of signal_type since reclassifier may have changed it
            if re.search(r"\(\+\d+ more\)", clean_title):
                removed_garbage += 1
                continue
            # Pattern 3: static TEAM bios/corporate blurbs are not discrete move signals.
            if (
                (
                    _is_team_role_profile_line(clean_title, "TEAM")
                    or _is_role_opening_title(clean_title)
                    or _is_team_static_description(clean_title, what, "TEAM")
                )
                and not _has_people_transition_verb(f"{clean_title} {what}".lower())
            ):
                removed_garbage += 1
                continue

        # Reject "Historical:" prefix signals (archived page content, not current events)
        what_changed_raw = (signal.get("what_changed") or "").strip()
        if re.match(r"^historical:", what_changed_raw, re.IGNORECASE):
            removed_garbage += 1
            continue

        # Reject internal dealing / regulatory notices
        combined_text = f"{clean_title} {what_changed_raw}".lower()
        if re.search(r"\binternal dealing\b|\bsoggetto rilevante\s+mar\b", combined_text, re.IGNORECASE):
            removed_garbage += 1
            continue

        # Reject misextracted team members (non-person names like events, sports teams)
        if re.search(r"\b(?:olimpiad[ie]|snowboard|squadra\s+regional[ei]|campionat[oi])\b", combined_text, re.IGNORECASE):
            removed_garbage += 1
            continue

        # Filter support-staff-only people_move signals
        signal = _filter_support_roles_from_signal(signal)
        if signal is None:
            removed_support_only += 1
            continue

        # Filter junior non-Italy people from people_move signals
        signal = _filter_junior_non_italy_people(signal)
        if signal is None:
            removed_junior_non_italy += 1
            continue

        # Filter out signals that are not Europe/Italy relevant
        fund = funds_by_slug.get(fund_slug) if fund_slug else None
        fund_scope = _fund_geo_scope(fund, fund_slug)
        signal["_fund_geo_scope"] = fund_scope  # store for use in strict gate

        # Backfill italy_relevant for signals missing the field (e.g. from deprecated generators)
        if signal.get("italy_relevant") is None:
            backfill_text = " ".join([
                signal.get("title", ""),
                signal.get("what_changed", ""),
                signal.get("diff_summary", ""),
            ])
            if _mentions_italy(backfill_text):
                signal["italy_relevant"] = True
            elif _mentions_non_eu_geo(backfill_text):
                signal["italy_relevant"] = False
            elif _mentions_europe(backfill_text):
                signal["italy_relevant"] = None  # EU but not specifically Italy — leave unknown
            else:
                signal["italy_relevant"] = False  # no geo evidence → default to False

        # Negative geography correction: if italy_relevant=True was set as an
        # upstream default (relevance_score=0, no relevance_reasons) AND the text
        # explicitly mentions non-Italian EU geography WITHOUT mentioning Italy,
        # flip to False.  This catches signals like "Proxima Fusion, €2B, Bavaria"
        # from RSS aggregators that default italy_relevant=True for all articles.
        if signal.get("italy_relevant") is True:
            _rel_score = signal.get("relevance_score")
            _rel_reasons = signal.get("relevance_reasons") or []
            _has_evidence = (isinstance(_rel_score, (int, float)) and _rel_score > 0) or len(_rel_reasons) > 0
            if not _has_evidence:
                _neg_geo_text = " ".join([
                    signal.get("title", ""),
                    signal.get("what_changed", ""),
                    signal.get("diff_summary", ""),
                ])
                if _NON_ITALY_EU_COUNTRIES_RE.search(_neg_geo_text) and not _mentions_italy(_neg_geo_text):
                    signal["italy_relevant"] = False
                elif _mentions_non_eu_geo(_neg_geo_text) and not _mentions_italy(_neg_geo_text):
                    signal["italy_relevant"] = False

        # For italy_focused funds, override False → True (the fund is Italian by definition)
        # Core signal types (deals, exits, fundraises, fund launches) are ALWAYS Italy-relevant
        # for Italian funds — incidental mentions of foreign cities shouldn't block this
        if signal.get("italy_relevant") is False and fund_scope == "italy_focused":
            if signal.get("signal_type") in CORE_GEO_TYPES:
                signal["italy_relevant"] = True
            else:
                backfill_check = " ".join([
                    signal.get("title", ""),
                    signal.get("what_changed", ""),
                    signal.get("diff_summary", ""),
                ])
                if not _NON_ITALY_EU_COUNTRIES_RE.search(backfill_check):
                    signal["italy_relevant"] = True

        signal = _boost_italy_relevance(signal, fund_scope)

        # Correct italy_relevant=False for signals with Europe/Italy text evidence
        # The initial relevance scorer may miss EMEA, Italian names, etc.
        if signal.get("italy_relevant") is False:
            geo_text = " ".join([
                signal.get("title", ""),
                signal.get("what_changed", ""),
                signal.get("diff_summary", ""),
            ])
            if _mentions_italy(geo_text):
                signal["italy_relevant"] = True
            elif _mentions_europe(geo_text):
                signal["italy_relevant"] = True  # Europe-relevant = relevant for Italian PE audience
            # Italian name patterns in people_move signals
            elif signal.get("signal_type") == "people_move" and _has_italian_name(geo_text):
                signal["italy_relevant"] = True

        if not _is_geo_relevant_signal(signal, fund_scope, fund):
            removed_geo_irrelevant += 1
            continue

        # ML classification (keep/type) with confidence thresholds
        ml_result = None
        if classifier is not None:
            ml_result = classifier.predict(signal, raw_title=raw_title or None, raw_summary=raw_summary or None)
            signal["ml_keep"] = ml_result.keep
            signal["ml_keep_prob"] = round(ml_result.keep_prob, 3)
            signal["ml_keep_confidence"] = round(ml_result.keep_confidence, 3)
            signal["ml_keep_confident"] = ml_result.keep_confident
            signal["ml_type"] = ml_result.type_label
            signal["ml_type_prob"] = round(ml_result.type_prob, 3)
            signal["ml_type_confident"] = ml_result.type_confident
            signal["ml_confidence"] = round(ml_result.confidence, 3)

            if ml_result.type_confident and map_type_to_signal_type is not None:
                new_type = map_type_to_signal_type(
                    ml_result.type_label,
                    signal.get("signal_type") or "",
                )
                if new_type != signal.get("signal_type"):
                    ml_type_overrides += 1
                signal["signal_type"] = new_type

            if ML_USE_KEEP and ml_result.keep_confident and not ml_result.keep:
                removed_ml += 1
                continue

        # Post-ML correction: event/conference attendance — ML may override our demotion
        post_ml_text = (raw_title + " " + raw_summary).lower()
        demoted_to_other_by_editorial = was_universal_other_demotion
        if (
            _RE_EVENT_ATTENDANCE.search(post_ml_text)
            or _RE_EVENT_RECAP_ITALIAN.search(post_ml_text)
            or re.search(r"\b\d+(?:st|nd|rd|th)?\s+annual\b.{0,80}\b\d{1,2}/\d{1,2}/\d{4}\b", post_ml_text)
        ):
            signal["signal_type"] = "other"
            demoted_to_other_by_editorial = True

        # Post-ML correction: job postings — ML often misclassifies hiring notices as exits/deals
        # Italian selection procedure language is unambiguous
        if signal.get("signal_type") != "job_posting" and _matches_any(JOB_POSTING_PATTERNS, post_ml_text):
            if not _matches_any(DEAL_CLASSIFY_PATTERNS, post_ml_text) and not _matches_any(EXIT_CLASSIFY_PATTERNS, post_ml_text):
                signal["signal_type"] = "job_posting"

        # Post-ML: market review reports misclassified by ML as deal_announced.
        # ML sees "M&A" / "acquisition" vocabulary in review/report articles and fires
        # deal_announced at high confidence. _RE_REPORT with the market-review patterns
        # is the authoritative override.
        if signal.get("signal_type") == "deal_announced" and _RE_REPORT.search(post_ml_text):
            signal["signal_type"] = "report"

        # Post-ML: re-apply rule-based rescue for signals ML demoted to 'other'.
        # ML may override correct rule-based classifications (fund_launch, report, debt_financing,
        # people_move, deal_announced). Re-apply apply_type_corrections("other") which has tight,
        # high-confidence patterns. Skip if a universal demotion or editorial check already set
        # "other" intentionally (demoted_to_other_by_editorial = True).
        if signal.get("signal_type") == "other" and not demoted_to_other_by_editorial:
            _post_ml_rescued = apply_type_corrections(
                "other",
                post_ml_text,
                (signal.get("title") or "").lower(),
                (signal.get("page_category") or "").upper(),
                (signal.get("diff_summary") or "").lower(),
            )
            if _post_ml_rescued != "other":
                signal["signal_type"] = _post_ml_rescued

        # Post-ML correction: fund_launch misclassifications
        # ML often overrides the reclassifier's correct decision — apply same guards
        if signal.get("signal_type") == "fund_launch":
            title_lower = (signal.get("title") or "").lower()
            post_ml_text2 = (raw_title + " " + raw_summary).lower()
            # Check fund vehicle language in TITLE only (not concatenated text)
            # Concatenating title + what_changed creates false matches when they repeat
            # e.g. "Fondo X launches partnership [News: Fondo X launches partnership]"
            has_fund_vehicle = bool(_RE_FUND_LAUNCH_STRICT.search(title_lower))
            # Merger/fusion → deal_announced (not fund_launch)
            # e.g. "Al via la fusione tra Smart Capital, Crowd Fund Me..." — "al via" + "Fund" in company name
            if re.search(r"\b(?:fusion[ei]|merger|fonde|si\s+fondono)\b", post_ml_text2):
                signal["signal_type"] = "deal_announced"
            # Fund-level raise language takes priority over debt for debt funds.
            elif _RE_FUND_LEVEL_FUNDRAISE.search(post_ml_text2):
                if _RE_FUNDRAISE_CLOSING.search(post_ml_text2) or _RE_CHIUDE_FONDO.search(post_ml_text2):
                    signal["signal_type"] = "fundraise_closed"
                else:
                    signal["signal_type"] = "fundraise_announced"
            # Bond issuance / refinancing → debt_financing
            elif _RE_BOND_ISSUANCE.search(post_ml_text2) and not has_fund_vehicle and not _RE_FUND_LEVEL_FUNDRAISE.search(post_ml_text2):
                signal["signal_type"] = "debt_financing"
            # Credit facility → debt_financing
            elif _RE_CREDIT_FACILITY.search(post_ml_text2) and not has_fund_vehicle and not _RE_FUND_LEVEL_FUNDRAISE.search(post_ml_text2):
                signal["signal_type"] = "debt_financing"
            # Accelerator launch → other (strategic initiative, not a fund vehicle)
            elif _matches_any(ACCELERATOR_LAUNCH_PATTERNS, post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # Accelerator results / graduates → other
            elif _RE_ACCELERATOR_RESULTS.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # Outsourcing/procurement → other
            elif _RE_OUTSOURCING.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # Debt restructuring → other
            elif _RE_DEBT_RESTRUCTURING.search(post_ml_text2) and not has_fund_vehicle:
                if _RE_DEBT_RESTRUCTURE_CONTEXT.search(post_ml_text2) and _mentions_tagged_fund(signal, post_ml_text2):
                    signal["signal_type"] = "debt_financing"
                else:
                    signal["signal_type"] = "other"
            # LP commitment to existing fund → fundraise
            elif _RE_LP_COMMITMENT.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "fundraise_announced"
            # Regulatory communication → other
            elif _RE_REGULATORY_COMMUNICATION.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # Project financing → debt_financing (but not equity raises like aucap)
            elif _RE_PROJECT_FINANCING.search(post_ml_text2) and not _RE_BOND_EXCLUDE.search(post_ml_text2) and not _RE_FUND_LEVEL_FUNDRAISE.search(post_ml_text2):
                signal["signal_type"] = "debt_financing"
            # Ordinal/new investment → deal
            elif _RE_ORDINAL_INVESTMENT.search(post_ml_text2):
                signal["signal_type"] = "deal_announced"
            # Board/appointment → people_move (unless also fund launch)
            elif _RE_BOARD_APPOINTMENT.search(post_ml_text2) and not _RE_FUND_LAUNCH_VERBS.search(post_ml_text2):
                signal["signal_type"] = "people_move"
            # Office opening / footprint expansion → people_move
            elif _RE_OFFICE_OPENING.search(post_ml_text2) and not _matches_any(DEAL_CLASSIFY_PATTERNS, post_ml_text2):
                signal["signal_type"] = "people_move"
            # Investment verbs or "investimento da/in X" → deal
            # Guard: if a fund vehicle exists in the title, "invest in" describes the fund's
            # investment mandate (e.g. "launches X fund to invest in Y"), not a deal transaction.
            elif _RE_INVEST_VERBS.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "deal_announced"
            # Company round (startup raises money) → deal
            elif _RE_COMPANY_ROUND.search(post_ml_text2):
                signal["signal_type"] = "deal_announced"
            # Startup funding rounds → fundraise
            elif _RE_STARTUP_ROUND.search(title_lower):
                if _RE_ROUND_CLOSED.search(title_lower):
                    signal["signal_type"] = "fundraise_closed"
                else:
                    signal["signal_type"] = "fundraise_announced"
            # "Chiude la raccolta" or "chiude il fondo" → fundraise_closed
            elif _RE_CHIUDE_FONDO.search(post_ml_text2):
                signal["signal_type"] = "fundraise_closed"
            # Milestones like "superando il target" imply completed raise
            elif _RE_FUNDRAISE_MILESTONE.search(post_ml_text2):
                signal["signal_type"] = "fundraise_closed"
            # Finalized deal → deal_announced
            elif _RE_FINALIZZAT.search(post_ml_text2):
                signal["signal_type"] = "deal_announced"
            # Partnership (without acquisition verbs AND no fund vehicle language) → partnership
            # If both fund_launch and partnership patterns match, keep fund_launch
            # (launching a fund via partnership distribution is still a fund launch)
            elif _RE_PARTNERSHIP.search(post_ml_text2) and not has_fund_vehicle:
                if not _RE_PARTNERSHIP_EXCLUDE.search(post_ml_text2):
                    signal["signal_type"] = "partnership"
                else:
                    signal["signal_type"] = "deal_announced"
            # Revenue/financial results (no fund vehicle language) → other
            elif re.search(r"\b(?:ricav\w+|fatturato|revenue|risultat\w+\s+finanziar\w+|bilancio)\b", post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # Editorial/analysis content → other
            elif _RE_EDITORIAL_STRATEGY.search(post_ml_text2) and not has_fund_vehicle:
                signal["signal_type"] = "other"
            # "launches/lancia + partnership" in title → partnership (not fund_launch)
            # e.g. "Fondo X launches strategic partnership with Y"
            # Note: \bpartnership (no trailing \b) to match "partnershipwith" (extractor bug: missing space)
            elif re.search(r"\b(?:launch(?:es|ed)?|lancia|lancio)\b.{0,30}\b(?:partnership|collaborazione|accordo|alleanza)", title_lower):
                signal["signal_type"] = "partnership"
            # Historical launch reference ("launched in 2022") → other (article, not current launch)
            elif re.search(r"\blaunched?\s+in\s+20(?:1\d|2[0-4])\b", post_ml_text2):
                signal["signal_type"] = "other"
            # Catch-all: fund_launch without any fund vehicle language → re-run reclassifier
            elif not has_fund_vehicle:
                reclassified = _reclassify_signal_type(signal, raw_title + " " + raw_summary, fund=fund)
                if reclassified != "fund_launch":
                    signal["signal_type"] = reclassified
                else:
                    # Reclassifier also thinks it's fund_launch without matching vehicle patterns → other
                    signal["signal_type"] = "other"

        # Post-ML correction: partnership/other that is actually a fund_launch
        # e.g. "Blackstone launches BXEF fund" gets classified as partnership from "expanded partnership" in what_changed
        # Only promote when title has an explicit launch verb + fund vehicle (not just "Fund II" in fund name)
        if signal.get("signal_type") in {"partnership", "other", "deal_announced"}:
            title_for_fl = (signal.get("title") or "").lower()
            # Don't promote mergers/fusions back to fund_launch
            # e.g. "Al via la fusione tra Smart Capital, Crowd Fund Me" — "al via" + "Fund" = false match
            if not re.search(r"\b(?:fusion[ei]|merger|fonde|si\s+fondono)\b", title_for_fl):
                has_launch_verb_and_fund = bool(_RE_FUND_LAUNCH_STRICT.search(title_for_fl))
                # Guard: don't promote if title also has acquisition/exit verbs.
                # e.g. "Armònia Italy Fund II acquisisce PSH" — "Fund II" matches strict
                # pattern but "acquisisce" is a deal verb, not a fund launch verb.
                if (
                    has_launch_verb_and_fund
                    and not _matches_any(DEAL_CLASSIFY_PATTERNS, title_for_fl)
                    and not _matches_any(EXIT_CLASSIFY_PATTERNS, title_for_fl)
                ):
                    signal["signal_type"] = "fund_launch"

        # Post-ML correction: fundraise that is actually a company round → deal_announced
        # ML classifier often labels startup rounds as "fund" → fundraise, but from the
        # fund's perspective, investing in a startup's round IS a deal.
        if signal.get("signal_type") in ("fundraise_announced", "fundraise_closed"):
            post_ml_fundraise_text = (raw_title + " " + raw_summary).lower()
            if (
                _RE_FUNDRAISE_CLOSING.search(post_ml_fundraise_text)
                or _RE_CHIUDE_FONDO.search(post_ml_fundraise_text)
                or _RE_FUNDRAISE_MILESTONE.search(post_ml_fundraise_text)
            ):
                signal["signal_type"] = "fundraise_closed"
            elif _RE_COMPANY_ROUND.search(post_ml_fundraise_text) and not _RE_FUND_LEVEL_FUNDRAISE.search(post_ml_fundraise_text):
                signal["signal_type"] = "deal_announced"

        # Post-ML correction: exits misclassified as deal_announced
        # Strong exit verbs (sells, vende, cede) always indicate an exit
        if signal.get("signal_type") == "deal_announced":
            text_check = (raw_title + " " + raw_summary).lower()
            # Portfolio company news is NOT a fund-level deal
            if _RE_PORTFOLIO_UPDATE.search(text_check):
                signal["signal_type"] = "portfolio_update"
                demoted_to_other_by_editorial = True
            # Accelerator/program launch → fund_launch (new investment program, not a deal)
            elif _RE_ACCELERATOR_LAUNCH.search(text_check):
                signal["signal_type"] = "fund_launch"
            elif _RE_STRONG_EXIT_VERBS.search(text_check):
                title_check = (signal.get("title") or "").lower()
                buyer_cues = r"\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b|\bpotrebbero\s+essere\s+interessat\w*\b|\bvaluta\s+l[''\u2019]acqui\w+\b"
                has_explicit_seller = bool(_RE_EXPLICIT_SELLER.search(text_check))
                if not (re.search(buyer_cues, title_check) and not has_explicit_seller):
                    signal["signal_type"] = "exit_announced"
            elif _RE_CHIUDE_RACCOLTA.search(text_check):
                signal["signal_type"] = "fundraise_closed"
            # Bond issuance as primary event (piazza/colloca bond) → debt even if text mentions acquisitions
            elif re.search(r"\b(?:piazza|collocat\w+|emett\w+|emissione)\b.{0,40}\bbond\b|\bbond\b.{0,40}\b(?:piazza|collocat\w+|emett\w+|emissione)\b", text_check, re.IGNORECASE):
                signal["signal_type"] = "debt_financing"
            # Bond/debt financing misclassified as deal
            elif (_RE_BOND_ISSUANCE.search(text_check) and not _RE_BOND_EXCLUDE.search(text_check)):
                signal["signal_type"] = "debt_financing"
            elif _RE_DEBT_FINANCING_BROAD.search(text_check) and not _RE_BOND_EXCLUDE.search(text_check):
                signal["signal_type"] = "debt_financing"
            elif _RE_DEBT_RESTRUCTURING.search(text_check):
                if _RE_DEBT_RESTRUCTURE_CONTEXT.search(text_check) and _mentions_tagged_fund(signal, text_check):
                    signal["signal_type"] = "debt_financing"

        # Post-ML correction: exit_announced with buyer-perspective language → deal_announced
        if signal.get("signal_type") == "exit_announced":
            text_check_ex = (raw_title + " " + raw_summary).lower()
            title_check_ex = (signal.get("title") or "").lower()
            buyer_cues_ex = r"\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b|\bpotrebbero\s+essere\s+interessat\w*\b|\bvaluta\s+l[''\u2019]acqui\w+\b"
            has_explicit_seller_ex = bool(_RE_EXPLICIT_SELLER.search(text_check_ex) or _RE_EXITED_FROM_PORTFOLIO.search(text_check_ex))
            # Merger/fusion without explicit seller cues is not a completed exit.
            if _RE_MERGER.search(text_check_ex) and not has_explicit_seller_ex and not _RE_STRONG_EXIT_VERBS.search(text_check_ex):
                signal["signal_type"] = "deal_announced"
            # "Fund acquires X" in title = buyer, not exiter
            elif re.search(r"\bacquires?\s+\w+", title_check_ex) and not has_explicit_seller_ex:
                signal["signal_type"] = "deal_announced"
            elif re.search(buyer_cues_ex, title_check_ex):
                if not has_explicit_seller_ex:
                    signal["signal_type"] = "deal_announced"
            elif re.search(buyer_cues_ex, text_check_ex):
                if not _RE_EXIT_VERBS.search(text_check_ex):
                    signal["signal_type"] = "deal_announced"
            elif re.search(r"\b(?:agreement|accordo|intesa|convenzione)\b", text_check_ex) and not _RE_EXIT_VERBS.search(text_check_ex) and not _RE_ACQUISITION_VERBS.search(text_check_ex):
                if re.search(r"\b(?:partnership|collaborazione|gestione|manage|management|tenders?|bando)\b", text_check_ex):
                    signal["signal_type"] = "partnership"

        # Post-ML correction: partnership with investment language → deal_announced
        # Italian "partnership" often means co-investment, especially with "aumento di capitale",
        # "round da", "finalizzata la partnership" + investment amounts, "invests in", "€X M investment"
        if signal.get("signal_type") == "partnership":
            text_check_p = (raw_title + " " + raw_summary).lower()
            # Portfolio company news is not fund-level activity
            if _RE_PORTFOLIO_UPDATE.search(text_check_p):
                signal["signal_type"] = "portfolio_update"
                demoted_to_other_by_editorial = True
            elif re.search(r"\b(?:aumento\s+di\s+capitale|round\s+da|incassa|raccog\w+|investi\w+\s+(?:di|da|per|in)\s+|co[\-\s]?invest\w+|€\d+\s*[MB]\w*\s+invest\w+|\d+\s*M€?\s+invest\w+)\b", text_check_p):
                signal["signal_type"] = "deal_announced"
            elif _RE_STRONG_EXIT_VERBS.search(text_check_p):
                signal["signal_type"] = "exit_announced"

        # Post-ML correction: other with portfolio company evidence → portfolio_update
        if signal.get("signal_type") == "other":
            text_check_o = (raw_title + " " + raw_summary).lower()
            if _RE_PORTFOLIO_UPDATE.search(text_check_o):
                signal["signal_type"] = "portfolio_update"

        # Post-ML correction: people_move with interview/speech/event language → other
        # CEO/CFO mentioned in interviews or event speeches are NOT personnel changes
        if signal.get("signal_type") == "people_move":
            text_check_pm = (raw_title + " " + raw_summary).lower()
            title_check_pm = (signal.get("title") or "").lower()
            page_category_pm = (signal.get("page_category") or "").upper()
            # Static profile cards and role-opening titles are not true personnel-move events.
            if (
                (
                    _is_team_role_profile_line(title_check_pm, page_category_pm)
                    or _is_role_opening_title(title_check_pm)
                    or _is_team_static_description(title_check_pm, text_check_pm, page_category_pm)
                )
                and not _has_people_transition_verb(text_check_pm)
            ):
                signal["signal_type"] = "other"
                demoted_to_other_by_editorial = True
            elif _RE_REPORT.search(text_check_pm) and not _RE_INVEST_VERBS.search(text_check_pm):
                signal["signal_type"] = "report"
            elif re.search(r"\bintervist\w+\b|\binterview\w*\b|\bsits?\s+down\s+with\b|\breflects?\s+on\b|\bexplains?\b|\bspiega\b|\bracconta\b", text_check_pm):
                if not re.search(r"\b(?:nomin\w+|appoint\w+|hired?|joins?|joined|dimission\w+|resign\w+|leaves?)\b", text_check_pm):
                    signal["signal_type"] = "other"
                    demoted_to_other_by_editorial = True

        # Post-ML correction: partnership with interview language → other
        if signal.get("signal_type") == "partnership":
            text_check_pi = (raw_title + " " + raw_summary).lower()
            if re.search(r"\bintervist\w+\b|\binterview\w*\b|\bsits?\s+down\s+with\b|\breflects?\s+on\b|\bexplains?\b|\bspiega\b|\bracconta\b", text_check_pi):
                if not re.search(r"\b(?:nomin\w+|appoint\w+|hired?|joins?|joined|firmato|signed|accordo|agreement)\b", text_check_pi):
                    signal["signal_type"] = "other"
                    demoted_to_other_by_editorial = True

        # Post-ML correction: deal_announced with pure people-transition language → people_move
        if signal.get("signal_type") == "deal_announced":
            text_check_da = (raw_title + " " + raw_summary).lower()
            title_check_da = (signal.get("title") or "").lower()
            page_category_da = (signal.get("page_category") or "").upper()
            if _is_team_static_description(title_check_da, text_check_da, page_category_da):
                signal["signal_type"] = "other"
                demoted_to_other_by_editorial = True
            else:
                has_people_transition = _has_people_transition_verb(text_check_da)
                has_explicit_deal = bool(
                    re.search(
                        r"\b(?:acquir\w+|acquisizion\w+|rileva"
                        r"|entra\s+(?:nel\s+capitale|in)\b|enters?\s+capital|buys?|compra"
                        r"|tratt[ai]\s+l[''\u2019]acquisto)\b",
                        text_check_da,
                    )
                    or re.search(r"\binvest\w+\s+(?:in|into|nel|nella|nei|nelle|da|per)\b", text_check_da)
                    or _RE_OFFER_BID.search(text_check_da)
                    or _RE_COMPANY_ROUND.search(text_check_da)
                    or _RE_MERGER.search(text_check_da)
                    or _RE_STRONG_EXIT_VERBS.search(text_check_da)
                    or _RE_EXPLICIT_SELLER.search(text_check_da)
                )
                if has_people_transition and not has_explicit_deal:
                    signal["signal_type"] = "people_move"

        # Post-ML correction: deal_announced with "launches" + fund vehicle/accelerator → fund_launch
        if signal.get("signal_type") == "deal_announced":
            text_check_da2 = (raw_title + " " + raw_summary).lower()
            has_launch = re.search(r"\b(?:launch(?:es|ed)?|lancia|lanci[ao])\b", text_check_da2)
            has_vehicle = _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, text_check_da2) or re.search(r"\b(?:accelerat(?:or|ore)|incubat(?:or|ore))\b", text_check_da2)
            if has_launch and has_vehicle:
                if not re.search(r"\b(?:acquir\w+|invest\w+\s+in\b|stake|majority|minority)\b", text_check_da2):
                    signal["signal_type"] = "fund_launch"

        # Post-ML correction: deal_announced where portfolio company (not the fund) acquires → portfolio_update.
        # Primary detection now in correct_deal() via _RE_PORTFOLIO_CO_AS_ACQUIRER (shared with enricher).
        # This block handles the remaining signal-specific case: fund name appears only in parenthetical.
        if signal.get("signal_type") == "deal_announced":
            text_check_pu = (raw_title + " " + raw_summary).lower()
            if _RE_PORTFOLIO_CO_AS_ACQUIRER.search(text_check_pu):
                signal["signal_type"] = "portfolio_update"
            elif re.search(r"\b(?:acquir\w+|complet\w+\s+(?:the\s+)?acquisition)\b", text_check_pu):
                # Fund mentioned only in parenthetical = portfolio company is the buyer
                fund_slug = (signal.get("fund_slug") or "").replace("-", " ").lower()
                fund_first = fund_slug.split()[0] if fund_slug else ""
                if fund_first and len(fund_first) >= 3:
                    if re.search(rf"\([^)]*{re.escape(fund_first)}[^)]*\)", text_check_pu):
                        if not text_check_pu.startswith(fund_first):
                            signal["signal_type"] = "portfolio_update"

        # Post-ML correction: deal_announced/exit with "estimate/analysis/market" → report or other
        if signal.get("signal_type") in ("deal_announced", "exit_announced"):
            text_check_rpt = (raw_title + " " + raw_summary).lower()
            if re.search(r"\b(?:estimat\w+|analysis|market\s+(?:at|size)|joint\s+analysis)\b", text_check_rpt):
                if not re.search(r"\b(?:acquir\w+|invest\w+|stake|close[ds]?|complet\w+)\b", text_check_rpt):
                    signal["signal_type"] = "other"

        # Post-ML correction: deal_announced/exit with "joined/joins network" → other
        if signal.get("signal_type") in ("deal_announced", "exit_announced"):
            text_check_net = (raw_title + " " + raw_summary).lower()
            if re.search(r"\b(?:join(?:s|ed)?)\s+(?:the\s+)?(?:\w+\s+)*?network\b", text_check_net):
                if not re.search(r"\b(?:acquir\w+|invest\w+|stake|close[ds]?)\b", text_check_net):
                    signal["signal_type"] = "other"

        # Post-ML correction: exit_announced with bank "finances/financing" → debt_financing
        if signal.get("signal_type") == "exit_announced":
            text_check_df = (raw_title + " " + raw_summary).lower()
            if re.search(r"\b(?:financ(?:es?|ing|ed)|secured?\s+.*?financ|credit\s+facilit)\b", text_check_df):
                if not re.search(r"\b(?:sells?|sold|exit\w*|divest\w*|cede|cession)\b", text_check_df):
                    signal["signal_type"] = "debt_financing"

        # Post-ML correction: fund_launch for "restructuring plan/accelerat" → portfolio_update or other
        if signal.get("signal_type") == "fund_launch":
            text_check_fl2 = (raw_title + " " + raw_summary).lower()
            if re.search(r"\brestructur\w+\s+plan\b", text_check_fl2):
                signal["signal_type"] = "portfolio_update"

        # Post-ML correction: re-run full reclassifier for "other" signals.
        # ML often overrides the reclassifier's correct decision — trust pattern matches.
        if signal.get("signal_type") == "other" and not demoted_to_other_by_editorial:
            title_check_other = (signal.get("title") or "").lower()
            page_category_other = (signal.get("page_category") or "").upper()
            text_check_other = (raw_title + " " + raw_summary).lower()
            # Don't rescue static team profile/job-style titles back into semantic types.
            if (
                (
                    _is_team_role_profile_line(title_check_other, page_category_other)
                    or _is_role_opening_title(title_check_other)
                    or _is_team_static_description(title_check_other, text_check_other, page_category_other)
                )
                and not _has_people_transition_verb(text_check_other)
            ):
                demoted_to_other_by_editorial = True
            else:
                reclassified = _reclassify_signal_type(signal, raw_title + " " + raw_summary, fund=fund)
                if reclassified and reclassified != "other":
                    # Guard: don't promote to fund_launch unless TITLE has fund vehicle language.
                    # The reclassifier uses full text which can match "launched...fondo" in what_changed,
                    # undoing the post-ML demotion that correctly identified stale/editorial signals.
                    if reclassified == "fund_launch":
                        title_check_fl = (signal.get("title") or "").lower()
                        if not _matches_any(FUND_LAUNCH_CLASSIFY_PATTERNS, title_check_fl):
                            reclassified = "other"
                    if reclassified != "other":
                        signal["signal_type"] = reclassified

        # Final post-ML reconciliation: run the shared correction engine one more
        # time so ML/local overrides cannot leave stale misclassifications.
        _final_text = (raw_title + " " + raw_summary).lower()
        _final_title = (signal.get("title") or raw_title or "").lower()
        _final_page_category = (signal.get("page_category") or "").upper()
        _final_diff_summary = (signal.get("diff_summary") or "").lower()

        _final_demotion = apply_universal_demotions(_final_text, _final_title)
        if _final_demotion is not None:
            signal["signal_type"] = _final_demotion
            if _final_demotion == "other":
                demoted_to_other_by_editorial = True
        else:
            _editorial_skip = (
                signal.get("signal_type") == "other"
                and demoted_to_other_by_editorial
                and not (_RE_INVEST_VERBS.search(_final_text) or _RE_ACQUISITION_VERBS.search(_final_text))
            )
            if not _editorial_skip:
                signal["signal_type"] = apply_type_corrections(
                    signal.get("signal_type") or "other",
                    _final_text,
                    _final_title,
                    _final_page_category,
                    _final_diff_summary,
                )

        # Safety net: if a signal is still "other" but has strong investment verbs
        # plus monetary evidence, recover it as a deal announcement.
        if signal.get("signal_type") == "other":
            _rescue_text = " ".join(
                [
                    raw_title or "",
                    raw_summary or "",
                    signal.get("title_original") or "",
                    signal.get("what_changed_original") or "",
                ]
            ).lower()
            _has_strong_deal_money = bool(
                _RE_INVEST_VERBS.search(_rescue_text)
                and re.search(r"[€$£]\s*\d", _rescue_text)
            )
            if _has_strong_deal_money and not _RE_EDITORIAL_STRATEGY.search(_rescue_text) and not _RE_INTERVIEW.search(_rescue_text):
                signal["signal_type"] = "deal_announced"

        # Pre-score for strict gate override and downstream filtering
        score = calculate_quality_score(
            signal,
            raw_title=raw_title or None,
            raw_summary=raw_summary or None,
            raw_text=raw_text or None,
        )
        signal["quality_score"] = score

        # Drop unhelpful website_change signals (after reclassification)
        if signal.get("signal_type") == "website_change":
            removed_strict_gate += 1
            continue

        # Precision-first strict gates (target ~90% quality)
        summary = raw_summary or ""
        title = raw_title or summary
        text = raw_text or f"{title} {summary}".lower()
        evidence_score = _news_evidence_score(signal, text, summary)
        signal["evidence_score"] = evidence_score
        signal["quality_confidence"] = _quality_confidence(signal, text, summary, score, evidence_score)
        quality_component = (score / 100)
        evidence_component = (evidence_score / 5)
        geo_boost = 0.1 if signal.get("italy_relevant") is True else 0.0
        type_boost = 0.05 if signal.get("signal_type") in {
            "deal_announced",
            "exit_announced",
            "fundraise_announced",
            "fundraise_closed",
            "fund_launch",
            "debt_financing",
        } else 0.0
        conf = signal.get("quality_confidence") or "low"
        conf_boost = 0.05 if conf == "high" else (-0.05 if conf == "low" else 0.0)
        signal["confidence_score"] = round(
            min(1.0, max(0.0, 0.4 * quality_component + 0.4 * evidence_component + geo_boost + type_boost + conf_boost)),
            3,
        )

        if not _passes_strict_quality_gates(signal, text, summary, pre_score=score, evidence_score=evidence_score):
            if _ml_override_keep(signal):
                kept_ml_override += 1
            else:
                removed_strict_gate += 1
                continue

        def _accept_signal(sig: dict, sc: int) -> None:
            """Track stats and append a kept signal."""
            sig["signal_types"] = detect_all_signal_types(sig)
            filtered.append(sig)
            c = sig.get("quality_confidence") or "low"
            if c in confidence_distribution:
                confidence_distribution[c] += 1
            if sc <= 20:
                score_distribution["0-20"] += 1
            elif sc <= 40:
                score_distribution["21-40"] += 1
            elif sc <= 60:
                score_distribution["41-60"] += 1
            elif sc <= 80:
                score_distribution["61-80"] += 1
            else:
                score_distribution["81-100"] += 1

        if score == 0:
            removed_garbage += 1
        elif score < MIN_QUALITY_SCORE:
            # Core signal types get a lower threshold (75 vs 80) — these are already
            # classified as investment events, so we accept slightly lower evidence
            effective_threshold = 75 if signal.get("signal_type") in CORE_QUALITY_TYPES else MIN_QUALITY_SCORE
            if score >= effective_threshold:
                _accept_signal(signal, score)
                continue
            elif _ml_override_keep(signal):
                kept_ml_override += 1
                _accept_signal(signal, score)
                continue
            else:
                removed_low_quality += 1
                continue
        else:
            _accept_signal(signal, score)

    # Semantic dedup: suppress near-duplicate signals about same deal from different sources
    pre_semantic_dedup = len(filtered)
    filtered = _semantic_dedup(filtered)
    removed_semantic_dedup = pre_semantic_dedup - len(filtered)
    if removed_semantic_dedup:
        print(f"  Semantic dedup: suppressed {removed_semantic_dedup} near-duplicate signals")

    # Cross-fund URL dedup: suppress signals from different funds pointing to the exact same article
    filtered = _cross_fund_url_dedup(filtered)

    # Cross-page dedup: suppress PORTFOLIO signals when NEWS covers same company
    pre_cross_dedup = len(filtered)
    filtered = _cross_page_dedup(filtered)
    removed_cross_page = pre_cross_dedup - len(filtered)

    # Sort by score (highest first)
    filtered.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    # Save
    data["signals"] = filtered
    data["signal_count"] = len(filtered)
    data["filtered_at"] = datetime.now(timezone.utc).isoformat()
    data["filter_stats"] = {
        "original_count": len(signals),
        "filtered_count": len(filtered),
        "removed_invalid_fund": removed_invalid_fund,
        "removed_duplicates": removed_duplicates,
        "resolved_duplicate_ids": resolved_duplicate_ids,
        "removed_strict_gate": removed_strict_gate,
        "removed_garbage": removed_garbage,
        "removed_low_quality": removed_low_quality,
        "removed_support_only": removed_support_only,
        "removed_junior_non_italy": removed_junior_non_italy,
        "removed_geo_irrelevant": removed_geo_irrelevant,
        "removed_misattributed": removed_misattributed,
        "removed_orphan_fund": removed_orphan_fund,
        "removed_ml": removed_ml,
        "removed_cross_page": removed_cross_page,
        "kept_ml_override": kept_ml_override,
        "ml_type_overrides": ml_type_overrides,
        "min_quality_score": MIN_QUALITY_SCORE,
        "confidence_distribution": confidence_distribution,
    }

    safe_json_write(OUTPUT_FILE, data)

    # Detect mentions of unknown funds (not in db.json) and alert via Telegram
    try:
        from fund_gap_detector import detect_unknown_fund_mentions
        from fundradar_worker.alerting import AlertConfig, send_unknown_fund_alerts
        known_slugs = set(funds_by_slug.keys())
        gaps = detect_unknown_fund_mentions(filtered, known_slugs, invalid_slugs=slug_normalizer.invalid_slugs)
        if gaps:
            send_unknown_fund_alerts(gaps, AlertConfig.from_env())
    except Exception as _gap_exc:
        print(f"Warning: fund gap detection failed: {_gap_exc}")

    print(f"\nScore distribution:")
    for range_name, count in score_distribution.items():
        bar = "█" * (count // 2)
        print(f"  {range_name}: {count:3d} {bar}")
    print(f"\nConfidence distribution (kept after strict gates):")
    for level in ("high", "medium", "low"):
        print(f"  {level}: {confidence_distribution.get(level, 0)}")

    print(f"\nFiltering results:")
    print(f"  Removed (orphan fund): {removed_orphan_fund}", end="")
    if orphan_slugs:
        print(f" [{', '.join(sorted(orphan_slugs))}]")
    else:
        print()
    print(f"  Removed (duplicates): {removed_duplicates}")
    print(f"  Resolved (duplicate IDs): {resolved_duplicate_ids}")
    print(f"  Removed (strict gate): {removed_strict_gate}")
    print(f"  Removed (ML keep=false): {removed_ml}")
    print(f"  Removed (cross-page dedup): {removed_cross_page}")
    print(f"  Removed (garbage): {removed_garbage}")
    print(f"  Removed (low quality < {MIN_QUALITY_SCORE}): {removed_low_quality}")
    print(f"  Removed (support staff only): {removed_support_only}")
    print(f"  Removed (junior non-Italy): {removed_junior_non_italy}")
    print(f"  Removed (non Europe/Italy): {removed_geo_irrelevant}")
    print(f"  Removed (misattributed): {removed_misattributed}")
    print(f"  Kept (ML override): {kept_ml_override}")
    print(f"  ML type overrides: {ml_type_overrides}")
    print(f"  Kept: {len(filtered)}")

    print(f"\nTop 5 signals by quality:")
    for s in filtered[:5]:
        summary = (s.get("enriched_summary") or s.get("what_changed") or "")[:60]
        print(f"  [{s['quality_score']:3d}] {s.get('fund_slug')}: {summary}...")

    print(f"\nOutput: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
