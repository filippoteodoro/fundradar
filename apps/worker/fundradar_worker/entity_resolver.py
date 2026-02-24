"""
Entity resolver for Fundradar portfolio companies.

Handles fuzzy matching and resolution of company names to canonical entities.
"""

import re
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


# Legal suffixes to normalize — single source of truth for company name matching.
# Used by entity_resolver AND signal_to_portfolio (via import).
LEGAL_SUFFIXES = [
    r"\bS\.?p\.?A\.?",
    r"\bS\.?r\.?l\.?",
    r"\bS\.?a\.?s\.?",
    r"\bS\.?n\.?c\.?",
    r"\bS\.?A\.?S\.?",
    r"\bLtd\.?",
    r"\bLLC\.?",
    r"\bInc\.?",
    r"\bGmbH\.?",
    r"\bAG\.?",
    r"\bB\.?V\.?",
    r"\bN\.?V\.?",
    r"\bPLC\.?",
    r"\bCorp\.?",
    r"\bCorporation",
    r"\bCompany",
    r"\bGroup",
    r"\bGruppo",
    r"\bHolding",
    r"\bHoldings",
    r"\bPartecipazioni",
]

# Pattern for matching
SUFFIX_PATTERN = re.compile(
    r"(?:\s+|,\s*)(?:" + "|".join(LEGAL_SUFFIXES) + r")\s*$",
    re.IGNORECASE,
)


@dataclass
class CompanyEntity:
    """Canonical company entity."""

    id: str
    name: str
    normalized_name: str
    website: str | None = None
    sector: str | None = None
    country: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class CompanyMatch:
    """Result of company name resolution."""

    entity: CompanyEntity | None
    match_type: Literal["exact", "alias", "fuzzy", "website", "new"]
    confidence: float
    matched_name: str | None = None
    is_new: bool = False


def normalize_company_name(name: str) -> str:
    """
    Normalize a company name for matching.

    IMPORTANT: This function must stay aligned with normalizeCompanyName()
    in apps/web/src/lib/data.ts — both are used for PEM↔website portfolio
    matching. If they diverge, duplicate entries appear on fund pages.

    This is the SINGLE source of truth for company name normalization across
    the pipeline. signal_to_portfolio.py imports this — do NOT create local copies.

    Steps: lowercase → strip parenthetical → strip "logo" → strip legal
    suffixes (multi-pass) → strip "Technologies" → non-alphanumeric
    to space → collapse spaces.
    """
    if not name:
        return ""

    # Lowercase
    normalized = name.lower().strip()

    # Strip parenthetical content: "(via X)", "(fka Y)", etc.
    normalized = re.sub(r"\s*\(.*\)", "", normalized)

    # Strip trailing "logo" from image alt text
    normalized = re.sub(r"\s*logo\s*$", "", normalized, flags=re.IGNORECASE)

    # Remove legal suffixes (multi-pass: handles "Company Holdings S.r.l.")
    for _ in range(3):
        cleaned = SUFFIX_PATTERN.sub("", normalized).strip()
        if cleaned == normalized:
            break
        normalized = cleaned

    # Strip trailing "Technologies"
    normalized = re.sub(r"\s+technologies\s*$", "", normalized, flags=re.IGNORECASE)

    # Non-alphanumeric → space (handles hyphens: "SF-Filter" → "sf filter")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    return normalized


def similarity_score(a: str, b: str) -> float:
    """
    Calculate similarity between two strings.

    Uses a combination of:
    - Exact substring match
    - Character-level similarity (Jaccard)
    - Word-level similarity
    """
    if not a or not b:
        return 0.0

    a = a.lower()
    b = b.lower()

    # Exact match
    if a == b:
        return 1.0

    # One contains the other
    if a in b or b in a:
        shorter = min(len(a), len(b))
        longer = max(len(a), len(b))
        return shorter / longer * 0.95

    # Character-level Jaccard
    chars_a = set(a)
    chars_b = set(b)
    char_intersection = len(chars_a & chars_b)
    char_union = len(chars_a | chars_b)
    char_sim = char_intersection / char_union if char_union > 0 else 0

    # Word-level Jaccard
    words_a = set(a.split())
    words_b = set(b.split())
    word_intersection = len(words_a & words_b)
    word_union = len(words_a | words_b)
    word_sim = word_intersection / word_union if word_union > 0 else 0

    # Weighted combination
    return 0.4 * char_sim + 0.6 * word_sim


