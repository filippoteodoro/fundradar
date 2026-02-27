#!/usr/bin/env python3
"""
Shared signal patterns used by both filter_signals.py and enrich_signals_openai.py.

This module is the single source of truth for regex patterns, constants, and utility
functions that are duplicated across the filter and enricher scripts. When updating
a pattern, update it HERE — both consumers import from this module.

NOTE: Do NOT use re.VERBOSE for any of these patterns — they are single-line patterns.
"""

import re


# ─────────────────────────────────────────────────────────────────────────────
# Core signal type sets
# ─────────────────────────────────────────────────────────────────────────────

# CORE_GEO_TYPES: fund-level types that pass geo gate for italy_focused / europe_wide funds
# (no people_move, no portfolio_update — those are company/person-level, need text evidence)
CORE_GEO_TYPES = {
    "deal_announced", "exit_announced", "fundraise_announced",
    "fundraise_closed", "fund_launch", "partnership", "report",
    "debt_financing",
}

# CORE_QUALITY_TYPES: types that get lower quality threshold (75 vs 80) — includes people_move + portfolio_update
CORE_QUALITY_TYPES = CORE_GEO_TYPES | {"people_move", "portfolio_update"}


# ─────────────────────────────────────────────────────────────────────────────
# Compiled regex patterns (shared between filter and enricher)
# ─────────────────────────────────────────────────────────────────────────────

# Portfolio company activity detection (bolt-on, add-on, Italian ownership phrases)
_RE_PORTFOLIO_UPDATE = re.compile(
    r"\bportfolio\s+compan(?:y|ies)\b"
    r"|\b(?:partecipata|controllata)\s+(?:da|di)\b"
    r"|\btramite\s+(?:la\s+sua\s+)?(?:partecipata|controllata)\b"
    r"|\bin\s+portafoglio\s+(?:a|di)\b"
    r"|\bsociet[àa]\s+in\s+portafoglio\b"
    r"|\badd[\-\s]?ons?\b"
    r"|\bbolt[\-\s]?ons?\b"
    r"|\btuck[\-\s]?ins?\b"
    r"|\bcontrolling\s+shareholder\b",
    re.IGNORECASE,
)

# Basic exit verbs
_RE_EXIT_VERBS = re.compile(
    r"\bsells?\b|\bselling\b|\bsold\b|\bexits?\b|\bexited\b"
    r"|\bvend(?:e|ere|ita|ono)\b|\bvendut[oa]\b|\bcede\b|\bcession[ei]\b"
    r"|\bdisinvest\w+\b|\bdivest\w+\b|\ba\s+vendere\b",
    re.IGNORECASE,
)

# Strong exit verbs — broader than _RE_EXIT_VERBS, includes "sale of stake", "successful realisation"
_RE_STRONG_EXIT_VERBS = re.compile(
    r"\bsells?\b|\bsold\b|\bvend(?:e|ere|ita|ono)\b|\bvendut[oa]\b"
    r"|\bcede\b|\bcession[ei]\b|\bdisinvest\w+\b|\bdivest\w+\b"
    r"|\bexits?\b|\bexited\b|\brealis(?:ation|ation|ed)\b|\brealiz(?:ation|ation|ed)\b"
    r"|\bsale\s+of\s+(?:its?\s+)?(?:stake|shares?|interest|partecipazione|quota)\b"
    r"|\bsuccessful\s+realis\w+\b",
    re.IGNORECASE,
)

# Investment/acquisition verbs
# Uses the BROADER version from filter_signals.py which includes additional patterns
_RE_INVEST_VERBS = re.compile(
    r"\binveste\b|\binvestono\b|\bacquir\w+\b|\bacquisizion\w*\b|\brileva\b"
    r"|\binvest(?:s|ing)?\s+(?:in|into|nel|nella|nei|nelle)\b"
    r"|\binvestiment[oi]\s+(?:di|da|in|nel|per)\b"
    r"|\bprende\s+il\s+controllo\b|\bingresso\s+(?:di|in|nel)\b"
    r"|\bentra\s+nel\s+capitale\b|\boperazion[ei]\s+di\s+(?:debito|credito)\b"
    r"|\binvestitore\s+unic\w*\s+al\s+fianco\s+di\b"
    r"|\bsole\s+investor\s+(?:backing|alongside)\b"
    r"|\btakes?\s+(?:a\s+)?(?:stake|quota|partecipazione)\b"
    r"|\bpreso\s+(?:una?\s+)?(?:quota|partecipazione)\b"
    r"|\binvested\s+in\b"
    r"|(?<!\w)[€$£]\s*[\d.,]+[MBK]?\s+in\s+investments?\b",
    re.IGNORECASE,
)

# Board appointment detection
# Standardized name: _RE_BOARD_APPOINT (filter called it _RE_BOARD_APPOINTMENT)
# Uses the BROADER version with re.IGNORECASE and "responsabile", "nuovo cda/consiglio"
_RE_BOARD_APPOINT = re.compile(
    r"\b(?:board|consiglio|nomin(?:a|at\w+|e)|appointed|eletto|responsabile"
    r"|nuovo\s+(?:cda|consiglio))\b",
    re.IGNORECASE,
)

# Ordinal investment: "primo investimento", "secondo investimento", etc.
_RE_ORDINAL_INVESTMENT = re.compile(
    r"\b(?:nuovo|nuov[oa]|primo|secondo|terz[oa]|quart[oa]|quint[oa]"
    r"|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
    r"|\d+[°ºª]?(?:st|nd|rd|th)?)"
    r"\s+(?:investiment[oi]|operazione|investment|deal|operation)\b",
    re.IGNORECASE,
)

# "chiude la raccolta" patterns
_RE_CHIUDE_RACCOLTA = re.compile(
    r"\bchiude\s+la\s+raccolta\b|\bchiude\b.*\bfundraising\b|\bcloses\s+fundraising\b",
    re.IGNORECASE,
)

# Fundraise closing patterns (broader than _RE_CHIUDE_RACCOLTA)
_RE_FUNDRAISE_CLOSING = re.compile(
    r"\bchius[oa]\b.*\bclosing\b|\bclosing\b.*\bchius[oa]\b"
    r"|\bchiude\b.*\bclosing\b|\bchiuso il closing\b|\bfinal close\b|\bhard cap\b"
    r"|\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|veicolo|oversubscribed)\b"
    r"|\b(?:primo|secondo|terzo|first|second|third|successful)\s+closing\b"
    r"|\brealizza\b.*\bclosing\b"
    r"|\b(?:announces?|completes?|closes?)\s+(?:its?\s+)?(?:first|second|final)\s+closing\b",
    re.IGNORECASE,
)

