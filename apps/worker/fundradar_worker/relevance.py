"""
Italy relevance scoring for signals.

Filters and scores content based on Italy-specific indicators to ensure
signals are relevant to the Italian PE/VC market.
"""

import re
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ExtractedEntities:
    """Entities extracted from text during relevance scoring."""
    companies: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)


@dataclass
class RelevanceResult:
    """Result of Italy relevance scoring."""
    relevance_score: float  # 0.0 to 1.0
    relevance_reasons: list[str]
    italy_relevant: bool
    extracted_entities: ExtractedEntities
    threshold_used: float


PageCategory = Literal["NEWS", "TEAM", "PORTFOLIO", "CAREERS", "ABOUT", "HOME", "OTHER"]


class ItalyRelevanceScorer:
    """
    Scores content for Italy relevance.

    Uses pattern matching to identify Italian cities, regions, legal entity
    suffixes, and other indicators of Italy-relevant content.
    """

    # Default threshold for italy_relevant flag
    DEFAULT_THRESHOLD = 0.35

    # Lower threshold for news (headlines often lack explicit location)
    NEWS_THRESHOLD = 0.25

    # Italian cities (major + notable)
    ITALIAN_CITIES = [
        # Major cities
        "Milano", "Milan", "Roma", "Rome", "Torino", "Turin",
        "Napoli", "Naples", "Bologna", "Firenze", "Florence",
        "Genova", "Genoa", "Venezia", "Venice", "Palermo",
        # Notable business centers
        "Padova", "Padua", "Verona", "Trieste", "Bari", "Catania",
        "Bergamo", "Brescia", "Modena", "Parma", "Reggio Emilia",
        "Monza", "Vicenza", "Treviso", "Udine", "Ancona",
        "Pescara", "Lecce", "Salerno", "Taranto", "Perugia",
        "Cagliari", "Sassari", "Bolzano", "Trento",
    ]

    # Italian regions
    ITALIAN_REGIONS = [
        "Lombardia", "Lombardy", "Veneto", "Emilia-Romagna", "Emilia Romagna",
        "Piemonte", "Piedmont", "Toscana", "Tuscany", "Lazio",
        "Campania", "Puglia", "Sicilia", "Sicily", "Sardegna", "Sardinia",
        "Liguria", "Marche", "Friuli-Venezia Giulia", "Friuli Venezia Giulia",
        "Abruzzo", "Calabria", "Umbria", "Basilicata", "Molise",
        "Trentino-Alto Adige", "Trentino Alto Adige", "Valle d'Aosta",
    ]

    # Italian legal entity suffixes
    ITALIAN_LEGAL_SUFFIXES = [
        r"S\.?p\.?A\.?",  # S.p.A. / SpA / SPA
        r"S\.?r\.?l\.?",  # S.r.l. / Srl / SRL
        r"S\.?a\.?s\.?",  # S.a.s. / Sas / SAS
        r"S\.?n\.?c\.?",  # S.n.c. / Snc / SNC
        r"S\.?c\.?a\.?r\.?l\.?",  # S.c.a.r.l.
        r"SGR",  # Societa di Gestione del Risparmio
    ]

    # Italy direct mentions
    ITALY_MENTIONS = [
        "Italy", "Italia", "Italian", "Italiano", "Italiana",
    ]

    # Italian financial/business terms
    ITALIAN_BUSINESS_TERMS = [
        "Borsa Italiana", "Piazza Affari", "CONSOB", "Banca d'Italia",
        "Cassa Depositi", "CDP", "AIFI", "Assonime", "Confindustria",
        "made in Italy", "Italian market", "mercato italiano",
    ]

    # Weight factors for different indicator types
    WEIGHTS = {
        "italy_direct": 0.4,       # Direct mention of Italy/Italia/Italian
        "city": 0.25,              # Italian city mentioned
        "region": 0.2,             # Italian region mentioned
        "legal_suffix": 0.3,       # Italian legal entity suffix
        "business_term": 0.25,     # Italian business/financial term
    }

    def __init__(self, default_threshold: float = DEFAULT_THRESHOLD):
        self.default_threshold = default_threshold
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency."""
        # Cities pattern
        cities_pattern = r"(?i)\b(" + "|".join(re.escape(c) for c in self.ITALIAN_CITIES) + r")\b"
        self._cities_re = re.compile(cities_pattern)

        # Regions pattern
        regions_pattern = r"(?i)\b(" + "|".join(re.escape(r) for r in self.ITALIAN_REGIONS) + r")\b"
        self._regions_re = re.compile(regions_pattern)

        # Legal suffixes pattern (case insensitive)
        legal_pattern = r"(?i)\b(" + "|".join(self.ITALIAN_LEGAL_SUFFIXES) + r")\b"
        self._legal_re = re.compile(legal_pattern)

        # Italy direct mentions
        italy_pattern = r"(?i)\b(" + "|".join(re.escape(m) for m in self.ITALY_MENTIONS) + r")\b"
        self._italy_re = re.compile(italy_pattern)

        # Business terms
        business_pattern = r"(?i)(" + "|".join(re.escape(t) for t in self.ITALIAN_BUSINESS_TERMS) + r")"
        self._business_re = re.compile(business_pattern)

        # Entity extraction patterns
        # Simple company name pattern (capitalized words followed by legal suffix)
        self._company_re = re.compile(
            r"([A-Z][a-zA-Z&\-\']+(?:\s+[A-Z][a-zA-Z&\-\']+)*)\s*(?:S\.?p\.?A\.?|S\.?r\.?l\.?|S\.?a\.?s\.?)",
            re.IGNORECASE
        )

        # Person name pattern (Title + Name or two capitalized words)
        self._person_re = re.compile(
            r"\b((?:Dr\.?|Mr\.?|Ms\.?|Mrs\.?|Prof\.?)?\s*[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
        )

    def score(
        self,
        text: str,
        page_category: PageCategory = "OTHER",
        fund_has_italy_presence: bool | None = None,
    ) -> RelevanceResult:
        """
        Score content for Italy relevance.

        Args:
            text: The text content to analyze
            page_category: The type of page (affects threshold)
            fund_has_italy_presence: If known, whether the fund has Italy presence

        Returns:
            RelevanceResult with score, reasons, and extracted entities
        """
        if not text:
            return RelevanceResult(
                relevance_score=0.0,
                relevance_reasons=[],
                italy_relevant=False,
                extracted_entities=ExtractedEntities(),
                threshold_used=self.default_threshold,
            )

        reasons = []
        score = 0.0
        entities = ExtractedEntities()

        # Direct Italy mentions (highest weight)
        italy_matches = self._italy_re.findall(text)
        if italy_matches:
            unique_matches = list(set(m.lower() for m in italy_matches))
            count = len(italy_matches)
            # Cap contribution from multiple mentions
            contribution = min(self.WEIGHTS["italy_direct"] * (1 + 0.1 * (count - 1)), 0.6)
            score += contribution
            reasons.append(f"Italy mentioned ({', '.join(unique_matches[:3])})")

        # Italian cities
        city_matches = self._cities_re.findall(text)
        if city_matches:
            unique_cities = list(set(m.title() for m in city_matches))
            entities.locations.extend(unique_cities)
            count = len(city_matches)
            contribution = min(self.WEIGHTS["city"] * (1 + 0.1 * (count - 1)), 0.4)
            score += contribution
            reasons.append(f"Italian cities: {', '.join(unique_cities[:5])}")

        # Italian regions
        region_matches = self._regions_re.findall(text)
        if region_matches:
            unique_regions = list(set(m.title() for m in region_matches))
            entities.locations.extend(unique_regions)
            contribution = min(self.WEIGHTS["region"] * (1 + 0.05 * (len(region_matches) - 1)), 0.3)
            score += contribution
            reasons.append(f"Italian regions: {', '.join(unique_regions[:3])}")

        # Italian legal suffixes (strong indicator)
        legal_matches = self._legal_re.findall(text)
        if legal_matches:
            unique_legal = list(set(m.upper().replace(".", "") for m in legal_matches))
            count = len(legal_matches)
            contribution = min(self.WEIGHTS["legal_suffix"] * (1 + 0.15 * (count - 1)), 0.5)
            score += contribution
            reasons.append(f"Italian entity types: {', '.join(unique_legal[:3])}")

        # Italian business terms
        business_matches = self._business_re.findall(text)
        if business_matches:
            unique_terms = list(set(business_matches))
            contribution = min(self.WEIGHTS["business_term"] * len(unique_terms), 0.3)
            score += contribution
            reasons.append(f"Italian business context: {', '.join(unique_terms[:3])}")

        # Extract entities for enrichment
        companies = self._company_re.findall(text)
        if companies:
            entities.companies = list(set(c.strip() for c in companies if len(c) > 2))[:20]

        people = self._person_re.findall(text)
        if people:
            entities.people = list(set(p.strip() for p in people if len(p.split()) >= 2))[:20]

        # Bonus if fund already known to have Italy presence
        if fund_has_italy_presence:
            score += 0.15
            reasons.append("Fund has known Italy presence")

        # Cap score at 1.0
        score = min(score, 1.0)

        # Determine threshold based on page category
        threshold = self._get_threshold(page_category)

        return RelevanceResult(
            relevance_score=round(score, 3),
            relevance_reasons=reasons,
            italy_relevant=score >= threshold,
            extracted_entities=entities,
            threshold_used=threshold,
        )

    def _get_threshold(self, page_category: PageCategory) -> float:
        """Get the relevance threshold for a page category."""
        if page_category == "NEWS":
            return self.NEWS_THRESHOLD
        elif page_category in ("TEAM", "CAREERS"):
            # People moves might not mention Italy explicitly
            return 0.3
        elif page_category == "PORTFOLIO":
            # Portfolio companies should have Italy connection
            return 0.35
        return self.default_threshold

    def batch_score(
        self,
        items: list[tuple[str, PageCategory]],
        fund_has_italy_presence: bool | None = None,
    ) -> list[RelevanceResult]:
        """
        Score multiple items for efficiency.

        Args:
            items: List of (text, page_category) tuples
            fund_has_italy_presence: If known, whether the fund has Italy presence

        Returns:
            List of RelevanceResult in same order as input
        """
        return [
            self.score(text, category, fund_has_italy_presence)
            for text, category in items
        ]


def score_italy_relevance(
    text: str,
    page_category: PageCategory = "OTHER",
) -> RelevanceResult:
    """
    Convenience function to score Italy relevance.

    Args:
        text: The text content to analyze
        page_category: The type of page

    Returns:
        RelevanceResult with score and reasons
    """
    scorer = ItalyRelevanceScorer()
    return scorer.score(text, page_category)
