"""
Post classifier for detecting signals from LinkedIn posts.

Analyzes post content to identify deal announcements, exits,
fundraises, and people moves.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .posts_scraper import LinkedInPost

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    """Types of signals detected from LinkedIn posts."""

    DEAL_ANNOUNCED = "deal_announced"
    EXIT_ANNOUNCED = "exit_announced"
    FUNDRAISE_ANNOUNCED = "fundraise_announced"
    PEOPLE_MOVE = "people_move"
    PORTFOLIO_NEWS = "portfolio_news"
    FUND_NEWS = "fund_news"
    JOB_POSTING = "job_posting"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedPost:
    """A post with signal classification."""

    post: LinkedInPost
    signal_type: SignalType
    confidence: float  # 0.0 to 1.0
    extracted_entities: dict[str, Any] = field(default_factory=dict)
    classification_reason: str = ""


# Pattern definitions for signal detection
DEAL_PATTERNS = [
    r"pleased to announce.*investment",
    r"proud to announce.*investment",
    r"excited to announce.*partner",
    r"we['']ve invested in",
    r"we have invested in",
    r"announcing our investment",
    r"new investment in",
    r"portfolio company",
    r"strategic investment",
    r"acquired a (?:majority |minority )?stake",
    r"backing (?:the )?team",
    r"supporting (?:the )?growth",
]

EXIT_PATTERNS = [
    r"congratulations.*(?:ipo|acquisition|sale|exit)",
    r"successfully exited",
    r"successful exit",
    r"completed (?:the )?sale",
    r"sale of (?:our )?portfolio",
    r"acquired by",
    r"(?:ipo|listing) on",
    r"gone public",
    r"exited our investment",
    r"portfolio company.*acquired",
]

FUNDRAISE_PATTERNS = [
    r"closed (?:fund|our)",
    r"raised €?\$?\d+",
    r"final close",
    r"first close",
    r"fund \w+ (?:at|with) €?\$?\d+",
    r"(?:fund|capital|commitment).*(?:billion|million|mln|bn|m)",
    r"new fund",
    r"successor fund",
    r"fundraising",
]

PEOPLE_MOVE_PATTERNS = [
    r"welcome[sd]? (?:aboard |to )?(?:our team |our firm )?(?:\w+ ){1,3}(?:as|to)",
    r"pleased to welcome",
    r"joining (?:us|our team|the firm)",
    r"new (?:partner|managing director|principal|director|associate)",
    r"promoted to",
    r"appointed as",
    r"(?:announces|announcing) (?:the )?(?:appointment|hire|promotion)",
    r"strengthening our team",
]

JOB_POSTING_PATTERNS = [
    r"we['']re hiring",
    r"we are hiring",
    r"job opening",
    r"join our team",
    r"looking for",
    r"open position",
    r"career opportunit",
    r"apply now",
    r"#hiring",
]

PORTFOLIO_NEWS_PATTERNS = [
    r"portfolio company.*announce",
    r"portfolio company.*launch",
    r"portfolio company.*expand",
    r"congrat(?:ulation)?s? to (?:\w+ ){1,3}(?:for|on)",
    r"proud of (?:our )?portfolio",
    r"great news from",
]

# Entity extraction patterns
COMPANY_NAME_PATTERN = r"(?:invest(?:ed|ment)? in|acquired|backing|partner(?:ed|ing)? with)\s+([A-Z][A-Za-z0-9\s&\-]+?)(?:\s*[,\.]|\s+(?:a|an|the|to|from|in|is|has|will))"
AMOUNT_PATTERN = r"(?:€|\$|EUR |USD )(\d+(?:\.\d+)?)\s*(?:million|mln|m|billion|bn|b)"
FUND_NUMBER_PATTERN = r"(?:Fund|Fondo)\s+([IVXLCDM]+|\d+)"


def _match_patterns(text: str, patterns: list[str]) -> tuple[bool, str | None]:
    """Check if text matches any pattern and return matching pattern."""
    text_lower = text.lower()
    for pattern in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, pattern
    return False, None


def _extract_company_name(text: str) -> str | None:
    """Extract company name from deal announcement."""
    match = re.search(COMPANY_NAME_PATTERN, text, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        # Clean up trailing words that shouldn't be part of name
        name = re.sub(r"\s+(?:a|an|the)$", "", name, flags=re.IGNORECASE)
        return name
    return None


def _extract_amount(text: str) -> dict[str, Any] | None:
    """Extract monetary amount from text."""
    match = re.search(AMOUNT_PATTERN, text, re.IGNORECASE)
    if match:
        amount = float(match.group(1))
        unit = "million"
        if "billion" in match.group(0).lower() or "bn" in match.group(0).lower() or "b" == match.group(0).lower()[-1]:
            unit = "billion"
            amount *= 1000  # Convert to millions for consistency

        currency = "EUR"
        if "$" in match.group(0) or "USD" in match.group(0):
            currency = "USD"

        return {
            "amount_millions": amount,
            "currency": currency,
            "raw": match.group(0),
        }
    return None


def _extract_fund_number(text: str) -> str | None:
    """Extract fund number (e.g., 'Fund IV')."""
    match = re.search(FUND_NUMBER_PATTERN, text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


class PostClassifier:
    """
    Classifier for LinkedIn posts to detect signals.

    Uses pattern matching and keyword analysis to identify
    deal announcements, exits, fundraises, and people moves.
    """

    def __init__(self, min_confidence: float = 0.5):
        """
        Initialize classifier.

        Args:
            min_confidence: Minimum confidence threshold for classification
        """
        self.min_confidence = min_confidence

    def classify(self, post: LinkedInPost) -> ClassifiedPost:
        """
        Classify a single post.

        Args:
            post: LinkedInPost to classify

        Returns:
            ClassifiedPost with signal type and confidence
        """
        text = post.text or ""
        if not text:
            return ClassifiedPost(
                post=post,
                signal_type=SignalType.UNKNOWN,
                confidence=0.0,
                classification_reason="Empty post text",
            )

        # Check patterns in priority order
        classifications = []

        # Deal announcements (highest priority)
        matched, pattern = _match_patterns(text, DEAL_PATTERNS)
        if matched:
            company = _extract_company_name(text)
            amount = _extract_amount(text)
            classifications.append({
                "type": SignalType.DEAL_ANNOUNCED,
                "confidence": 0.9,
                "pattern": pattern,
                "entities": {
                    "company_name": company,
                    "amount": amount,
                },
            })

        # Exit announcements
        matched, pattern = _match_patterns(text, EXIT_PATTERNS)
        if matched:
            company = _extract_company_name(text)
            classifications.append({
                "type": SignalType.EXIT_ANNOUNCED,
                "confidence": 0.85,
                "pattern": pattern,
                "entities": {
                    "company_name": company,
                },
            })

        # Fundraise announcements
        matched, pattern = _match_patterns(text, FUNDRAISE_PATTERNS)
        if matched:
            amount = _extract_amount(text)
            fund_num = _extract_fund_number(text)
            classifications.append({
                "type": SignalType.FUNDRAISE_ANNOUNCED,
                "confidence": 0.85,
                "pattern": pattern,
                "entities": {
                    "amount": amount,
                    "fund_number": fund_num,
                },
            })

        # People moves
        matched, pattern = _match_patterns(text, PEOPLE_MOVE_PATTERNS)
        if matched:
            # Look for names following "welcome" pattern
            name_match = re.search(
                r"welcom(?:e[sd]?|ing)\s+(?:aboard\s+)?(?:our\s+)?(?:new\s+)?(\w+\s+\w+)",
                text, re.IGNORECASE
            )
            name = name_match.group(1) if name_match else None

            classifications.append({
                "type": SignalType.PEOPLE_MOVE,
                "confidence": 0.8,
                "pattern": pattern,
                "entities": {
                    "person_name": name,
                },
            })

        # Job postings (lower priority if it's just a hiring post)
        matched, pattern = _match_patterns(text, JOB_POSTING_PATTERNS)
        if matched:
            classifications.append({
                "type": SignalType.JOB_POSTING,
                "confidence": 0.7,
                "pattern": pattern,
                "entities": {},
            })

        # Portfolio news
        matched, pattern = _match_patterns(text, PORTFOLIO_NEWS_PATTERNS)
        if matched:
            company = _extract_company_name(text)
            classifications.append({
                "type": SignalType.PORTFOLIO_NEWS,
                "confidence": 0.6,
                "pattern": pattern,
                "entities": {
                    "company_name": company,
                },
            })

        # Select best classification
        if classifications:
            # Sort by confidence, take highest
            classifications.sort(key=lambda x: x["confidence"], reverse=True)
            best = classifications[0]

            return ClassifiedPost(
                post=post,
                signal_type=best["type"],
                confidence=best["confidence"],
                extracted_entities={k: v for k, v in best["entities"].items() if v},
                classification_reason=f"Matched pattern: {best['pattern']}",
            )

        # Default to fund news if post has some engagement
        engagement = post.engagement or {}
        total_engagement = sum(engagement.values())
        if total_engagement > 100:
            return ClassifiedPost(
                post=post,
                signal_type=SignalType.FUND_NEWS,
                confidence=0.3,
                classification_reason="High engagement but no specific pattern match",
            )

        return ClassifiedPost(
            post=post,
            signal_type=SignalType.UNKNOWN,
            confidence=0.0,
            classification_reason="No pattern matched",
        )

    def classify_batch(
        self,
        posts: list[LinkedInPost],
        filter_unknown: bool = True,
    ) -> list[ClassifiedPost]:
        """
        Classify multiple posts.

        Args:
            posts: List of posts to classify
            filter_unknown: Whether to filter out unknown classifications

        Returns:
            List of ClassifiedPost objects
        """
        results = []
        for post in posts:
            classified = self.classify(post)

            if filter_unknown and classified.signal_type == SignalType.UNKNOWN:
                continue

            if classified.confidence >= self.min_confidence:
                results.append(classified)

        # Sort by confidence
        results.sort(key=lambda x: x.confidence, reverse=True)
        return results

    def to_signal_records(
        self,
        classified_posts: list[ClassifiedPost],
        source_name: str = "LinkedIn",
    ) -> list[dict[str, Any]]:
        """
        Convert classified posts to SignalRecord-compatible dicts.

        Args:
            classified_posts: List of classified posts
            source_name: Name of the source for signals

        Returns:
            List of dicts compatible with SignalRecord
        """
        signals = []
        now = datetime.now(timezone.utc).isoformat()

        for cp in classified_posts:
            post = cp.post

            # Build title based on signal type
            if cp.signal_type == SignalType.DEAL_ANNOUNCED:
                company = cp.extracted_entities.get("company_name", "new company")
                title = f"Investment announced: {company}"
            elif cp.signal_type == SignalType.EXIT_ANNOUNCED:
                company = cp.extracted_entities.get("company_name", "portfolio company")
                title = f"Exit announced: {company}"
            elif cp.signal_type == SignalType.FUNDRAISE_ANNOUNCED:
                fund = cp.extracted_entities.get("fund_number", "")
                amount = cp.extracted_entities.get("amount", {})
                if amount:
                    title = f"Fund {fund} closed at {amount.get('raw', '')}"
                else:
                    title = f"Fund {fund} closed" if fund else "New fund announced"
            elif cp.signal_type == SignalType.PEOPLE_MOVE:
                person = cp.extracted_entities.get("person_name", "new team member")
                title = f"New hire: {person}"
            elif cp.signal_type == SignalType.JOB_POSTING:
                title = "Job opening posted"
            elif cp.signal_type == SignalType.PORTFOLIO_NEWS:
                company = cp.extracted_entities.get("company_name", "portfolio company")
                title = f"Portfolio news: {company}"
            else:
                title = f"LinkedIn update from {post.company_name}"

            # Truncate what_changed for readability
            what_changed = post.text[:500] + "..." if len(post.text) > 500 else post.text

            signals.append({
                "fund_slug": post.company_slug,
                "signal_type": cp.signal_type.value,
                "title": title,
                "what_changed": what_changed,
                "source_url": post.source_url,
                "source_name": source_name,
                "observed_at": now,
                "published_at": post.published_at,
                "confidence": cp.confidence,
                "metadata": {
                    "linkedin_post_id": post.post_id,
                    "post_type": post.post_type,
                    "engagement": post.engagement,
                    "extracted_entities": cp.extracted_entities,
                    "classification_reason": cp.classification_reason,
                },
            })

        return signals
