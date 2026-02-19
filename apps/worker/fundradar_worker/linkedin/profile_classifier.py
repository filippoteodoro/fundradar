"""
Profile classifier for analyzing employee backgrounds.

Classifies LinkedIn profiles by professional background (IB, PE, consulting, etc.)
and extracts structured data for people analytics.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .people_scraper import LinkedInProfile, Experience, Education

logger = logging.getLogger(__name__)


class BackgroundType(str, Enum):
    """Professional background categories."""

    INVESTMENT_BANKING = "investment_banking"
    PRIVATE_EQUITY = "private_equity"
    VENTURE_CAPITAL = "venture_capital"
    CONSULTING = "consulting"
    BIG_FOUR = "big_four"
    CORPORATE = "corporate"
    TECH = "tech"
    STARTUP = "startup"
    LEGAL = "legal"
    OTHER = "other"


class SeniorityLevel(str, Enum):
    """Seniority levels in PE/VC."""

    PARTNER = "partner"
    MANAGING_DIRECTOR = "managing_director"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VICE_PRESIDENT = "vice_president"
    ASSOCIATE = "associate"
    ANALYST = "analyst"
    OTHER = "other"


@dataclass
class ClassifiedProfile:
    """A profile with background classification."""

    profile: LinkedInProfile
    primary_background: BackgroundType
    secondary_backgrounds: list[BackgroundType] = field(default_factory=list)
    current_seniority: SeniorityLevel = SeniorityLevel.OTHER
    years_experience: float | None = None
    tenure_at_current: float | None = None
    education_tier: str | None = None  # "top_mba", "top_undergrad", "other"
    estimated_gender: str | None = None  # "male", "female", None
    classification_details: dict[str, Any] = field(default_factory=dict)


# Company classification for background detection
IB_COMPANIES = [
    "goldman sachs", "morgan stanley", "jp morgan", "jpmorgan",
    "bank of america", "merrill lynch", "credit suisse", "ubs",
    "deutsche bank", "barclays", "citigroup", "lazard", "evercore",
    "moelis", "centerview", "perella weinberg", "rothschild",
    "mediobanca", "banca imi", "intesa sanpaolo", "unicredit",
    "banca akros", "equita", "jefferies", "piper sandler",
    # Defunct IB firms (still common in senior professionals' histories)
    "lehman brothers", "bear stearns", "dresdner", "wachovia",
    "banca commerciale italiana", "banca caboto",
    # European banks active in Italian M&A market
    "societe generale", "sgcib", "bnp paribas", "credit agricole", "natixis",
    "nomura", "hsbc", "commerzbank", "ing bank", "abn amro",
    "rabobank", "banca mediolanum",
    "ubi banca", "banco bpm", "mps", "monte dei paschi",
    "banca sella", "sella bank", "sella group", "ersel",
    "banca popolare di milano", "banca popolare di sondrio",
    # Italian/European IB boutiques
    "houlihan lokey", "lincoln international", "dc advisory",
    "alantra", "oaklins", "banca leonardo", "leonardo & co",
    "fineurop", "citi", "degroof petercam", "kempen",
    "intermonte", "banca finnat",
    "centrobanca", "credito emiliano", "credem",
    # Asset managers with IB/trading operations
    "carmignac", "schroders", "fidelity", "vanguard", "pimco",
    "blackrock", "amundi", "generali investments",
]

PE_COMPANIES = [
    "kkr", "blackstone", "carlyle", "apollo", "tpg", "warburg pincus",
    "advent international", "bain capital", "cvc", "permira",
    "cinven", "bc partners", "pai partners", "ardian", "investindustrial",
    "clessidra", "peninsula", "nb renaissance", "wise equity", "alcedo",
    "xenon", "fondo italiano", "progressio", "mindful capital",
    "dea capital", "quadrivio", "ambienta", "f2i", "trilantic",
    "h.i.g.", "hig capital", "eurazeo", "sagard",
    # Italian PE/VC funds from our DB (common in senior professionals' histories)
    "21 invest", "21investimenti", "investitori associati", "value partners",
    "the equity club", "l catterton", "lcatterton",
    "nb private equity", "nb aurora", "renaissance partners",
    "verde sgr", "argos wityu", "nuo capital", "palladio",
    "charme capital", "astorg", "oakley capital", "towerbrook",
    "portobello capital", "sofinnova", "sofipa",
    "bridgepoint", "eqt", "apax",
    "intermediate capital", "icg", "ares management",
    # More Italian/European PE funds frequently in backgrounds
    "fsi investimenti", "fsi sgr", "fsi", "algebris",
    "invitalia",  # Italian public investment agency — in our DB
    "neuberger berman", "nb investment",
    "finint investments", "finint",
    "axon partners", "wrm group", "wrm capital",
    "green arrow capital", "green arrow",
    "claris ventures", "oltre impact",
    "friulia", "antin infrastructure",
    "europa investimenti", "ethica corporate finance",
    "aurora growth capital", "aurora growth",
    "prelios", "castello sgr",
    "alter domus",  # fund admin — borderline but PE-adjacent
    # Italian PE/VC funds found via classifier audit (appearing in employee histories)
    "pillarstone", "amber capital", "nextalia", "quattrор", "quattror",
    "rancilio cube", "alkemia capital", "apeiron",
    "ventiseidieci", "faro value", "zest group",
    "xgen venture", "mito technology",
    "tikehau", "cerberus", "oaktree", "lone star",
    "advent", "macquarie", "partners group",
    "andera partners", "idinvest", "eurizon",
    "banca generali", "azimut",
    "fondazione", "cdp equity",
]

VC_COMPANIES = [
    "sequoia", "andreessen horowitz", "a16z", "kleiner perkins",
    "accel", "index ventures", "general catalyst", "founders fund",
    "p101", "united ventures", "vertis", "indaco", "primo ventures",
    "cdp venture", "360 capital", "italian angels", "digital magics",
    "lventure", "liftt", "scientifica", "eureka!", "eureka venture",
    # Italian VC funds found in employee histories
    "five seasons ventures", "eit digital", "plug and play",
    "techstars", "y combinator", "500 startups",
    "neva sgr", "oltre venture",
]

CONSULTING_COMPANIES = [
    "mckinsey", "mck ", "bain", "boston consulting", "bcg",
    "roland berger", "oliver wyman", "strategy&", "at kearney",
    "kearney", "lep", "arthur d. little", "simon-kucher",
    "monitor deloitte", "pa consulting", "capgemini", "ibm consulting",
    "alixpartners", "prometeia", "zeb consulting",
    "marsh & mclennan", "mercer", "willis towers watson",
    "the boston consulting group",
]

BIG_FOUR = [
    "deloitte", "pwc", "pricewaterhousecoopers", "price waterhouse",
    "ey", "ernst & young", "ernst and young",
    "kpmg", "accenture",
    "arthur andersen", "coopers & lybrand",  # defunct Big Four/Five
    "grant thornton", "bdo", "mazars", "crowe", "rsm",
]

LAW_FIRMS = [
    "allen & overy", "allen and overy", "a&o shearman",
    "clifford chance", "freshfields", "linklaters", "slaughter and may",
    "hogan lovells", "white & case", "cleary gottlieb",
    "latham & watkins", "skadden", "kirkland & ellis",
    "gianni origoni", "dla piper", "bird & bird",
    "bonelli erede", "chiomenti", "gattai", "lombardi",
    "pedersoli", "legance", "dla", "nctm",
    "studio legale", "law firm",
    # Additional global/European law firms
    "baker mckenzie", "baker & mckenzie", "norton rose", "herbert smith",
    "ashurst", "simmons & simmons", "dentons", "cms",
    "weil gotshal", "sullivan & cromwell", "davis polk",
    "jones day", "sidley austin", "mayer brown",
    "shearn delamore", "shearman & sterling",
    # Italian law firms
    "toffoletto", "de berti jacchia", "orrick", "osborne clarke",
    "studio tributario", "studio professionale",
    "grimaldi studio legale", "pirola pennuto",
]

# Top MBA programs
TOP_MBA_SCHOOLS = [
    "harvard business school", "hbs", "stanford gsb", "stanford graduate school",
    "wharton", "booth", "kellogg", "columbia business school", "mit sloan",
    "insead", "london business school", "lbs", "iese", "sda bocconi",
    "bocconi", "ie business school", "esade", "hec paris",
]

# Top undergrad programs (finance focus)
TOP_UNDERGRAD = [
    "bocconi", "luiss", "politecnico di milano", "politecnico milano",
    "cambridge", "oxford", "lse", "london school of economics",
    "harvard", "yale", "princeton", "mit", "stanford",
]

# Seniority title patterns
SENIORITY_PATTERNS = {
    SeniorityLevel.PARTNER: [
        r"\bpartner\b", r"\bmanaging partner\b", r"\bgeneral partner\b",
        r"\bsenior partner\b", r"\bfounding partner\b",
        r"\bfounder\b", r"\bco-founder\b", r"\bceo\b", r"\bchief executive\b",
        # Board / Chairman / President
        r"\bchairman\b", r"\bchairperson\b", r"\bpresident\b", r"\bpresidente\b",
        r"\bboard member\b", r"\bmember.*board\b", r"\bboard of directors\b",
        r"\bconsigliere\b", r"\bmembro del consiglio\b",
        r"\badvisory board\b", r"\bboard observer\b",
        # Italian CEO
        r"\bamministratore delegato\b", r"\bad\b(?=\s|$)",
        # Senior advisor
        r"\bsenior advisor\b", r"\bsenior adviser\b",
    ],
    SeniorityLevel.MANAGING_DIRECTOR: [
        r"\bmanaging director\b", r"\bmd\b", r"\bsenior managing director\b",
        r"\bcfo\b", r"\bcoo\b", r"\bcto\b", r"\bchief \w+ officer\b",
        r"\bhead of\b", r"\bdirettore generale\b",
        # Italian director/head titles
        r"\bdirettore\b", r"\bresponsabile\b",
        r"\bgeneral counsel\b", r"\bcounsel\b",
    ],
    SeniorityLevel.PRINCIPAL: [
        r"\bprincipal\b", r"\bsenior principal\b",
        # Generic investment professional → mid-senior
        r"\binvestment professional\b", r"\bprivate equity\b(?!.*(?:analyst|associate|intern))",
        r"\binvestor\b",
    ],
    SeniorityLevel.DIRECTOR: [
        r"\bdirector\b", r"\bsenior director\b", r"\binvestment director\b",
    ],
    SeniorityLevel.VICE_PRESIDENT: [
        r"\bvice president\b", r"\bvp\b", r"\bavp\b", r"\bsenior vp\b",
        r"\bmanager\b", r"\bsenior manager\b",
        # Italian finance roles
        r"\bcontroller\b", r"\bcompliance officer\b",
        r"\binvestor relations\b",
    ],
    SeniorityLevel.ASSOCIATE: [
        r"\bassociate\b", r"\bsenior associate\b", r"\binvestment associate\b",
    ],
    SeniorityLevel.ANALYST: [
        r"\banalyst\b", r"\bsenior analyst\b", r"\binvestment analyst\b",
        r"\banalista\b",
        r"\bintern\b", r"\bstagiaire\b", r"\btirocinio\b",
        r"\bjunior\b",
    ],
}

# Common Italian first names for gender estimation
MALE_NAMES = [
    "alessandro", "andrea", "antonio", "carlo", "claudio", "davide",
    "emanuele", "fabio", "federico", "filippo", "francesco", "giacomo",
    "gianluca", "giorgio", "giovanni", "giuseppe", "luca", "luigi",
    "marco", "mario", "massimo", "matteo", "maurizio", "michele",
    "nicola", "paolo", "pietro", "riccardo", "roberto", "salvatore",
    "sergio", "simone", "stefano", "tommaso", "vincenzo",
    "john", "michael", "david", "james", "william", "robert", "thomas",
]

FEMALE_NAMES = [
    "alessandra", "alice", "anna", "arianna", "beatrice", "camilla",
    "chiara", "claudia", "cristina", "elena", "eleonora", "elisa",
    "elisabetta", "emanuela", "federica", "francesca", "gabriella",
    "giulia", "ilaria", "irene", "laura", "lucia", "marta", "martina",
    "maria", "marina", "monica", "paola", "roberta", "sara", "serena",
    "silvia", "simona", "sofia", "stefania", "valentina", "veronica",
    "emma", "sarah", "jennifer", "jessica", "emily", "elizabeth",
]


def _normalize_company(name: str) -> str:
    """Normalize company name for matching: lowercase, strip accents, remove dots."""
    # Strip accents: Crédit → Credit, José → Jose
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = nfkd.encode("ascii", "ignore").decode()
    # Remove dots (handles "J.P. Morgan" → "jp morgan"), collapse spaces
    no_dots = ascii_name.replace(".", "")
    return re.sub(r"\s+", " ", no_dots.lower()).strip()


def _check_company_list(company: str, company_list: list[str]) -> bool:
    """Check if company name matches any in list (dot/accent-normalized)."""
    company_norm = _normalize_company(company)
    for target in company_list:
        if target in company_norm:
            return True
    return False


def _classify_experience(exp: Experience) -> BackgroundType | None:
    """Classify a single experience entry."""
    company = exp.company or ""
    title = exp.title or ""
    combined = f"{company} {title}".lower()
    company_lower = company.lower()
    company_norm = _normalize_company(company)  # dots/accents stripped for matching

    # 1. Known company name matching (highest confidence)
    if _check_company_list(company, IB_COMPANIES):
        return BackgroundType.INVESTMENT_BANKING
    if _check_company_list(company, PE_COMPANIES):
        return BackgroundType.PRIVATE_EQUITY
    if _check_company_list(company, VC_COMPANIES):
        return BackgroundType.VENTURE_CAPITAL
    if _check_company_list(company, CONSULTING_COMPANIES):
        return BackgroundType.CONSULTING
    if _check_company_list(company, BIG_FOUR):
        return BackgroundType.BIG_FOUR
    if _check_company_list(company, LAW_FIRMS):
        return BackgroundType.LEGAL

    # 2. Structural company name patterns (catches PE/VC/IB not in hardcoded lists)
    # SGR = Società di Gestione del Risparmio — Italian regulated fund manager
    if re.search(r'\bsgr\b', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    # SICAF/SICAV = Italian/EU regulated investment vehicles
    if re.search(r'\b(sicaf|sicav)\b', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    # "Investments" / "Investimenti" as standalone word = investment firm
    # e.g. "Algebris Investments", "Europa Investimenti", "Athena Investments A/S"
    if re.search(r'\b(investments?|investimenti)\b', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    if any(kw in company_lower for kw in ["private equity", "private capital", "buyout fund"]):
        return BackgroundType.PRIVATE_EQUITY
    if any(kw in company_lower for kw in ["venture capital", "venture fund", "ventures"]):
        return BackgroundType.VENTURE_CAPITAL
    # "Capital" + finance word → PE (e.g. "Charme Capital Partners", "Green Arrow Capital SGR")
    if re.search(r'\bcapital\b.*(partner|group|advisor|management|invest)', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    # Standalone "Capital" as company name component (e.g. "Amber Capital", "Tikehau Capital")
    if re.search(r'\bcapital\b', company_lower) and len(company_lower.split()) <= 4:
        return BackgroundType.PRIVATE_EQUITY
    # "[Finance word] Partners" → PE (e.g. "Antin Infrastructure Partners")
    if re.search(r'\b(equity|infrastructure|growth|buyout|impact|debt|credit)\b.*\bpartners?\b', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    # "Investment Partners" or "Investment Management" as name component
    if re.search(r'\binvestment\s+(partner|manager|management|group|advisor)', company_lower):
        return BackgroundType.PRIVATE_EQUITY
    # "Asset Management" company names
    if re.search(r'\basset\s+management\b', company_lower):
        return BackgroundType.PRIVATE_EQUITY

    # 3. Title/combined keywords — English and Italian
    if any(kw in combined for kw in [
        "investment bank", "m&a", "corporate finance", "ecm", "dcm",
        "leveraged finance", "debt capital", "capital markets",
        "fusioni", "acquisizioni", "mercati dei capitali", "finanza aziendale",
        "trader", "trading", "sales & trading", "structured finance",
        "equity research", "fixed income", "equity sales",
    ]):
        return BackgroundType.INVESTMENT_BANKING
    if any(kw in combined for kw in [
        "private equity", "buyout", "lbo", "growth equity",
        "portfolio company", "fund manager", "fund management",
        "gestore di fondi", "gestore fondi", "gestore del fondo",
        "investment professional", "deal origination", "deal sourcing",
        "infrastructure fund", "alternative investment",
        "portfolio manager", "private credit", "private debt",
        "fund of funds", "asset allocation",
        "investment associate", "investment analyst",
        "principal investing",
    ]):
        return BackgroundType.PRIVATE_EQUITY
    if any(kw in combined for kw in [
        "venture capital", "vc ", "seed", "series a", "early stage",
        "tech transfer", "startup investor",
        "venture partner", "venture analyst",
        "accelerator", "incubator",
    ]):
        return BackgroundType.VENTURE_CAPITAL
    if any(kw in combined for kw in [
        "consultant", "consulting", "consulente", "consulenza",
        "strategy", "advisory", "adviseur",
    ]):
        return BackgroundType.CONSULTING
    if any(kw in combined for kw in [
        "lawyer", "attorney", "legal counsel", "avvocato", "notaio",
        "solicitor", "paralegal", "legal associate", "legal advisor",
        "barrister", "legal department", "ufficio legale",
        "trainee solicitor", "legal intern",
    ]):
        return BackgroundType.LEGAL
    if any(kw in combined for kw in [
        "engineer", "developer", "cto", "tech lead", "ingegnere",
        "data scientist", "machine learning", "software",
    ]):
        return BackgroundType.TECH
    if any(kw in combined for kw in ["founder", "co-founder", "startup"]):
        return BackgroundType.STARTUP

    # 4. Corporate — positive match on known industrials, roles, and entity patterns.
    if any(kw in combined for kw in [
        "corporate", "industry", "industrial", "manufacturing", "operations",
        "supply chain", "procurement", "logistics", "purchasing", "buyer",
        "marketing manager", "marketing director", "marketing",
        "sales manager", "sales director", "head of sales",
        "product manager", "general manager", "country manager",
        "brand manager", "commercial", "business development",
        "financial analyst", "financial controller", "finance manager",
        "fund account", "credit analyst", "risk analyst",
        "real estate", "asset manag",
        "human resources", "hr manager", "hr director",
        "cfo", "chief financial", "chief operating", "chief marketing",
        "direttore commerciale", "responsabile commerciale",
        "direttore generale", "responsabile",
        "trainer", "department manager",
        # Broader corporate role patterns
        "project manager", "program manager",
        "account manager", "key account",
        "head of strategy", "head of business",
        "managing director",  # at non-finance companies
        "chief executive", "ceo",
        "innovation manager", "r&d", "research and development",
        "quality manager", "compliance",
        "controller", "auditor", "internal audit",
        "treasury", "treasurer",
        "insurance", "assicurazion",
        "retail", "hospitality", "tourism",
        "telecom", "energy", "pharma", "automotive",
    ]):
        return BackgroundType.CORPORATE
    corporate_patterns = [
        r"\b(spa|srl|s\.p\.a|s\.r\.l)\b",  # Italian corporate suffixes
        r"\b(inc|corp|ltd|plc|ag|gmbh|nv|sa)\b",  # Global corporate suffixes
        r"\b(sas|sarl|bv|pty)\b",  # More international corporate suffixes
    ]
    if any(re.search(p, company_lower) for p in corporate_patterns):
        return BackgroundType.CORPORATE

    return BackgroundType.OTHER


def _get_seniority(title: str) -> SeniorityLevel:
    """Determine seniority level from title."""
    title_lower = title.lower()

    for level, patterns in SENIORITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_lower):
                return level

    return SeniorityLevel.OTHER


def is_investment_relevant(profile: "LinkedInProfile") -> bool:
    """
    Return False for support staff who are not relevant to investors/fund analytics:
    IT staff, HR, admin, secretaries, office managers.

    Investor relations, compliance, ESG, CFO, and all investment roles are kept.
    """
    # Get the person's current title
    current_exp = next((e for e in profile.experience if e.is_current), None)
    title = ((current_exp.title if current_exp else None) or profile.headline or "").lower()

    if not title or title.strip() in ("--", ""):
        return True  # No title info — keep by default

    # --- Exclude: IT and tech support ---
    it_patterns = [
        r"\bit\b.*(manager|director|specialist|operations|program|infrastructure|advisor|coordinator)",
        r"(helpdesk|help desk|sysadmin|system admin|network admin)",
        r"software engineer",
        r"\bprogrammer\b",
    ]
    if any(re.search(p, title) for p in it_patterns):
        return False

    # --- Exclude: HR and talent ---
    hr_patterns = [
        r"\b(human resources?|risorse umane)\b",
        r"\bhr\s+(manager|director|specialist|partner|coordinator)\b",
        r"(talent acquisition|talent management)",
        r"\brecruiter\b",
        r"\brecruiting\b",
        r"responsabile.*risorse umane",
        r"sviluppo risorse umane",
    ]
    if any(re.search(p, title) for p in hr_patterns):
        return False

    # --- Exclude: admin and secretarial ---
    admin_patterns = [
        r"\bsegretari[ao]\b",           # segretaria, segretario
        r"segreteria",
        r"\breception(ist)?\b",
        r"assistente (amministrativ|di direzione|di team)",
        r"(administrative|executive) assistant",
        r"personal assistant",
        r"\boffice manager\b",
        r"impiegat[ao].*amministra",     # impiegata area amministrazione
    ]
    if any(re.search(p, title) for p in admin_patterns):
        return False

    # --- Exclude: blue collar, retail, back office support ---
    other_exclude = [
        r"\boperai[ao]\b",              # factory worker
        r"\boperario\b",
        r"\bcommess[ao]\b",             # retail clerk
        r"\bback office\b",
        r"\boffice assistant\b",
        r"\bmiddle office\b",
        r"\bsindaco effettivo\b",        # statutory auditor (non-investment)
        r"\bdottore commercialista\b",
    ]
    if any(re.search(p, title) for p in other_exclude):
        return False

    return True


def _classify_education(education: list[Education]) -> str | None:
    """Classify education tier."""
    for edu in education:
        school_lower = edu.school.lower() if edu.school else ""
        degree_lower = (edu.degree or "").lower()

        # Check for MBA
        if "mba" in degree_lower or "master in business" in degree_lower:
            if any(top in school_lower for top in TOP_MBA_SCHOOLS):
                return "top_mba"

        # Check for top undergrad
        if any(top in school_lower for top in TOP_UNDERGRAD):
            return "top_undergrad"

    return "other"


def _calculate_years_experience(experience: list[Experience]) -> float | None:
    """Calculate total years of experience."""
    if not experience:
        return None

    # Find earliest start date
    earliest_year = None
    for exp in experience:
        if exp.start_date:
            try:
                year = int(exp.start_date.split("-")[0])
                if earliest_year is None or year < earliest_year:
                    earliest_year = year
            except (ValueError, IndexError):
                continue

    if earliest_year:
        current_year = datetime.now().year
        return float(current_year - earliest_year)

    return None


def _calculate_tenure(experience: list[Experience]) -> float | None:
    """Calculate tenure at current position."""
    for exp in experience:
        if exp.is_current and exp.start_date:
            try:
                start_year = int(exp.start_date.split("-")[0])
                start_month = int(exp.start_date.split("-")[1]) if "-" in exp.start_date else 1
                now = datetime.now()
                years = now.year - start_year
                months = now.month - start_month
                return round(years + months / 12, 1)
            except (ValueError, IndexError):
                continue
    return None


def _estimate_gender(name: str) -> str | None:
    """Estimate gender from first name."""
    if not name:
        return None

    first_name = name.split()[0].lower() if name else ""

    if first_name in MALE_NAMES:
        return "male"
    if first_name in FEMALE_NAMES:
        return "female"

    # Heuristic for Italian names
    if first_name.endswith("a") and not first_name.endswith("ia"):
        return "female"
    if first_name.endswith("o") or first_name.endswith("i"):
        return "male"

    return None


class ProfileClassifier:
    """
    Classifier for LinkedIn profiles.

    Analyzes professional background, seniority, and other attributes.
    """

    def classify(self, profile: LinkedInProfile) -> ClassifiedProfile:
        """
        Classify a single profile.

        Args:
            profile: LinkedInProfile to classify

        Returns:
            ClassifiedProfile with background classification
        """
        # "Background" means career origin — where did this person come from before
        # joining the fund? Since everyone in our dataset currently works at a PE/VC
        # fund (company_slug is always set), their current role is a given.
        # Classifying it as PE would make 100% of people look like PE, hiding the
        # interesting signal (did they come from IB? consulting? corporate?).
        # So: when company_slug is set, skip the current fund role from the vote.
        board_titles = {
            "board member", "member of the board", "board of directors",
            "non-executive", "independent director",
            "consigliere", "amministratore", "membro del consiglio",
            "vice chairman", "chairman of the board", "of the board",
        }

        # Words from the fund slug that identify the fund itself in company names.
        # We only skip the current role if it's at the fund — not all current roles.
        # (Some professionals have multiple simultaneous "current" roles: portfolio
        # board seats, advisory roles at other firms, etc.)
        fund_slug_words: set[str] = set()
        if profile.company_slug:
            fund_slug_words = {
                w for w in profile.company_slug.replace("-", " ").split()
                if len(w) > 3 and w not in {"sgra", "sgrl", "sicaf", "group", "holding"}
            }

        # Build the list of experiences that actually inform "background"
        past_exps = []
        for exp in profile.experience:
            title_lower = (exp.title or "").lower()
            company_lower = (exp.company or "").lower()

            # Skip the current role only if it's at the fund itself.
            if exp.is_current and fund_slug_words:
                if any(word in company_lower for word in fund_slug_words):
                    continue

            # Skip board/advisory roles — portfolio company seats, not career background.
            if any(bt in title_lower for bt in board_titles):
                continue
            past_exps.append(exp)

        background_counts: dict[BackgroundType, int] = {}
        for i, exp in enumerate(past_exps):
            # Most recent prior role = highest weight (3), next = 2, older = 1
            weight = 3 if i == 0 else (2 if i == 1 else 1)
            bg = _classify_experience(exp)
            if bg:
                background_counts[bg] = background_counts.get(bg, 0) + weight

        # If no prior experience at all (career began at fund, or only fund listed),
        # classify as PE since that's their entire professional identity.
        if not background_counts and profile.company_slug:
            background_counts[BackgroundType.PRIVATE_EQUITY] = 1

        # If no experience data (e.g. basic/headline-only scrape), infer from headline
        if not background_counts and profile.headline:
            h = profile.headline.lower()
            if any(kw in h for kw in [
                "private equity", "buyout", "lbo", "pe ", " pe,",
                "private assets", "investment professional", "investment manager",
                "deal origination", "deal sourcing", "portfolio company",
                "infrastructure fund", "growth equity",
            ]):
                background_counts[BackgroundType.PRIVATE_EQUITY] = 1
            elif any(kw in h for kw in [
                "venture capital", "vc ", "seed", "early stage", "startup investor",
                "early-stage", "deep tech",
            ]):
                background_counts[BackgroundType.VENTURE_CAPITAL] = 1
            elif any(kw in h for kw in [
                "investment bank", "m&a", "corporate finance", "ecm", "dcm", "capital markets",
                "leveraged finance", "debt capital",
            ]):
                background_counts[BackgroundType.INVESTMENT_BANKING] = 1
            elif any(kw in h for kw in [
                "consultant", "consulting", "advisory", "strategy&", "mckinsey", "bain", "bcg",
                "roland berger", "oliver wyman", "kearney",
            ]):
                background_counts[BackgroundType.CONSULTING] = 1
            elif any(kw in h for kw in [
                "deloitte", "kpmg", "pwc", "ernst", "ey ", "grant thornton", "accenture",
            ]):
                background_counts[BackgroundType.BIG_FOUR] = 1
            elif any(kw in h for kw in [
                "engineer", "developer", "software", "data science", "machine learning",
                "artificial intelligence", "cybersecurity",
            ]):
                background_counts[BackgroundType.TECH] = 1
            elif any(kw in h for kw in [
                "lawyer", "attorney", "legal", "counsel", "avvocato", "notaio",
            ]):
                background_counts[BackgroundType.LEGAL] = 1

        # Determine primary and secondary backgrounds
        sorted_backgrounds = sorted(
            background_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # When OTHER wins the vote, prefer the next-highest specific category —
        # any specific classification is better than "unknown".
        specific = [(bg, cnt) for bg, cnt in sorted_backgrounds if bg != BackgroundType.OTHER]
        primary = specific[0][0] if specific else BackgroundType.OTHER
        secondary = [bg for bg, _ in specific[1:3]]

        # Get current seniority
        current_title = profile.headline or ""
        for exp in profile.experience:
            if exp.is_current:
                current_title = exp.title or current_title
                break

        seniority = _get_seniority(current_title)

        return ClassifiedProfile(
            profile=profile,
            primary_background=primary,
            secondary_backgrounds=secondary,
            current_seniority=seniority,
            years_experience=_calculate_years_experience(profile.experience),
            tenure_at_current=_calculate_tenure(profile.experience),
            education_tier=_classify_education(profile.education),
            estimated_gender=_estimate_gender(profile.name),
            classification_details={
                "background_counts": {k.value: v for k, v in background_counts.items()},
                "current_title": current_title,
            },
        )

    def classify_batch(self, profiles: list[LinkedInProfile]) -> list[ClassifiedProfile]:
        """Classify multiple profiles."""
        return [self.classify(p) for p in profiles]

    def get_background_summary(
        self,
        classified_profiles: list[ClassifiedProfile],
    ) -> dict[str, Any]:
        """
        Generate summary statistics for a group of profiles.

        Args:
            classified_profiles: List of classified profiles

        Returns:
            Dict with background statistics
        """
        if not classified_profiles:
            return {}

        # Count backgrounds
        background_counts = {bt: 0 for bt in BackgroundType}
        seniority_counts = {sl: 0 for sl in SeniorityLevel}
        education_counts = {"top_mba": 0, "top_undergrad": 0, "other": 0}
        gender_counts = {"male": 0, "female": 0, "unknown": 0}

        total_experience = []
        total_tenure = []

        for cp in classified_profiles:
            background_counts[cp.primary_background] += 1

            for sec in cp.secondary_backgrounds:
                background_counts[sec] += 0.5  # Weight secondary less

            seniority_counts[cp.current_seniority] += 1

            if cp.education_tier:
                education_counts[cp.education_tier] = education_counts.get(cp.education_tier, 0) + 1

            if cp.estimated_gender:
                gender_counts[cp.estimated_gender] += 1
            else:
                gender_counts["unknown"] += 1

            if cp.years_experience:
                total_experience.append(cp.years_experience)
            if cp.tenure_at_current:
                total_tenure.append(cp.tenure_at_current)

        total = len(classified_profiles)
        return {
            "total_profiles": total,
            "backgrounds": {
                k.value: round(v, 1) for k, v in background_counts.items() if v > 0
            },
            "seniority": {
                k.value: v for k, v in seniority_counts.items() if v > 0
            },
            "education": education_counts,
            "gender_breakdown": {
                "male_pct": round(gender_counts["male"] / total * 100, 1) if total else 0,
                "female_pct": round(gender_counts["female"] / total * 100, 1) if total else 0,
                "unknown_pct": round(gender_counts["unknown"] / total * 100, 1) if total else 0,
            },
            "experience": {
                "avg_years": round(sum(total_experience) / len(total_experience), 1) if total_experience else None,
                "min_years": min(total_experience) if total_experience else None,
                "max_years": max(total_experience) if total_experience else None,
            },
            "tenure": {
                "avg_years": round(sum(total_tenure) / len(total_tenure), 1) if total_tenure else None,
            },
        }