class EntityResolver:
    """
    Resolves company names to canonical entities.

    Supports fuzzy matching, alias lookup, and creating new entities.
    """

    def __init__(self, store_path: Path | None = None):
        self.store_path = store_path
        self.entities: dict[str, CompanyEntity] = {}
        self._name_index: dict[str, str] = {}  # normalized_name -> entity_id
        self._website_index: dict[str, str] = {}  # domain -> entity_id
        self._alias_index: dict[str, str] = {}  # alias -> entity_id
        self._next_id = 1
        self._lock = threading.RLock()

        if store_path and store_path.exists():
            self._load()

    def _load(self):
        """Load entities from disk."""
        with open(self.store_path) as f:
            data = json.load(f)

        for entity_data in data.get("entities", []):
            entity = CompanyEntity(
                id=entity_data["id"],
                name=entity_data["name"],
                normalized_name=entity_data["normalized_name"],
                website=entity_data.get("website"),
                sector=entity_data.get("sector"),
                country=entity_data.get("country"),
                aliases=entity_data.get("aliases", []),
            )
            self._add_to_indices(entity)

        self._next_id = data.get("next_id", len(self.entities) + 1)

    def _save(self):
        """Save entities to disk."""
        if not self.store_path:
            return
        with self._lock:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)

            entities_data = []
            for entity in self.entities.values():
                entities_data.append({
                    "id": entity.id,
                    "name": entity.name,
                    "normalized_name": entity.normalized_name,
                    "website": entity.website,
                    "sector": entity.sector,
                    "country": entity.country,
                    "aliases": entity.aliases,
                })

            with open(self.store_path, "w") as f:
                json.dump({
                    "entities": entities_data,
                    "next_id": self._next_id,
                }, f, indent=2)

    def _add_to_indices(self, entity: CompanyEntity):
        """Add entity to lookup indices."""
        with self._lock:
            self.entities[entity.id] = entity
            self._name_index[entity.normalized_name] = entity.id

            if entity.website:
                domain = self._extract_domain(entity.website)
                if domain:
                    self._website_index[domain] = entity.id

            for alias in entity.aliases:
                normalized_alias = normalize_company_name(alias)
                self._alias_index[normalized_alias] = entity.id

    def _extract_domain(self, url: str) -> str | None:
        """Extract domain from URL for matching."""
        if not url:
            return None

        url = url.lower()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return None

    def _generate_id(self) -> str:
        """Generate a unique entity ID."""
        entity_id = f"company-{self._next_id:05d}"
        self._next_id += 1
        return entity_id

    def resolve(
        self,
        name: str,
        website: str | None = None,
        sector: str | None = None,
        country: str | None = None,
        fuzzy_threshold: float = 0.90,
        create_if_new: bool = True,
    ) -> CompanyMatch:
        """
        Resolve a company name to a canonical entity.

        Args:
            name: The company name to resolve
            website: Optional company website for matching
            sector: Optional sector (used when creating new entity)
            country: Optional country (used when creating new entity)
            fuzzy_threshold: Minimum similarity for fuzzy match
            create_if_new: Whether to create a new entity if no match

        Returns:
            CompanyMatch with resolution result
        """
        normalized = normalize_company_name(name)

        with self._lock:
            # 1. Exact normalized name match
            if normalized in self._name_index:
                entity_id = self._name_index[normalized]
                return CompanyMatch(
                    entity=self.entities[entity_id],
                    match_type="exact",
                    confidence=1.0,
                    matched_name=normalized,
                )

            # 2. Alias match
            if normalized in self._alias_index:
                entity_id = self._alias_index[normalized]
                return CompanyMatch(
                    entity=self.entities[entity_id],
                    match_type="alias",
                    confidence=0.95,
                    matched_name=normalized,
                )

            # 3. Website domain match
            if website:
                domain = self._extract_domain(website)
                if domain and domain in self._website_index:
                    entity_id = self._website_index[domain]
                    return CompanyMatch(
                        entity=self.entities[entity_id],
                        match_type="website",
                        confidence=0.90,
                        matched_name=domain,
                    )

            # 4. Fuzzy name match
            best_match = None
            best_score = 0.0

            for entity_normalized, entity_id in self._name_index.items():
                score = similarity_score(normalized, entity_normalized)
                if score > best_score:
                    best_score = score
                    best_match = entity_id

            if best_match and best_score >= fuzzy_threshold:
                return CompanyMatch(
                    entity=self.entities[best_match],
                    match_type="fuzzy",
                    confidence=best_score,
                    matched_name=self.entities[best_match].normalized_name,
                )

            # 5. No match - create new if requested
            if create_if_new:
                entity = CompanyEntity(
                    id=self._generate_id(),
                    name=name,
                    normalized_name=normalized,
                    website=website,
                    sector=sector,
                    country=country,
                )
                self._add_to_indices(entity)
                self._save()

                return CompanyMatch(
                    entity=entity,
                    match_type="new",
                    confidence=1.0,
                    is_new=True,
                )

        return CompanyMatch(
            entity=None,
            match_type="new",
            confidence=0.0,
            is_new=True,
        )

    def add_alias(self, entity_id: str, alias: str):
        """Add an alias for an entity."""
        if entity_id not in self.entities:
            return

        entity = self.entities[entity_id]
        normalized_alias = normalize_company_name(alias)

        if normalized_alias not in entity.aliases:
            entity.aliases.append(alias)
            self._alias_index[normalized_alias] = entity_id
            self._save()

    def update_entity(
        self,
        entity_id: str,
        website: str | None = None,
        sector: str | None = None,
        country: str | None = None,
    ):
        """Update entity fields."""
        if entity_id not in self.entities:
            return

        entity = self.entities[entity_id]

        if website and not entity.website:
            entity.website = website
            domain = self._extract_domain(website)
            if domain:
                self._website_index[domain] = entity_id

        if sector and not entity.sector:
            entity.sector = sector

        if country and not entity.country:
            entity.country = country

        self._save()

    def get_stats(self) -> dict:
        """Get resolver statistics."""
        return {
            "total_entities": len(self.entities),
            "total_aliases": len(self._alias_index),
            "entities_with_website": sum(1 for e in self.entities.values() if e.website),
        }


# Module-level resolver
_resolver: EntityResolver | None = None


def get_entity_resolver() -> EntityResolver:
    """Get the global entity resolver."""
    global _resolver

    if _resolver is None:
        default_path = Path(__file__).parent.parent.parent.parent / "data" / "derived" / "portfolio_companies.json"
        _resolver = EntityResolver(default_path)

    return _resolver


def resolve_company(
    name: str,
    website: str | None = None,
    sector: str | None = None,
) -> CompanyMatch:
    """Convenience function to resolve a company name."""
    resolver = get_entity_resolver()
    return resolver.resolve(name, website, sector)