# Fundraise milestone detection
_RE_FUNDRAISE_MILESTONE = re.compile(
    r"\bsupera\s+(?:i\s+)?\d+.*(?:raccolt|capital)\b"
    r"|\bsupera(?:ndo)?\s+(?:il\s+)?(?:proprio\s+)?target\b"
    r"|\bsurpass\w*\s+\d+.*(?:raised|capital)\b"
    r"|\bsurpass(?:ing)?\s+(?:its?\s+)?target\b"
    r"|\barriva\s+a\s+\d+.*\b(?:m|mln|milion)\b",
    re.IGNORECASE,
)

# Outsourcing/procurement patterns (including RFPs and expressions of interest)
_RE_OUTSOURCING = re.compile(
    r"\b(?:outsourcing|affidamento\s+in\s+outsourcing|indagine\s+esplorativa"
    r"|manifestazion[ei]\s+di\s+interesse|procedura\s+comparativa"
    r"|gara\s+d[i'\u2019]\s*appalto|bando\s+di\s+gara"
    r"|soliciting\s+expressions?\s+of\s+interest"
    r"|full[\-\s]?outsourcing\s+provider"
    r"|request\s+for\s+(?:proposal|quote|information)s?"
    r"|RFP\s+for\b)\b",
    re.IGNORECASE,
)

# Fashion/marketing/PR campaign — portfolio company marketing, not PE activity
_RE_FASHION_CAMPAIGN = re.compile(
    r"\b(?:spring[\s/]+summer|fall[\s/]+winter|autumn[\s/]+winter|SS\s*\d{2,4}|FW\s*\d{2,4}|AW\s*\d{2,4})\b"
    r".*\b(?:campaign|collection|lookbook|runway|fashion\s+show|capsule)\b"
    r"|\b(?:campaign|collection|lookbook|runway|fashion\s+show|capsule)\b"
    r".*\b(?:spring[\s/]+summer|fall[\s/]+winter|autumn[\s/]+winter|SS\s*\d{2,4}|FW\s*\d{2,4}|AW\s*\d{2,4})\b"
    r"|\b(?:shot\s+on\b|directed\s+by\b|photographed\s+by\b|creative\s+director\b).*\b(?:campaign|collection)\b"
    r"|\bpresents?\s+(?:its?\s+)?(?:new\s+)?(?:spring|fall|winter|summer|SS|FW|AW)\b"
    # Location-based photo/PR campaign: "chooses X for its campaign", "selects Y for new campaign"
    r"|\bchooses?\s+(?:the\s+)?\w.*?\bfor\s+(?:its?\s+)?.*?\bcampaign\b"
    r"|\bselects?\s+(?:the\s+)?\w.*?\bfor\s+(?:its?\s+)?.*?\bcampaign\b",
    re.IGNORECASE,
)

# Boilerplate template signals — no real content
_RE_BOILERPLATE_TEMPLATE = re.compile(
    r"^new\s+(?:investment|deal|fundraise)\s+involving\s+[\w\s]+$"
    r"|^new\s+(?:investment|deal)\s+in\s+[\w\s]+$"
    r"|^the\s+messenger$",
    re.IGNORECASE,
)

# Magazine/editorial format changes — not PE activity
_RE_EDITORIAL_FORMAT = re.compile(
    r"\b(?:shift|switch|transition)\w*\s+(?:from|to)\s+(?:weekly|fortnightly|monthly|biweekly|daily)\b"
    r"|\b(?:weekly|fortnightly|monthly|biweekly)\s+(?:to|issues?)\b.*\b(?:premium|positioning|format)\b"
    r"|\b(?:editorial|magazine)\s+(?:format|strategy|relaunch|rebrand)\b",
    re.IGNORECASE,
)

# Job posting patterns (Italian job selection language)
# Standardized name: _RE_JOB_SELECTION (filter also had _RE_JOB_POSTING_SHORT with same content)
_RE_JOB_SELECTION = re.compile(
    r"\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]"
    r"|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)"
    r"|avvia\s+(?:la\s+)?selezione)\b",
    re.IGNORECASE,
)

# Report/annual report detection
_RE_REPORT = re.compile(
    r"\b(?:bilancio|financial\s+results?|annual\s+report|year[\-\s]?end\s+report"
    r"|sustainability\s+report|rapporto\s+(?:annuale|di\s+sostenibilit[àa])"
    r"|esg\s+report|quarterly\s+(?:report|credit\s+check|results?)"
    r"|interim\s+report|half[\-\s]?year\s+report"
    r"|utile\s+d[i'\u2019]\s*esercizio"
    r"|closes?\s+(?:the\s+)?financial\s+year|risultati?\s+finanziari"
    r"|(?:primo|secondo|terzo|quarto)\s+trimestre\b.*\butile\b"
    r"|utile\s+netto\s+a\s+\d+)\b",
    re.IGNORECASE,
)

# Event attendance — not a transaction
_RE_EVENT_ATTENDANCE = re.compile(
    r"\b(?:guest|relator[ei]|speaker|panelist|moderator)\b.*\b(?:event[oi]?|congress[oi]?|summit|conferenz\w*|forum|webinar|panel|convegno)\b"
    r"|\b(?:event[oi]?|congress[oi]?|summit|conferenz\w*|forum|webinar|panel|convegno)\b.*\b(?:guest|relator[ei]|speaker|panelist|moderator)\b"
    r"|\binterviene\s+(?:a|al)l['\u2019]?\s*(?:event[oi]?|congress[oi]?|summit|conferenz\w*|forum|webinar|panel)\b"
    r"|\b(?:partecipa|interviene|presente)\s+(?:a|al)l['\u2019]?\s*\w+\s*(?:event[oi]?|congress[oi]?|summit|conferenz\w*|forum|webinar|panel|convegno)\b"
    r"|\bspeaks?\s+at\s+(?:the\s+)?(?:event|conference|summit|forum|congress|panel|webinar|convegno)\b"
    r"|\bcontribut\w+\s+(?:to|a|al)l?\b.{0,60}\b(?:event[oi]?|congress[oi]?|summit|conferenz\w*|forum|convegno)\b",
    re.IGNORECASE,
)

# Event titles (congress/summit/forum with year or at end of string)
# Uses the BROADER version from filter_signals.py which also matches "in <word>" at end
_RE_EVENT_TITLE = re.compile(
    r"^(?:.*\s)?(?:congress[oi]?|summit|forum|conferenz\w*|convegno|workshop|webinar"
    r"|tavola\s+rotonda|seminari[oi]?)\s*(?:\d{4}|in\s+\w+|$)",
    re.IGNORECASE,
)

# Conference recaps/highlights
_RE_EVENT_INSIGHTS = re.compile(
    r"\binsights?\s+from\b.*\b(?:conference|summit|forum|event)\b"
    r"|\b(?:conference|summit|forum)\s+(?:recap|highlights?|takeaways?|wrap[\-\s]?up)\b",
    re.IGNORECASE,
)

