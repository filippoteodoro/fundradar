"""
Portfolio diff detection for Fundradar.

Detects added/removed/changed companies between portfolio extractions.
"""

from dataclasses import dataclass, field
from typing import Literal

from .enrichment import PortfolioCompany
from .entity_resolver import normalize_company_name, similarity_score
from .url_utils import extract_domain as _extract_domain


@dataclass
class CompanyChange:
    """A change in portfolio company status."""

    company: PortfolioCompany
    change_type: Literal["added", "removed", "status_changed", "updated"]
    old_status: str | None = None
    new_status: str | None = None
    confidence: float = 1.0
    matched_to: PortfolioCompany | None = None  # For fuzzy matches


@dataclass
class PortfolioDiff:
    """Result of comparing two portfolio extractions."""

    added: list[CompanyChange] = field(default_factory=list)
    removed: list[CompanyChange] = field(default_factory=list)
    status_changed: list[CompanyChange] = field(default_factory=list)
    unchanged: list[PortfolioCompany] = field(default_factory=list)
    has_changes: bool = False

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.status_changed)


def _match_company(
    company: PortfolioCompany,
    candidates: list[PortfolioCompany],
    threshold: float = 0.85,
) -> tuple[PortfolioCompany | None, float]:
    """
    Find the best matching company in candidates.

    Returns (matched_company, confidence_score).
    """
    normalized = normalize_company_name(company.name)
    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_normalized = normalize_company_name(candidate.name)

        # Exact normalized match
        if normalized == candidate_normalized:
            return candidate, 1.0

        # Website match
        if company.website and candidate.website:
            company_domain = _extract_domain(company.website)
            candidate_domain = _extract_domain(candidate.website)
            if company_domain and company_domain == candidate_domain:
                return candidate, 0.95

        # Fuzzy name match
        score = similarity_score(normalized, candidate_normalized)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return best_match, best_score

    return None, 0.0



def diff_portfolio(
    old: list[PortfolioCompany],
    new: list[PortfolioCompany],
    fuzzy_threshold: float = 0.85,
) -> PortfolioDiff:
    """
    Compare two portfolio extractions and detect changes.

    Args:
        old: Previous portfolio extraction
        new: Current portfolio extraction
        fuzzy_threshold: Minimum similarity for fuzzy matching

    Returns:
        PortfolioDiff with categorized changes
    """
    result = PortfolioDiff()

    # Track which old companies have been matched
    matched_old = set()
    old_by_normalized = {normalize_company_name(c.name): c for c in old}

    # Process new companies
    for new_company in new:
        match, score = _match_company(new_company, old, fuzzy_threshold)

        if match:
            matched_old.add(id(match))

            # Check for status change
            old_status = match.status or "current"
            new_status = new_company.status or "current"

            if old_status != new_status:
                result.status_changed.append(CompanyChange(
                    company=new_company,
                    change_type="status_changed",
                    old_status=old_status,
                    new_status=new_status,
                    confidence=score,
                    matched_to=match,
                ))
            else:
                result.unchanged.append(new_company)
        else:
            # New company added
            result.added.append(CompanyChange(
                company=new_company,
                change_type="added",
                new_status=new_company.status or "current",
                confidence=1.0,
            ))

    # Find removed companies (in old but not matched)
    for old_company in old:
        if id(old_company) not in matched_old:
            result.removed.append(CompanyChange(
                company=old_company,
                change_type="removed",
                old_status=old_company.status or "current",
                confidence=1.0,
            ))

    result.has_changes = result.total_changes > 0
    return result


def generate_change_signals(
    fund_slug: str,
    diff: PortfolioDiff,
) -> list[dict]:
    """
    Generate signal records from portfolio diff.

    Args:
        fund_slug: The fund identifier
        diff: Portfolio diff result

    Returns:
        List of signal dictionaries
    """
    from datetime import datetime, timezone

    signals = []
    now = datetime.now(timezone.utc).isoformat()

    # Signals for added companies
    for change in diff.added:
        signals.append({
            "fund_slug": fund_slug,
            "signal_type": "deal_announced",
            "title": f"New portfolio company: {change.company.name}",
            "what_changed": f"Added to portfolio: {change.company.name}",
            "company_name": change.company.name,
            "company_sector": change.company.sector,
            "company_website": change.company.website,
            "source_url": change.company.source_url,
            "observed_at": now,
            "confidence": change.confidence,
        })

    # Signals for removed companies (potential exits)
    for change in diff.removed:
        signals.append({
            "fund_slug": fund_slug,
            "signal_type": "exit_announced",
            "title": f"Portfolio exit: {change.company.name}",
            "what_changed": f"Removed from portfolio: {change.company.name}",
            "company_name": change.company.name,
            "company_sector": change.company.sector,
            "source_url": change.company.source_url,
            "observed_at": now,
            "confidence": change.confidence,
        })

    # Signals for status changes
    for change in diff.status_changed:
        if change.new_status == "exited":
            signal_type = "exit_announced"
            title = f"Portfolio exit: {change.company.name}"
        else:
            signal_type = "portfolio_update"
            title = f"Status change: {change.company.name}"

        signals.append({
            "fund_slug": fund_slug,
            "signal_type": signal_type,
            "title": title,
            "what_changed": f"Status: {change.old_status} -> {change.new_status}",
            "company_name": change.company.name,
            "source_url": change.company.source_url,
            "observed_at": now,
            "confidence": change.confidence,
        })

    return signals
