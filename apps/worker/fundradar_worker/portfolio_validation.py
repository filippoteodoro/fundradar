"""
Portfolio entry validation for Fundradar worker.

Ports the validation logic from the web app's data.ts (isValidPortfolioEntry,
cleanPortfolioName) to Python so garbage entries are filtered BEFORE writing
to portfolio_items.json.

The web app keeps its own validation as defense-in-depth for manual entries
and new garbage patterns.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Sector names that are not company names (exact match, case-insensitive)
SECTOR_NAMES = {
    "consumer & leisure", "consumer", "consumer goods", "consumer products",
    "industrials & energy transition", "industrials", "industrial",
    "tmt", "technology", "tech", "digital",
    "business services", "services", "professional services",
    "healthcare", "health", "life sciences",
    "financial services", "finance", "financials",
    "energy", "energy transition", "renewables",
    "infrastructure", "infra",
    "media & telecom", "telecom", "telecommunications", "media",
    "real estate", "property",
    "education", "food & beverage",
    "private equity", "venture capital",
    "esg", "impact investing",
    "pri", "unpri",
    "other",
    "credit", "equity", "real assets",
}

# Fund suffixes to strip when comparing entry names against fund names
FUND_SUFFIXES_RE = re.compile(
    r"\b(sgr|s\.?g\.?r\.?|capital|partners|investimenti|advisory|management|"
    r"group|holding|fund|alternative funds|real estate)\b",
    re.IGNORECASE,
)

# Self-reference suffixes
SELF_REF_SUFFIXES_RE = re.compile(
    r"\s+(?:asset\s+management|sgr|holding|venture\s+partners|circle)"
    r"\s*(?:s\.?p\.?a\.?)?$",
    re.IGNORECASE,
)

# Single-word editorial labels that are never company names.
GENERIC_SINGLE_WORD_REJECTS = {
    "acquisitions",
    "acquisition",
    "insights",
    "insight",
    "investments",
    "investment",
    "announcements",
    "announcement",
    "news",
    "newsroom",
    "podcast",
    "resources",
}

# NAV patterns that indicate garbage entries (navigation text, UI artifacts, etc.)
NAV_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^page not found",
        r"^click here",
        r"^powered by",
        r"vai alla",
        r"^stay tuned",
        r"^logout$",
        r"^portfolio stories",
        r"^what we do$",
        r"^about us$",
        r"^contact us$",
        r"^home$",
        r"^menu$",
        r"^search$",
        r"^clear$",
        r"^privacy policy",
        r"^cookie policy",
        r"^infrastrutture:$",
        r"notizie\s*leggi",
        r"publications.*report",
        r"combined\s*shape",
        r"\.pdf$",
        r"^work with us$",
        r"^case stud(?:y|ies)$",
        r"^awards$",
        r"^governance$",
        r"^sustainability$",
        r"^compliance$",
        r"^ombudsman$",
        r"^people$",
        r"^employees$",
        r"^error page",
        r"^cross.border\s+merger",
        r"with\s+clouds?$",
        r"\bmerger\s+on\s+\d",
        r"^share this page$",
        r"^back to top$",
        r"^portfolio$",
        r"^current portfolio$",
        r"^prior investments$",
        r"^investments?$",
        r"^our (?:activities|latest news|investments|portfolio)$",
        r"^funds under management$",
        r"^core\s+sectors$",
        r"^employees\s+across\s+portfolio$",
        r"^countries\s+with\b",
        r"^years?\s+average\s+holding",
        r"^(?:all )?(?:sectors?|industries|strateg(?:y|ies)|regions?|status|year)$",
        r"^informativa$",
        r"^name:?$",
        r"^(?:abstract|digitally)\s",
        r"^(?:man|woman|young|person)\s+\w+\s+\w+\s",
        r"\b(?:looking|sitting|standing|hugging|hiking)\b",
        r"\b(?:background|pie chart|bar graph|generated image)\b",
        r"^la pagina richiesta",
        r"^per chi vuole",
        r"^per le\s+(imprese|pubbliche)",
        r"^chi siamo",
        r"^who we are$",
        r"^news e media",
        r"you may want to visit",
        r"^la prospettiva di\b",
        r"magazine\s+digitale\b",
        r"\bprivacy by\b",
        r"\bconsiglio di amministrazione\b",
        r"^delivering\s+\w+\s+\w+\s+with\s+",
        r"\b(?:chiude|closes?|enters?)\s+(?:un|a|the|il|lo|la)\s",
        r"^(?:path|group|rect(?:angle)?|circle|line|polygon|ellipse|use|mask|clippath|defs)\s+\d+$",
        r"^cookielawinfo-",
        r"^viewed_cookie",
        r"^cookie notice$",
        r"cookies?$",
        r"^strictly necessary",
        r"^functional cookies?",
        r"^analytics cookies?",
        r"^you appear to be located",
        r"^we are currently targeting",
        r"^(?:facebook|linkedin|twitter|instagram|youtube)-[a-z]+$",
        r"^our companies$",
        r"^back to homepage$",
        r"^homepage$",
        r"torna alla homepage",
        r"\s-\s+menu\s+",
        r"\d{2,4}x\d{2,4}",
        r"^[a-z]+-[a-z]+-$",
        r"^[a-z]+-$",
        r"_$",
        r"^portafoglio$",
        r"^portale\s+",
        r"^scafalatura\s",
        r"^investimenti\b",
        r"^contatti$",
        r"^fondo\s+",  # Fund names (Fondo Acceleratori, Fondo Tech Transfer, etc.)
        r"^strategie\b",  # Strategy pages (Strategie d'investimento)
        r"^eventi$",  # Events page
        r"^informativa\b",  # Informativa Candidati, Informativa Whistleblowing
        r"^whistleblowing$",
        r":\s*$",  # Section headers ending with colon
        r"^realizzate\s+fondo\b",  # Realized fund sections (REALIZZATE FONDO Q2...)
        r"^team\s+\w+$",  # Team sections (Team EIFFEL)
        r"^(?:esigenze|caratteristiche|vantaggi|requisiti|criteri|tipologi[ae]|informazion[ie]|mission[ei]?|modalit[aà]|interventi?|ambiti?\s+di)\b",  # Italian section headings
        r"^settori?\s+di\b",  # "Settori di intervento", "Settore di attività"
        r"^strumenti?\s+di\b",  # "Strumenti di investimento"
        r"^il\s+processo\b",  # "Il processo di investimento"
        r"^le\s+fasi\b",  # "Le fasi dell'investimento"
        r"^fund.of.funds\s+model$",  # Fund structure description
        r"^(?:english|italiano|français|deutsch|español)$",
        r"^(?:next|prev|previous)$",
        r"^il\s+(?:gruppo|club|nostro|team)\b",
        r"^la\s+sezione\b",
        r"^login\b",
        r"^///",
        r"^(?:photograph|photo|image|picture)\s+of\b",
        r"^(?:father|mother|three|two|smiling|happy)\s+\w+\s+\w+\s+\w+",
        r"\b(?:sat|hug|hugging|emerging|smiling|chemist|laboratory|wheelchair|laptops?|notebooks?)\b",
        r"\b(?:closes?|raises?|secures?)\s+(?:CHF|EUR|USD|GBP|£|\$|€)\s*[\d.,]+",
        r"^primary\s+(?:acquisitions|investments)",
        r"^(?:recent|past|current|former|selected)\s+(?:acquisitions|investments|deals)",
        r"\b(?:fund|fondo|capital)\s+[IVX]+$",
        r"^fondo\s+(?:basket|chiuso|aperto)\b",
        r"^view\s+(?:company\s+)?website$",
        r"^(?:read|learn|find out)\s+more$",
        r"^download\b",
        r"^lascia\s+un\s+commento",
        r"^leave\s+a\s+(?:comment|reply)",
        r"^(?:fibre|cable|yellow|green|blue|red|white|black)\s+\w+s?$",
        r"^teenager\s",
        r"^photogra\w+\s+of\b",
        r"\b(?:campionato|torneo|olimpiad[ei]|coppa|trofeo|gara)\b",
        r"\bsquadra\s+(?:nazionale|regionale)\b",
        r"^(?:success|together|delivering|building|creating|making\s+the\s+world)\s+\w+\s+\w+\s+\w+",
        r"^(?:empowered|built|designed|driven|committed)\s+to\s+\w+$",
        r"\?\s*$",
        r"^\d{4}\s+(?:investment|annual|quarterly|market|economic|outlook|perspectives?|report)",
        r"\.(jpg|jpeg|png|gif|svg|webp)$",
        r"^come operiamo$",
        r"^comunicati stampa$",
        r"^il fondo$",
        r"^sostenibilit[aà]$",
        r"^linee guida",
        r"^esg\s+per\b",
        r"^video$",
        r"^it\s+it$",
        r"^iniziative$",
        r"^persone$",
        r"^impact\s+report$",
        r"^governance$",
        r"^media$",
        r"at a glance$",
        r"^offices?\s+worldwide$",
        r"^assets?\s+under\s+management$",
        r"^full.time\s+employees$",
        r"^capital\s+raised$",
        r"^\w+\s+buyout\s+fund$",
        r"^featured\s+content$",
        r"^asset\s+management$",
        r"^retirement\s+solutions$",
        r"^capital\s+solutions$",
        r"^real\s+assets$",
        r"^[0-9a-f]{8}[\s-][0-9a-f]{4}",
        r"close-icon",
        r"^news$",
        r"^innovation$",
        r"^content\s+hub$",
        r"^the\s*hub$",
        r"^3d\s+render\b",
        r"^foto\s+sito\b",
        r"\bheader\s+investments?$",
        r"^i nostri valori$",
        r"^le nostre storie$",
        r"^dove investiamo$",
        r"^sustainable\s+securities",
        r"^smes?\s+alternative\s+credit",
        r"\b(?:senior\s+)?loan\s+fund$",
        r"^key\s+numbers$",
        r"^dna\s+",
        r"\binvestimento\s+diretto\b",
        r"^lavora\s+con\s+noi$",
        r"^eventi$",
        r"^informativa\b",
        r"^uploads$",
        r"^overview\s+\w+",
        r"^investimenti\s+portfolio$",
        r"^icon$",
        r"^arrow$",
        r"\bimage\s+\d",
        r"^image[-\s]broken$",
        r"\blogo\b",
        r"^mission$",
        r"^vision$",
        r"^network\s+e\s+opportunit",
        r"^posizionamento\s+unico$",
        r"^strategi[ae]\b",
        r"^curriculum$",
        r"^advisory\s+board$",
        r"^immagine\d",
        r"^swdes$",
        r"^(?:what|who|how|why|when|where)$",
        r"^organi\s+societ",
        r"\bchiude\s+un\s+round\b",
        r"\bcloses?\s+(?:a\s+)?(?:CHF|EUR|USD|GBP|[€$£])\b",
        r"\bpre-seed\s+(?:funding\s+)?round\b",
        r"\bimpresa\s+target\b",
        r"\bcaratteristiche\s+tipiche\b",
        r"\bvantaggi\s+per\b",
        r"\besigenze\s+dell",
        r"^[\w\s]{5,}:$",
        r"^successful\s+\w+\s+of\b",
        r"\brealisation\s+of\s+investment\b",
        r"^introduction$",
        r"^filter\s+results$",
        r"\bmembro\s+della\b",
        r"^sostenibilit\w+\s+nei\b",
        # BU Partners / Eureka section headings
        r"^active\s+investments?$",
        r"^realized\s+investments?$",
        r"^active\s+label$",
        # Deal signal fragments (Italian/English deal-structure text as company names)
        r"^(?:una?\s+)?(?:quota|partecipazione)\s+(?:di\s+)?(?:ampia\s+|significativa\s+)?(?:maggioranza|minoranza)\s+",
        r"^(?:il|lo|la|un|una)\s+[\d.,]+%\s+(?:di|del|della|dell')\s+",
        r"^(?:il|la)\s+(?:controllo|maggioranza)\s+(?:di|del|della|dell')\s+",
        r"^(?:a\s+)?(?:majority|minority|significant|controlling|strategic|additional)\s+(?:stake|interest|position|holding)\s+in\s+",
        # Fund vehicle / co-investment vehicle names (CDP Venture Capital)
        r"\bSICAF\b",
        r"\bEuVECA\b",
        # Stat headings (Sinloc: "350+ Mln€ capex generati", "Circa 1,4 Mld€", "130 investimenti")
        r"^\d+\+?\s*(?:Mln|Mld|M|B)[\s€$£]",
        r"^[Cc]irca\s+\d",
        r"^\d+\s+investimenti$",
        # Section heading "Settori Di Intervento"
        r"^settori\s+di\s+intervento$",
        r"^fondi$",
    ]
]


def clean_portfolio_name(name: str) -> str:
    """
    Clean a raw portfolio company name before validation.
    Strips common scraping artifacts so real companies aren't rejected.
    Equivalent of TypeScript cleanPortfolioName() in data.ts.
    """
    cleaned = name.strip()
    # Strip trailing " logo" from image alt text
    cleaned = re.sub(r"\s+logo$", "", cleaned, flags=re.IGNORECASE)
    # Strip promotional suffixes ("| Invested by...", "| Vertis SGR SpA")
    cleaned = _strip_promotional_suffix(cleaned)
    # Strip leading/trailing pipe characters
    cleaned = re.sub(r"^\s*\|\s*", "", cleaned)
    cleaned = re.sub(r"\s*\|\s*$", "", cleaned)
    # If pipe still remains, keep text before pipe
    if "|" in cleaned:
        before_pipe = cleaned.split("|")[0].strip()
        if len(before_pipe) >= 3:
            cleaned = before_pipe
    # Strip trailing period
    cleaned = re.sub(r"\.\s*$", "", cleaned)
    # Strip trailing underscores
    cleaned = re.sub(r"_+$", "", cleaned)
    return cleaned.strip()


def _strip_promotional_suffix(name: str) -> str:
    """Strip promotional pipe suffixes like '| Invested by...' or '| SGR name'."""
    cleaned = re.sub(r"\s*\|\s*(?:Invested by|Formerly)\s+.+$", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*\w+\s+SGR\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\|\s*\w+\s+subsidiary\b.*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def is_valid_portfolio_entry(name: str, fund_slug: str) -> bool:
    """
    Reject garbage portfolio entries: nav text, article titles, error pages, fund names.
    Returns True if the entry looks like a real company name.
    Equivalent of TypeScript isValidPortfolioEntry() in data.ts.
    """
    trimmed = name.strip()
    if not trimmed or len(trimmed) <= 2:
        return False

    # Reject names longer than 60 chars (article titles, error messages, image alt text)
    if len(trimmed) > 60:
        return False

    # Reject if name starts with "Logo "
    if re.match(r"^Logo\s", trimmed, re.IGNORECASE):
        return False

    # Reject colon-subtitle patterns where the part after the colon is long
    colon_match = re.search(r":\s*(.+)", trimmed)
    if colon_match and len(colon_match.group(1)) > 10:
        return False

    # Reject long parenthetical descriptions
    paren_match = re.search(r"\(([^)]+)\)", trimmed)
    if paren_match and len(paren_match.group(1)) > 20:
        return False

    # Reject names that end with a colon (filter labels like "REGIONS:", "INDUSTRY:")
    if re.match(r"^[A-Z]+:$", trimmed):
        return False

    # Reject article-title patterns: gerund + lowercase word(s) + preposition
    if re.match(r"^[A-Z][a-z]+ing\s+(?:on|in|into|with|for|new|big|the|a|an)\s", trimmed, re.IGNORECASE):
        return False
    if re.match(r"^[A-Z][a-z]+ing\s+\w+\s+\w*\s*(?:with|for|in|into)\s", trimmed, re.IGNORECASE):
        return False
    if re.match(
        r"^[A-Z][a-z]+ing\s+.+\b(?:across|through|throughout|toward|towards|via|among|between)\b",
        trimmed,
        re.IGNORECASE,
    ):
        return False

    # Reject description-like text
    if re.match(r"^(?:A\s+)?leading\s+", trimmed, re.IGNORECASE):
        return False
    if re.match(r"^(?:Global|World|European|Italian?)\s+leader\s+", trimmed, re.IGNORECASE):
        return False
    if re.match(r"^One of the\s+", trimmed, re.IGNORECASE):
        return False
    if re.search(r"\bis (?:a|the|one of)\b", trimmed, re.IGNORECASE):
        return False

    # Reject Italian investment-category headings
    if re.match(r"^Investimenti\s", trimmed, re.IGNORECASE):
        return False

    # Reject sentence-like editorial titles frequently misparsed as portfolio companies.
    if re.search(r"\bfeatured\s+on\b", trimmed, re.IGNORECASE):
        return False
    if re.search(r"\bpodcast\b", trimmed, re.IGNORECASE):
        return False
    if re.match(r"^The\s+\w+\s+of\s+the\s+", trimmed, re.IGNORECASE):
        return False

    # Reject single generic editorial/category words.
    if " " not in trimmed and trimmed.lower() in GENERIC_SINGLE_WORD_REJECTS:
        return False

    # Reject sector/industry category names
    if trimmed.lower() in SECTOR_NAMES:
        return False

    # Reject concatenated words >15 chars containing portfolio/company substrings
    if " " not in trimmed and len(trimmed) >= 12:
        lower = trimmed.lower()
        if re.search(
            r"portfolio|company|companies|invest(?:ment|ing)|ourport|insight|acquisit|announc|podcast|news|press",
            lower,
        ):
            return False

    # Reject known UI/nav patterns
    for pattern in NAV_PATTERNS:
        if pattern.search(trimmed):
            return False

    # Reject if name matches the fund's own name or is a variant of it
    fund_name_from_slug = fund_slug.replace("-", " ").lower()
    name_normalized = re.sub(r"[^a-z0-9\s]", "", trimmed.lower()).strip()
    if name_normalized == fund_name_from_slug:
        return False

    # Concatenated (no-space) match
    name_compact = name_normalized.replace(" ", "")
    fund_compact = fund_name_from_slug.replace(" ", "")
    if name_compact == fund_compact:
        return False

    # Strip common fund suffixes to get core name
    fund_core_name = FUND_SUFFIXES_RE.sub("", fund_name_from_slug).strip()
    fund_core_name = re.sub(r"\s+", " ", fund_core_name).strip()
    entry_core_name = FUND_SUFFIXES_RE.sub("", name_normalized).strip()
    entry_core_name = re.sub(r"\s+", " ", entry_core_name).strip()

    # Reject if core names match
    if len(fund_core_name) >= 2 and entry_core_name == fund_core_name:
        return False

    # Reject if entry core starts with fund core as a whole word
    if len(fund_core_name) >= 3 and len(entry_core_name) > len(fund_core_name):
        if entry_core_name.startswith(fund_core_name):
            after = entry_core_name[len(fund_core_name):]
            if after and (after[0] == " " or after[0].isdigit()):
                return False
    if len(fund_core_name) > len(entry_core_name) and len(entry_core_name) >= 3:
        if fund_core_name.startswith(entry_core_name):
            after = fund_core_name[len(entry_core_name):]
            if after and (after[0] == " " or after[0].isdigit()):
                return False

    # Reject partial fund name + generic suffix
    fund_words = fund_name_from_slug.split()
    if fund_words and len(fund_words[0]) >= 3:
        first_word = fund_words[0]
        if name_normalized.startswith(first_word) and len(name_normalized) > len(first_word):
            rest = name_normalized[len(first_word):].strip()
            if re.match(
                r"^(investment|capital|partners|management|im |group|advisory|sgr|holding|fund|real estate|alternative)",
                rest,
                re.IGNORECASE,
            ):
                return False

    # Reject "Gruppo [FundName]"
    gruppo_match = re.match(r"^gruppo\s+", trimmed, re.IGNORECASE)
    if gruppo_match:
        after_gruppo = re.sub(r"[^a-z0-9\s]", "", trimmed[gruppo_match.end():].lower()).strip()
        if len(fund_core_name) >= 3 and fund_core_name in after_gruppo:
            return False

    # Reject "[FundWord] Asset Management/SGR/Holding" self-references
    if SELF_REF_SUFFIXES_RE.search(trimmed) and fund_words and len(fund_words[0]) >= 3:
        before_suffix = SELF_REF_SUFFIXES_RE.sub("", trimmed).lower()
        before_suffix = re.sub(r"[^a-z0-9\s]", "", before_suffix).strip()
        if fund_core_name in before_suffix or before_suffix in fund_core_name:
            return False

    return True


def validate_and_clean_portfolio(
    companies: list[dict],
    fund_slug: str,
) -> list[dict]:
    """
    Clean and validate a list of extracted portfolio companies.
    Returns only valid entries with cleaned names.
    Logs rejected entries at DEBUG level for auditing.
    """
    valid = []
    for company in companies:
        raw_name = company.get("name", "")
        if not raw_name:
            continue

        cleaned_name = clean_portfolio_name(raw_name)
        if not cleaned_name or len(cleaned_name) <= 2:
            logger.debug(
                "Rejected portfolio entry for %s: empty after cleaning (raw: %r)",
                fund_slug, raw_name,
            )
            continue

        if not is_valid_portfolio_entry(cleaned_name, fund_slug):
            logger.debug(
                "Rejected portfolio entry for %s: failed validation (name: %r)",
                fund_slug, cleaned_name,
            )
            continue

        company["name"] = cleaned_name
        valid.append(company)

    rejected_count = len(companies) - len(valid)
    if rejected_count > 0:
        logger.info(
            "Portfolio validation for %s: %d/%d entries passed (%d rejected)",
            fund_slug, len(valid), len(companies), rejected_count,
        )

    return valid