# "joins forum/conference" → event attendance (not investment activity)
_RE_JOINS_EVENT = re.compile(
    r"\b(?:joins?|partecipa|presente)\s+(?:a\s+|al\s+|strategic\s+|the\s+)?\w*\s*"
    r"(?:forum|congress[oi]?|summit|conferenz\w*|convegno|event)\b",
    re.IGNORECASE,
)

# Explicit seller mentions
_RE_EXPLICIT_SELLER = re.compile(
    r"\ba\s+vendere\b"
    r"|\bil\s+venditore\b"
    r"|\bcede\s+(?:la\s+)?(?:propria\s+)?(?:partecipat\w+|quota|partecipazione)\b"
    r"|\bcede\s+(?:il\s+)?(?:proprio\s+)?(?:\d+%|controllo|majority|maggioranza)\b"
    r"|\bdisinvestiment[oi]\b",
    re.IGNORECASE,
)

# Partnership patterns
_RE_PARTNERSHIP = re.compile(
    r"\bpartnership\b|\bpartners?\s+with\b|\bjoint\s+venture\b"
    r"|\bdistribution\s+agreement\b|\bstrategic\s+alliance\b"
    r"|\bcollaborazione\s+strategica\b"
    r"|\baccordo\s+(?:di\s+)?(?:collaborazione|distribuzione|partnership)\b"
    r"|\balleanza\s+strategica\b|\bintesa\s+(?:strategica|commerciale)\b"
    r"|\bjoins?\s+forces\b|\bjoined\s+forces\b",
    re.IGNORECASE,
)

# Partnership exclusions (if any match, it's a deal, NOT a partnership)
_RE_PARTNERSHIP_EXCLUDE = re.compile(
    r"\bacqui\w+\b|\brileva\b|\bbuyout\b|\bmajority\b"
    r"|\bminority\s+stake\b|\bentra\s+nel\s+capitale\b",
    re.IGNORECASE,
)

# Italian "finalizzat*" deal patterns
_RE_FINALIZZAT = re.compile(r"\bfinalizzat\w+\b", re.IGNORECASE)

# Research/publication demotions
_RE_RESEARCH = re.compile(
    r"\b(?:white\s*paper|report\s+(?:annuale|di\s+ricerca)|ricerca|studio"
    r"|analisi|survey|outlook|barometr\w+|osservatori\w+)\b",
    re.IGNORECASE,
)

# Investor meeting/AGM patterns
# Uses the BROADER version from filter_signals.py (line 1687) which includes "event", "conference"
_RE_INVESTOR_MEETING = re.compile(
    r"\binvestor\s+(?:meeting|day|event|conference)\b"
    r"|\bassemblea\s+(?:dei\s+)?(?:soci|azionisti|investitori)\b"
    r"|\bagm\b|\bannual\s+general\s+meeting\b",
    re.IGNORECASE,
)

# "exited from portfolio" pattern
_RE_EXITED_FROM_PORTFOLIO = re.compile(
    r"\b(?:exited?\s+from\s+.*portfolio|uscit[ao]\s+dal?\s+portafoglio)\b",
    re.IGNORECASE,
)

# Bond/debt issuance patterns
# Standardized name: _RE_BOND_ISSUANCE (enricher called it _RE_BOND)
_RE_BOND_ISSUANCE = re.compile(
    r"\b(?:bond|obbligazion\w+|emissione|rifinanzia\w+|refinanc\w+|debt\s+issuance"
    r"|collocamento|collocare?|minibond[s]?|mini\s+bond[s]?)\b",
    re.IGNORECASE,
)

# Exclude equity actions from debt classification
_RE_BOND_EXCLUDE = re.compile(
    r"\b(?:acqui\w+|rileva|investiment[oi]|exit|sells?|cessione"
    r"|launch|lancia|nasce|aucap|aumento\s+di\s+capitale)\b",
    re.IGNORECASE,
)

# Broader debt financing patterns: bank loans, private debt, securitization
_RE_DEBT_FINANCING_BROAD = re.compile(
    r"\bprivate\s+debt\s+(?:transaction|deal|operazion\w+|investiment\w+)\b"
    r"|\bprivate\s+debt\b.*\b(?:completes?|conclude|chiude|finalizzat\w+)\b"
    r"|\bottiene\s+(?:da\s+\w+\s+)?finanziament[oi]\b"
    r"|\bfinanziament[oi]\s+(?:per|da|di)\s+[€$£]?\s*[\d.,]+\s*(?:m\b|mln|milion)"
    r"|\b(?:€|\$|£)?\s*[\d.,]+\s*(?:m\b|mln|million|milion|bn|billion)\s+in\s+new\s+financing\b"
    r"|\bsecuritiz\w+\b"
    r"|\bcartolarizzazion\w+\b"
    r"|\bnuov[aoe]\s+(?:operazion[ei]\s+di\s+)?(?:debito|finanziament[oi])\b"
    r"|\bgreen\s+bond\b"
    r"|\bdebt\s+(?:operation|transaction|facility)\b"
    r"|\boperazion[ei]\s+di\s+debito\b"
    r"|\bsenior\s+(?:secured\s+)?(?:loan|debt|facility|notes?)\b"
    r"|\bmezzanine\s+(?:financ\w+|debt|loan)\b"
    r"|\bunitranche\b"
    r"|\bprovid(?:es?|ed|ing)\b.{0,30}\bfinanc(?:ing|e)\b"
    r"|\bfinancing\s+support\b"
    r"|\breceives?\s+financ(?:ing|e)\s+from\b",
    re.IGNORECASE,
)

# Credit facility detection
_RE_CREDIT_FACILITY = re.compile(
    r"\brevolving\s+credit\s+facilit\w+\b"
    r"|\bcredit\s+facilit\w+\b.*\b(?:upsize|extend|renew)\b"
    r"|\b(?:upsize|extend)\w*\b.*\bcredit\s+facilit\w+\b",
    re.IGNORECASE,
)

# Project financing patterns
_RE_PROJECT_FINANCING = re.compile(
    r"\bproject\s+financing\b|\briceve\s+finanziamento\b"
    r"|\bottiene\s+(?:da\s+)?\w+\s+finanziamento\b"
    r"|\bsottoscritto\s+(?:project\s+)?financ\w+\b",
    re.IGNORECASE,
)

# Any PE-related verb (safety net)
_RE_HAS_ANY_PE_VERB = re.compile(
    r"\b(?:sells?|selling|sold|sale|exit\w*|cessione|vendita|vend[eio]\w*|vendut[oa]|cedut[oa]|dismette|a\s+vendere"
    r"|acquir\w+|acquisizion\w*|investi\w+|rileva|entra\s+nel\s+capitale|enters?\s+capital|buys?|compra"
    r"|offerta\b|offer\b|bid\b"
    r"|fundrais\w+|raccolta|closing|round|series|seed|chiude|chiusura"
    r"|launch|lancia|nasce|nascita|lancio"
    r"|partnership|joint\s+venture|nomina|appointed"
    r"|ipo\b|merger|fusione|buyout|lbo\b|takeover"
    r"|finanziamento|aumento\s+di\s+capitale|operazione|finalizzat\w+)\b",
    re.IGNORECASE,
)

