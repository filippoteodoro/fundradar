"""
Canonical fund slug normalization for Fundradar.

Ensures every fund resolves to a single canonical slug sourced from:
- data/db.json

Legacy or invalid slugs are handled via:
- data/derived/fund_aliases.json
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ALIASES_PATH = PROJECT_ROOT / "data" / "derived" / "fund_aliases.json"


def _normalize_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _normalize_domain(value: str | None) -> str:
    domain = (value or "").lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def _domain_from_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        return _normalize_domain(domain)
    except Exception:
        return ""


@dataclass(frozen=True)
class SlugNormalizationResult:
    slug: str | None
    reason: str


@dataclass
class FundSlugNormalizer:
    canonical_slugs: set[str]
    invalid_slugs: set[str]
    alias_map: dict[str, str]
    domain_aliases: dict[str, str]
    funds_by_slug: dict[str, dict]
    id_to_slug: dict[str, str]
    name_to_slug: dict[str, str]
    domain_to_slug: dict[str, str]

    @classmethod
    def load(cls, project_root: Path | None = None) -> "FundSlugNormalizer":
        root = project_root or PROJECT_ROOT
        db_path = root / "data" / "db.json"
        aliases_path = root / "data" / "derived" / "fund_aliases.json"

        funds: list[dict] = []
        if db_path.exists():
            with open(db_path) as f:
                db = json.load(f)
            funds.extend(db.get("funds", []))

        canonical_slugs = {f.get("slug") for f in funds if f.get("slug")}
        funds_by_slug: dict[str, dict] = {}
        for fund in funds:
            slug = fund.get("slug")
            if not slug or slug in funds_by_slug:
                continue
            funds_by_slug[slug] = fund

        alias_map: dict[str, str] = {}
        invalid_slugs: set[str] = set()
        domain_aliases: dict[str, str] = {}
        if aliases_path.exists():
            try:
                with open(aliases_path) as f:
                    aliases_data = json.load(f)
                invalid_slugs = {str(s).strip() for s in (aliases_data.get("invalid_slugs") or []) if s}
                raw_aliases = aliases_data.get("aliases") or {}
                for alias, canonical in raw_aliases.items():
                    if alias and canonical and canonical in canonical_slugs:
                        alias_map[str(alias).strip()] = str(canonical).strip()
                raw_domain_aliases = aliases_data.get("domain_aliases") or {}
                for alias_domain, canonical_domain in raw_domain_aliases.items():
                    if alias_domain and canonical_domain:
                        domain_aliases[_normalize_domain(alias_domain)] = _normalize_domain(canonical_domain)
            except Exception:
                pass

        id_to_slug: dict[str, str] = {}
        name_to_slug: dict[str, str] = {}
        domain_to_slug: dict[str, str] = {}

        for slug, fund in funds_by_slug.items():
            fund_id = str(fund.get("id") or "").strip()
            if fund_id:
                id_to_slug[fund_id] = slug
            name = fund.get("name") or ""
            if name:
                name_to_slug[_normalize_text(name)] = slug
            website = (fund.get("website") or "").strip()
            if website:
                domain = _domain_from_url(website)
                if domain:
                    domain_to_slug[domain] = slug

        # Apply domain aliases to domain_to_slug lookups
        for alias_domain, canonical_domain in domain_aliases.items():
            canonical_slug = domain_to_slug.get(canonical_domain)
            if canonical_slug:
                domain_to_slug[alias_domain] = canonical_slug

        return cls(
            canonical_slugs=canonical_slugs,
            invalid_slugs=invalid_slugs,
            alias_map=alias_map,
            domain_aliases=domain_aliases,
            funds_by_slug=funds_by_slug,
            id_to_slug=id_to_slug,
            name_to_slug=name_to_slug,
            domain_to_slug=domain_to_slug,
        )

    def normalize(
        self,
        slug: str | None = None,
        *,
        fund_id: str | None = None,
        name: str | None = None,
        source_url: str | None = None,
        source_domain: str | None = None,
    ) -> SlugNormalizationResult:
        candidate = (slug or "").strip()

        if candidate and candidate in self.invalid_slugs:
            return SlugNormalizationResult(None, "invalid")

        if candidate and candidate in self.alias_map:
            canonical = self.alias_map[candidate]
            return SlugNormalizationResult(canonical, "alias")

        if candidate and candidate in self.canonical_slugs:
            return SlugNormalizationResult(candidate, "canonical")

        if fund_id:
            fund_id = str(fund_id).strip()
            if fund_id in self.id_to_slug:
                return SlugNormalizationResult(self.id_to_slug[fund_id], "id")

        if name:
            normalized_name = _normalize_text(name)
            if normalized_name in self.name_to_slug:
                return SlugNormalizationResult(self.name_to_slug[normalized_name], "name")

        domain = _normalize_domain(source_domain) if source_domain else _domain_from_url(source_url)
        if domain:
            domain = self.domain_aliases.get(domain, domain)
            if domain in self.domain_to_slug:
                return SlugNormalizationResult(self.domain_to_slug[domain], "domain")

        return SlugNormalizationResult(None, "unknown")


_NORMALIZER: FundSlugNormalizer | None = None


def get_slug_normalizer() -> FundSlugNormalizer:
    global _NORMALIZER
    if _NORMALIZER is None:
        _NORMALIZER = FundSlugNormalizer.load()
    return _NORMALIZER