# Accelerator/program launch → other (fund's strategic initiative, NOT a fund vehicle)
_RE_ACCELERATOR_LAUNCH = re.compile(
    r"\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b"
    r".*\b(?:accelerator(?:e)?|incubator(?:e)?|polo|programma|program|hub)\b"
    r"|\b(?:accelerator(?:e)?|incubator(?:e)?|polo|programma|program|hub)\b"
    r".*\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b",
    re.IGNORECASE,
)

# Strict fund launch patterns (actual fund vehicles, NOT accelerators/programs)
# Uses the BROADER version from filter/enricher which includes "operativo il comparto"
_RE_FUND_LAUNCH_STRICT = re.compile(
    r"\b(?:lancia|lancio|nasce|nascita|launch(?:es|ed)?|avvia|al\s+via)\b.{0,80}\b(?:fondo|fund|comparto|veicolo|vehicle)\b"
    r"|\b(?:fund|fondo)\s+(?:i{1,3}|iv|v|vi{1,3}|ix|x|\d+)\b"
    r"|\bnew\s+fund\b|\bnuovo\s+fondo\b|\bfund\s+formation\b"
    r"|\bvehicle\s+launch\b|\bfund\s+(?:launch|inception|creation)\b"
    r"|\bcomparto\b.{0,50}\b(?:operativo|attivo|avviato)\b"
    r"|\boperativ[oa]\s+(?:il\s+)?comparto\b",
    re.IGNORECASE,
)

# Company-level round detection (portfolio company raises capital)
# Uses the BROADER version from filter_signals.py which has additional patterns
_RE_COMPANY_ROUND = re.compile(
    r"\b(?:round|serie|series|seed|pre[-\s]?seed)\s+(?:a|b|c|d|e|f|di)\b"
    r"|\bserie\s+[a-f]\b"
    r"|\bround\s+(?:seed|pre[-\s]?seed)\b"
    r"|\bround\s+(?:d[i'\u2019]\s*)?(?:investimento|finanziamento)\b"
    r"|\bround\s+da\s+[€$£]?\s*[\d.,]+"
    r"|\bincassa\s+(?:nuovo\s+)?round\b"
    r"|\braccog\w+\s+[€$£]?\s*[\d.,]+\s*(?:m\b|mln|milion|k\b|mila)"
    r"|\baumento\s+di\s+capitale\b.*\bstartup\b"
    r"|\bstartup\b.*\baumento\s+di\s+capitale\b"
    r"|\bchiude\s+un\s+(?:round|aumento\s+di\s+capitale)\b"
    r"|\briceve\s+un\s+finanziamento\b"
    r"|\baumento\s+di\s+capitale\s+(?:con|sottoscritto\s+da|da)\s+\w+"
    r"|\b(?:startup|scaleup|scale-up|spin[\-\s]?off)\b.*\b(?:chiude|raccog\w+|riceve|incassa|ottiene|conclude|completa)\b"
    r"|\b(?:chiude|raccog\w+|riceve|incassa|ottiene|conclude|completa)\b.*\b(?:startup|scaleup|scale-up|spin[\-\s]?off)\b"
    r"|\bfinanziamento\s+da\s+[€$£]?\s*[\d.,]+"
    r"|\bottiene\s+un\s+finanziamento\b"
    r"|\b(?:completa|conclude)\s+(?:un\s+)?(?:round|aumento\s+di\s+capitale)\b"
    r"|\bporta\s+a\s+casa\s+(?:un\s+)?round\b"
    r"|\b(?:chiuso|completato|concluso)\s+(?:il\s+)?(?:round|aumento\s+di\s+capitale)\b"
    r"|\braccog\w+\s+(?:oltre\s+)?[€$£]\s*[\d.,]+\b"
    r"|\bround\s+(?:aggiuntivo|addizionale)\b"
    r"|\bincassa\s+(?:altri\s+)?[€$£]?\s*[\d.,]+\s*(?:m\b|mln|milion|k\b|mila)"
    r"|\b\d+(?:[.,]\d+)?\s*(?:milion\w*|mln|mila)\s+di\s+euro\s+di\s+raccolta\b"
    r"|\bpassa\s+a\s+(?:fondo|fund)\b"
    # English patterns for translated startup rounds
    r"|\b(?:closed?s?|completes?|secures?|raises?)\s+(?:a\s+)?[€$£]?\s*[\d.,]+\s*(?:M|m|mln|million|B|bn|billion)?\s*(?:round|funding)\b"
    r"|\b[€$£]\s*[\d.,]+\s*(?:M|m|mln|million|B|bn|billion)\s+(?:round|funding)\s+(?:led|backed|from)\b"
    r"|\bstartup\b.*\b(?:closed?s?|raised?s?|secures?|completes?)\b.*\b(?:round|funding)\b"
    r"|\b(?:closed?s?|raised?s?|secures?|completes?)\b.*\b(?:round|funding)\b.*\bstartup\b",
    re.IGNORECASE,
)

# LP commitment to existing fund → fundraise (not fund_launch)
_RE_LP_COMMITMENT = re.compile(
    r"\b(?:entra|aderisce|sottoscrive)\s+(?:nel|al|il)\s+(?:fondo|fund)\b"
    r"|\b(?:nuov[oi]\s+)?(?:sottoscrittore|investitore|LP)\s+(?:del|nel|per)\s+(?:il\s+)?(?:fondo|fund)\b",
    re.IGNORECASE,
)

# Fund-level fundraise exclusion (prevents reclassifying fund's own fundraise as deal)
_RE_FUND_LEVEL_FUNDRAISE = re.compile(
    r"\b(?:primo|secondo|terzo|final[e]?)\s+closing\s+(?:del|di|per)\s+(?:il\s+)?(?:fondo|fund|veicolo)\b"
    r"|\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|veicolo)\b"
    r"|\btarget\s+size\b"
    r"|\bhard\s+cap\b"
    r"|\braccolta\s+(?:del|di|per)\s+(?:il\s+)?(?:fondo|fund)\b"
    r"|\braccog\w+.*\b(?:per|for)\s+(?:il\s+proprio\s+|its?\s+own\s+)?(?:fondo|fund)\b"
    r"|\bchiude\s+la\s+raccolta\s+(?:del|di|per|d[i'\u2019])\b"
    r"|\bfirst\s+closing\s+(?:for|of|per)\b"
    r"|\bcommitted?\s+capital\b"
    r"|\bfund\s+(?:i{1,3}|iv|v|vi{1,3}|ix|x|\d+)\s+(?:at|a|di)\s+"
    r"|\boversubscribed\b"
    r"|\bfondo\s+di\s+(?:continuazione|debito|private\s+debt)\b",
    re.IGNORECASE,
)

# Debt restructuring / creditor agreements
# Uses the BROADER version from filter_signals.py which includes "restructuring agreement"
_RE_DEBT_RESTRUCTURING = re.compile(
    r"\baccordo\s+(?:tra|con)\s+(?:il\s+)?(?:i\s+)?creditor\w*\b"
    r"|\baccordo\s+di\s+ristrutturazione\b"
    r"|\bconcordato\b"
    r"|\brestructuring\s+agreement\b",
    re.IGNORECASE,
)

# People title patterns (appointment/joins/promotes)
# filter called it _RE_PEOPLE_TITLE, enricher called it _RE_SENIOR_PEOPLE — same content
_RE_PEOPLE_TITLE = re.compile(
    r"\bappoint\w+|\bjoins?\b|\bpromot\w+\b|\bnamed\b"
    r"|\bnew\s+(?:ceo|cfo|coo|cio|partner)\b"
    # Departure language — leaving/stepping down is also a people_move
    r"|\bleaves?\b|\bleaving\b|\bleft\b|\bresign\w*\b|\bsteps?\s+down\b|\bstepping\s+down\b"
    r"|\bdepart\w*\b|\bdimission\w*\b|\blascia\b|\blasciat\w+\b|\babbandona\b",
    re.IGNORECASE,
)

# "chiude il fondo" patterns — broader than _RE_CHIUDE_RACCOLTA
_RE_CHIUDE_FONDO = re.compile(
    r"\bchiude\s+la\s+raccolta\b|\bchiude\b.*\bfundraising\b|\bcloses\s+fundraising\b"
    r"|\bchiude\b.*\b(?:fondo|fund)\b|\bchiusura\b.*\b(?:fondo|fund)\b",
    re.IGNORECASE,
)

# Value creation marketing
_RE_VALUE_CREATION = re.compile(
    r"\bvalue\s+creation\s+(?:driver|lever|tool|approach)\b",
    re.IGNORECASE,
)

# Event Italian recaps
_RE_EVENT_RECAP_ITALIAN = re.compile(
    r"\bpartner\s+coinvolti\b"
    r"|\bstartup\s+accelerat\w+\b"
    r"|\brete\s+nazionale\s+accelerator\w+\b",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Patterns shared between filter and enricher (previously duplicated inline)
# Moved here Feb 2026 to prevent drift between the two files.
# ─────────────────────────────────────────────────────────────────────────────

# Interviews/editorials without PE content
_RE_INTERVIEW = re.compile(
    r"\bintervist\w+\b|\binterview\w*\b|\bevoluzione\s+editoriale\b"
    r"|\bda\s+settimanale\s+a\b|\bprofile\s+of\b|\bportrait\s+of\b", re.IGNORECASE)

# Portfolio company revenue/performance articles
_RE_REVENUE_PERFORMANCE = re.compile(
    r"\bricavi\s+(?:ricorrenti|netti|totali)\b|\brevenue\s+(?:of|growth|reached|exceeds)\b"
    r"|\braggiunge\s+(?:ricavi|fatturato|vendite)\b|\bfatturato\s+(?:di|pari|a)\b"
    r"|\bebitda\s+shortfall\b|\bchiude\s+(?:la\s+)?settimana\s+in\s+(?:calo|rialzo)\b"
    r"|\bal\s+nasdaq\b.*\btitolo\b", re.IGNORECASE)

# Offer/bid language → deal_announced
_RE_OFFER_BID = re.compile(
    r"\bofferta\s+(?:da|di|per)\s+\d+|\boffer\s+(?:for|of|to\s+acquire)\b"
    r"|\bbid\s+(?:for|of|to\s+acquire)\b|\bofferta\s+(?:vincolante|non\s+vincolante|di\s+acquisto)\b", re.IGNORECASE)

# Office opening / footprint expansion
_RE_OFFICE_OPENING = re.compile(
    r"\bopens?\s+(?:a\s+|an\s+|new\s+)?(?:\w+\s+){0,3}office\b"
    r"|\bapre\s+(?:un\s+)?(?:nuovo\s+)?ufficio\b", re.IGNORECASE)

# Editorial "investment strategy/approach/philosophy" content (no real deal)
_RE_EDITORIAL_STRATEGY = re.compile(
    r"\binvestment\s+(?:strategy|approach|philosophy|thesis|era|landscape)\b"
    r"|\bstrategia\s+d[i'\u2019]\s*investiment[oi]\b"
    r"|\bour\s+(?:approach|strategy|investment\s+process)\b"
    r"|\binvestire\s+in\s+(?:innovazione|crescita|sviluppo|futuro|sostenibilit\w+)\b"
    r"|\b(?:key\s+player|game\s+changer|new\s+era|outlook|perspectives?|trends?)\s+(?:in|for|of)\s+(?:the\s+)?(?:\w+\s+)?(?:investment|market|sector|industry)\b", re.IGNORECASE)

# Accelerator batch results / graduates (NOT launch of a new accelerator)
_RE_ACCELERATOR_RESULTS = re.compile(
    r"\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b.*\b(?:accelerat\w+|programma)\b"
    r"|\b(?:accelerat\w+|programma)\b.*\b(?:risultati|graduates?|selezionat[ei]|completat[oi]|conclus[oi]|demo\s*day|batch)\b",
    re.IGNORECASE)

# Fund launch verbs: explicit "launch/lancia fund/fondo" pattern
_RE_FUND_LAUNCH_VERBS = re.compile(
    r"\b(?:launch|lancia|nasce|nascita|lancio)\b.*\b(?:fund|fondo)\b", re.IGNORECASE)

# Broader fund launch verbs (includes "avvia", "al via" — used in enricher's launch detection)
_RE_LAUNCH_FUND = re.compile(
    r"\b(?:launch|lancia|nasce|nascita|lancio|avvia|al\s+via)\b.{0,80}\b(?:fund|fondo)\b", re.IGNORECASE)

# Regulatory/internal dealing communications
_RE_REGULATORY_COMMUNICATION = re.compile(
    r"\binternal\s+dealing\b"
    r"|\bcomunicazione\s+(?:internal|interna)\b"
    r"|\bcomunicazione\s+internal\s+dealing\b"
    r"|\bsoggetto\s+rilevante\s+mar\b"
    r"|\bregulatory\s+(?:filing|notice|communication)\b"
    r"|\bandamento\s+(?:titolo|in\s+borsa)\b"
    r"|\bprocedura\s+di\s+adempimento\b"
    r"|\blake\s+bidco\b", re.IGNORECASE)

# Acquisition verbs (deal-side language)
_RE_ACQUISITION_VERBS = re.compile(
    r"\b(?:acquir\w+|acquis\w+|acquisizion\w+|investi\w+|rileva"
    r"|entra\s+(?:nel\s+capitale|in)\b|enters?\s+capital|buys?|compra"
    r"|tratt[ai]\s+l[''\u2019]acquisto)\b")

# Internship/stage offers → job_posting
_RE_INTERNSHIP = re.compile(
    r"\b(?:offerta\s+di\s+stage|tirocini[oa]?|stage\s+curriculare)\b")

# Job posting reclassification (procedura di selezione, etc.)
_RE_JOB_POSTING_RECLASSIFY = re.compile(
    r"\b(?:procedura\s+di\s+selezione|ricerca\s+(?:una?\s+)?risors[ae]"
    r"|selezione\s+per\s+(?:il\s+)?(?:ruolo|responsabile|posizione)"
    r"|avvia\s+(?:la\s+)?selezione|seeks?\s+a\s+(?:full|part)[\-\s]time)\b")

# Fundraise closing verbs (completed closes)
_RE_FUNDRAISE_CLOSED_VERBS = re.compile(
    r"\bfinal close\b|\bhard cap\b|\bclosed\b|\bchiude\b|\bchius[oa]\b|\bcomplet\w+\b"
    r"|\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|veicolo|oversubscribed)\b"
    r"|\b(?:primo|secondo|terzo|first|second|third|final|successful)\s+clos(?:e|ing)\b")

# Fundraise verbs full (broader than _RE_FUNDRAISE_CLOSING)
_RE_FUNDRAISE_VERBS_FULL = re.compile(
    r"\bfirst close\b|\bfinal close\b|\bhard cap\b|\bclosed\b|\bclosing\b"
    r"|\bfundrais\w+\b|\braccolta\b|\bchiude\b|\bchiusura\b|\braccog\w+\b")

# Fundraise acquisition (deal verbs in fundraise context)
_RE_FUNDRAISE_ACQUISITION = re.compile(
    r"\brileva\b|\bentra (?:nel capitale|in)\b|\bacquisizion\w*\b|\bacquisisce\b|\bacquir\w+\b|\bcompra\b")

# Debt restructure context (confirms debt intent)
_RE_DEBT_RESTRUCTURE_CONTEXT = re.compile(
    r"\b(?:debt|debito|creditor\w*|creditor[ei]|scadenza\s+del\s+debito|maturity)\b", re.IGNORECASE)

# "raccoglie X milioni/round" patterns
_RE_RACCOGLIE_ROUND = re.compile(
    r"\braccog\w+\b.*\b(?:milion|mln|m€|round|seed|serie|series)\b")
_RE_RACCOGLIE_EXCLUDE = re.compile(
    r"\bacquis\w*\b|\brileva\b|\bentra nel capitale\b")

# Close verbs (general)
_RE_CLOSE_VERBS = re.compile(
    r"\bchiude\b|\bcompleta\b|\bchiusura\b|\bclosed?\b|\bclosing\b", re.IGNORECASE)

# VC round broad detection
_RE_VC_ROUND_BROAD = re.compile(
    r"\b(?:round|serie|series|seed|pre[-\s]?seed)\s+(?:a|b|c|d|e|f|di)\b"
    r"|\bround\s+(?:seed|pre[-\s]?seed)\b"
    r"|\bround\s+(?:d[i'\u2019]\s*)?(?:investimento|finanziamento)\b"
    r"|\bround\s+da\s+\d+|\bincassa\s+(?:nuovo\s+)?round\b"
    r"|\braccog\w+\s+\d+\s*(?:m|mln|milion|k|mila)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:milion\w*|mln|mila)\s+di\s+euro\s+di\s+raccolta\b",
    re.IGNORECASE)

# Investment round in title
_RE_ROUND_INVEST = re.compile(
    r"\bround\s+(?:d[i'\u2019]\s*)?(?:investimento|finanziamento|pre[\-\s]?seed|seed|serie)", re.IGNORECASE)

# Strong deal evidence (acquisition, financing, investment)
_RE_STRONG_DEAL = re.compile(
    r"\bacquis\w+|\bcompra\b|\brileva\b|\bentra\s+nel\s+capitale\b"
    r"|\binvest(?:s|ed|ing)?\s+(?:in|nel)\b"
    r"|\bround\b|\bseries\s+[a-f]\b"
    r"|\bfinanziament[oi]\b|\baumento\s+di\s+capitale\b"
    r"|\bfundrais\w+\b"
    r"|\bsecures?\s+(?:€|\$|£)?\s*[\d.,]+\s*(?:m\b|mln|million|milion|k\b|bn|billion)?\s*(?:investment|funding|financing)?\b"
    r"|\bsecur(?:es?|ing)\b.{0,40}\b(?:investment|funding|financing)\b"
    r"|\binvestitore\s+unic\w*\s+al\s+fianco\s+di\b"
    r"|\bsole\s+investor\s+(?:backing|alongside)\b",
    re.IGNORECASE)

# Team strengthening / senior appointments
_RE_TEAM_STRENGTHENING = re.compile(
    r"\b(?:rafforzamento|potenziamento|ampliamento)\s+(?:del\s+)?(?:team|staff|organico|management)\b"
    r"|\bstrengthens?\b.*\bteam\b|\bsenior\s+appointments?\b"
    r"|\bseries\s+of\s+(?:senior\s+)?appointments?\b", re.IGNORECASE)

# Buyer perspective cues (bidding, interest in acquisition)
_RE_BUYER_CUES = re.compile(
    r"\bin\s+lizza\b|\bpotrebbe\s+essere\s+interessat\w*\b"
    r"|\bpotrebbero\s+essere\s+interessat\w*\b"
    r"|\bvaluta\s+l['\u2019]acqui\w+\b", re.IGNORECASE)

# Merger/fusion patterns
_RE_MERGER = re.compile(
    r"\b(?:fusion[ei]|merger|merg(?:e|es|ed|ing)|fonde|si\s+fondono)\b", re.IGNORECASE)

# Agreement/partnership language (used in exit→partnership reclassification)
_RE_AGREEMENT = re.compile(
    r"\b(?:agreement|accordo|intesa|convenzione)\b", re.IGNORECASE)
_RE_AGREEMENT_PARTNERSHIP_CONTEXT = re.compile(
    r"\b(?:partnership|collaborazione|gestione|manage|management|tenders?|bando)\b", re.IGNORECASE)

# Advisory board formation (not a hire/appointment)
_RE_ADVISORY_BOARD = re.compile(
    r"\b(?:advisory\s+board|comitato\s+(?:scientifico|consultivo))\b", re.IGNORECASE)

# Fund compartment becomes operational → fund_launch
_RE_FUND_COMPARTMENT_OPERATIONAL = re.compile(
    r"\boperativ[oa]\s+(?:il\s+)?comparto\b|\bcomparto\b.*\boperativ[oa]\b", re.IGNORECASE)

# Fundraise closing in deal context
_RE_CLOSING_FUND = re.compile(
    r"\bclosing\s+(?:del|di|per|of)\s+(?:il\s+)?(?:fondo|fund|oversubscribed)\b", re.IGNORECASE)

# Portfolio company backed/partecipata patterns
# NOTE: acquir\w+ covers English "acquires/acquired/acquiring"; acquis\w+ covers Italian/formal "acquisisce/acquisizione"
_RE_PORTFOLIO_COMPANY_BACKED = re.compile(
    r"\b(?:partecipata|sostenuta|backed)\b.*\b(?:acquis\w+|acquir\w+|complet\w+|espand\w+|expand\w+|rafforz\w+)",
    re.IGNORECASE)

# Portfolio company as acquirer — portfolio company (not the fund) is making the acquisition.
# Covers the full family of phrasings where a PORTFOLIO COMPANY is the acquirer, not the fund.
# These must be classified portfolio_update, not deal_announced.
#
# Key insight: "deal_announced" = fund deploys capital; "portfolio_update" = portfolio company acts.
# When Facile.it (Silver Lake portfolio co) acquires X, Silver Lake didn't make a new investment —
# its existing portfolio company made an add-on acquisition. → portfolio_update.
_RE_PORTFOLIO_CO_AS_ACQUIRER = re.compile(
    # "[Fund]-backed/-owned/-controlled [Company] acquires" — hyphenated compound adjective.
    # Requires at least one word between "backed" and the acquisition verb (guards against
    # "[Fund]-backed acquisition of X" which is a fund-level deal, not portfolio co M&A).
    r"\b\w+[\-\u2010\u2011\u2012\u2013](?:backed|owned|controlled)\b\s+\w.{0,100}\b(?:acquir\w+|merg\w+|purchas\w+)\b"
    # "backed by [Fund] ... acquires/merges" — fund name in non-principal position
    r"|\bbacked\s+by\b.{0,120}\b(?:acquir\w+|merg\w+|purchas\w+)\b"
    # "portfolio company acquires" — explicit portfolio language with acquisition verb
    r"|\bportfolio\s+compan(?:y|ies)\b.{0,120}\b(?:acquir\w+|merg\w+)\b"
    # Italian: "partecipata/sostenuta/controllata da/di [Fund] acquires"
    r"|\b(?:partecipata|sostenuta|controllata)\s+(?:da|di|by)\b.{0,120}\b(?:acquir\w+|acquis\w+|merg\w+)\b"
    # Italian: "tramite la sua partecipata/controllata ... acquires"
    r"|\btramite\s+(?:la\s+sua\s+)?(?:partecipata|controllata)\b.{0,120}\b(?:acquir\w+|acquis\w+)\b"
    # "promoted/controlled by [Fund] ... acquires/expands" (Italian-English hybrid)
    r"|\b(?:promoted|controllat[oa]|promoss[oa]|controlled)\s+(?:by|da)\b.{0,120}\b(?:acquir\w+|espand\w+|expand\w+|merg\w+)\b"
    # Bolt-on/add-on/tuck-in acquisition — BY DEFINITION portfolio company M&A
    r"|\b(?:add[\-\s]?on|bolt[\-\s]?on|tuck[\-\s]?in)\s+(?:acqui\w+|deal|investment|operazion\w+)\b"
    r"|\b(?:acqui\w+|deal)\b.{0,30}\b(?:add[\-\s]?on|bolt[\-\s]?on|tuck[\-\s]?in)\b"
    # "Company (Fund) acquires" — BeBeez-style parenthetical fund name.
    # The first char of the parenthetical must be a letter (guards against year "(2024)" etc.).
    # E.g.: "Lexham Power (EOS IM) acquires Innovo Agri",
    #        "Bianalisi (Charme+Columna) acquires X",
    #        "Phenna Group (Oakley Capital) makes sixth acquisition"
    r"|\b\w[\w\s.,'-]{2,50}\s+\([A-Za-z][^)]{2,59}\)\s*.{0,60}\b(?:acquir\w+|acquis\w+|merg\w+)\b",
    re.IGNORECASE,
)

# Interview patterns (for people_move/partnership reclassification)
_RE_INTERVIEW_EDITORIAL = re.compile(
    r"\bintervist\w+\b|\binterview\w*\b|\bsits?\s+down\s+with\b|\breflects?\s+on\b"
    r"|\bexplains?\b|\bspiega\b|\bracconta\b", re.IGNORECASE)

# People-related language (to confirm people_move signals)
_RE_PEOPLE_LANGUAGE = re.compile(
    r"\b(?:nomin\w+|hired?|joins?|joined|promot\w+|assume\s+(?:il\s+)?(?:ruolo|incarico)"
    r"|entra\s+(?:nel\s+)?(?:team|consiglio|cda)|nuovo\s+(?:ingresso|membro)"
    r"|new\s+(?:team\s+)?member"
    # Departure language — stepping down / leaving is still a people move
    r"|steps?\s+down|stepping\s+down|leaves?|leaving|left\s+(?:the\s+)?(?:firm|fund|company|role)"
    r"|resign\w*|depart\w*|dimission\w*|lascia|lasciat\w+|abbandona"
    r"|succession\w*|succeed\w*|replac\w+"
    # "names/appoints X as [role]" — announcement phrasing
    r"|names?\s+\w[\w\s]{1,40}\s+as\s+(?:(?:new|incoming|interim|acting)\s+)?(?:head|chief|director|managing\s+director|partner|president|vice|senior)"
    r"|appoints?\s+\w[\w\s]{1,40}\s+as\s+(?:(?:new|incoming|interim|acting)\s+)?(?:head|chief|director|managing\s+director|partner|president|vice|senior)"
    r"|appointed\s+(?:as\s+)?(?:(?:new|incoming|interim|acting)\s+)?(?:head|chief|director|managing\s+director|partner|president|vice|senior)"
    r")\b", re.IGNORECASE)

# Appointment verbs (for advisory board context check)
_RE_APPOINTMENT_VERBS = re.compile(
    r"\b(?:appoint\w+|nomin\w+|joins?|entra)\b", re.IGNORECASE)

# Broad appointment rescue for the "other" rescue path in apply_type_corrections().
# Looser than _RE_PEOPLE_LANGUAGE (uses .* between verb and role) — intentional: rescues signals
# that were demoted to other but clearly describe an appointment (e.g. "appointed ... CEO").
_RE_PEOPLE_APPOINTMENT_RESCUE = re.compile(
    r"\b(?:names?|appoints?|appointed|hired?)\b.*\b(?:head|director|partner|managing|chief"
    r"|ceo|cfo|coo|cto|president|chairman)\b",
    re.IGNORECASE,
)

# Team page profile noise: "Name Surname [optional seniority] [role title]" with no transition verb.
# Catches static team listing pages where the signal is just "Person Name — Title" with no PE event.
# Used in correct_people_move() and apply_type_corrections() other-rescue.
_RE_TEAM_PROFILE_NOISE = re.compile(
    r"^[a-zà-öø-ÿ][a-zà-öø-ÿ''.\-]+(?:\s+[a-zà-öø-ÿ][a-zà-öø-ÿ''.\-]+){1,3}\s+"
    r"(?:(?:managing|senior|junior|lead|principal|chief)\s+)?"
    r"(?:head|director|manager|partner|officer|counsel|analyst|associate|specialist"
    r"|investor\s+relations"
    r"|legal\s*(?:&|and)\s*corporate\s+affairs(?:\s+(?:specialist|manager|head|director))?)\b",
    re.IGNORECASE,
)

# Role-opening / job-posting titles misclassified as people_move.
# Example: "Senior Investment Associate, Clean Energy - Capital Dynamics"
# Used in correct_people_move() and apply_type_corrections() other-rescue.
_RE_ROLE_OPENING_TITLE = re.compile(
    r"^\s*(?:senior|junior|lead|principal|chief|head|managing)?\s*"
    r"(?:investment\s+)?(?:associate|analyst|manager|specialist|advisor|officer|counsel|director)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants shared between filter and enricher
# ─────────────────────────────────────────────────────────────────────────────

BULK_TEAM_EXTRACTION_THRESHOLD = 25

GENERIC_PORTFOLIO_NAME_TOKENS = {
    "fund", "fonds", "fondo", "fondi",
    "investment", "investments", "investimento", "investimenti", "investors", "investitori",
    "portfolio", "portafoglio", "companies", "company", "societa", "società",
    "holding", "holdings", "group", "gruppo", "partners", "partner", "capital",
    "management", "asset", "assets", "real", "estate", "infrastructure", "energy",
    "transition", "credit", "private", "equity", "venture", "project", "projects",
    "platform", "solutions", "services", "strategie",
    "sgr", "spa", "s.p.a", "srl", "s.r.l", "sa", "s.a", "sas", "sarl", "ltd", "inc", "llc",
}

GENERIC_PORTFOLIO_TARGET_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^our activities\b",
        r"^our latest news\b",
        r"^our companies\b",
        r"^our portfolio\b",
        r"^portfolio companies\b",
        r"^current portfolio\b",
        r"^prior investments\b",
        r"^ourportfoliocompanies\b",
        r"^portfolio\b",
    ]
]

PORTFOLIO_EXTRACTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"detected via extraction",
        r"via extraction",
    ]
]

PORTFOLIO_DELTA_EVIDENCE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\binvestment date\b",
        r"\bdata di investimento\b",
        r"\bacquisition date\b",
        r"\bentry date\b",
    ]
]


# ─────────────────────────────────────────────────────────────────────────────
# Utility functions shared between filter and enricher
# ─────────────────────────────────────────────────────────────────────────────

# Read-time noise patterns (used by _strip_read_time)
_READ_TIME_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b\d+\s*min(?:ute)?s?\s*read\b",
        r"\b\d+\s*min\.?\s*read\b",
        r"\b\d+\s*min(?:uto|uti)\s*di\s*lettura\b",
        r"\btempo\s+di\s+lettura\b",
        r"\bread\s+time\b",
    ]
]

# URL pattern (used by _strip_urls)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _strip_read_time(text: str) -> str:
    """Remove read-time artifacts like '5 min read' from text."""
    if not text:
        return text
    cleaned = text
    for pattern in _READ_TIME_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" -|").strip()


def _strip_urls(text: str) -> str:
    """Remove embedded URLs from text."""
    if not text:
        return text
    cleaned = _URL_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _is_generic_portfolio_name(name: str) -> bool:
    """Check if a name is generic (not a real company name).

    Uses the MORE COMPLETE version from filter_signals.py which includes
    additional checks for fund-internal section headers and alphanumeric brand names.
    """
    if not name:
        return True
    cleaned = re.sub(r"\([^)]*\)", "", name).strip()
    # Fund-internal section headers: INVESTIMENTI GAPEF 3, REALIZZATE FONDO Q2, etc.
    if re.match(
        r"^(?:investimenti|realizzate|realizzati|operazioni|partecipazioni)\s+",
        cleaned,
        re.IGNORECASE,
    ):
        return True
    # Italian website section headers misextracted as portfolio company names
    if re.match(
        r"^(?:esigenz[ei]|requisiti|criteri|caratteristiche|tipologi[ae]|settori?\s+di|"
        r"informazion[ie]|mission[ei]?|strategi[ae]|modalit[aà]|interventi?|"
        r"strumenti?\s+di|il\s+processo|le\s+fasi|ambiti?\s+di)\b",
        cleaned,
        re.IGNORECASE,
    ):
        return True
    raw_tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", cleaned)
    if not raw_tokens:
        return True
    tokens = [t.lower() for t in raw_tokens]
    if all(t.isdigit() for t in tokens):
        return True
    # Allow short alphanumeric brand names (e.g., R3, 3i, 2Hire)
    for raw in raw_tokens:
        if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", raw) and re.search(r"\d", raw):
            return False
        if raw.isupper() and len(raw) <= 3 and raw.lower() not in GENERIC_PORTFOLIO_NAME_TOKENS:
            return False
    non_generic = [t for t in tokens if t not in GENERIC_PORTFOLIO_NAME_TOKENS and not t.isdigit()]
    if not non_generic:
        return True
    if all(len(t) <= 3 for t in non_generic):
        return True
    return False


def _extract_portfolio_company_name(signal: dict, summary: str, title: str) -> str:
    """Extract portfolio company name from a signal.

    Uses the MORE COMPLETE version from filter_signals.py which includes
    additional label stripping for "New investment:", "New exit:", etc.
    """
    entities = signal.get("extracted_entities") or {}
    companies = entities.get("companies") or []
    if companies:
        return str(companies[0]).strip()
    candidate = (summary or title or "").strip()
    if not candidate:
        return ""
    # Strip leading labels like "New investment:" / "New exit:" / "New portfolio investment:"
    candidate = re.sub(
        r"^(?:new\s+(?:portfolio\s+)?(?:investment|exit|deal|portfolio)|portfolio\s+(?:investment|exit))\s*[:\-–]\s*",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\([^)]*\)", "", candidate).strip()
    candidate = re.split(
        r"\s+\bin\b|\s+\bnel\b|\s+\bnella\b|\s+-\s+|\s+–\s+|\s+\|\s+",
        candidate, maxsplit=1, flags=re.IGNORECASE,
    )[0].strip()
    m = re.match(r"^(.+?)(?:\s+\b(is|was|è|era|sono)\b)", candidate, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    return candidate
