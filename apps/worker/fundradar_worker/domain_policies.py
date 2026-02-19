"""
Domain policy management for Fundradar.

Handles domain-specific settings for fetching (timeouts, SSL, rate limits).
Includes auto-detection of JS-heavy sites requiring headless browser.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainPolicy(TypedDict, total=False):
    """Policy settings for a domain."""
    status: str  # ok, blocked, ssl_issue, slow, dns_error, rate_limited, intermittent
    reason: str
    timeout: int
    ssl_verify: bool
    retry_count: int
    rate_limit_delay: float
    requires_headless: bool
    skip_monitoring: bool


@dataclass
class FetchPolicy:
    """Resolved fetch policy for a URL."""
    timeout: int = 30
    ssl_verify: bool = True
    retry_count: int = 1
    rate_limit_delay: float = 1.0
    requires_headless: bool = False
    skip_monitoring: bool = False
    reason: str | None = None


class DomainPolicyRegistry:
    """
    Registry for domain-specific fetch policies.

    Loads policies from domain_policies.json and provides
    resolved settings for any URL.
    """

    def __init__(self, policies_path: Path | None = None):
        self.policies: dict[str, DomainPolicy] = {}
        self.default_policy: DomainPolicy = {
            "timeout": 30,
            "ssl_verify": True,
            "retry_count": 1,
            "rate_limit_delay": 1.0,
            "requires_headless": False,
            "skip_monitoring": False,
        }

        if policies_path and policies_path.exists():
            self._load(policies_path)

    def _load(self, path: Path):
        """Load policies from JSON file."""
        with open(path) as f:
            data = json.load(f)
            self.policies = data.get("policies", {})
            if "default_policy" in data:
                self.default_policy.update(data["default_policy"])

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()

    def get_policy(self, url: str) -> FetchPolicy:
        """
        Get the fetch policy for a URL.

        Looks up the domain in the registry, falls back to default.
        """
        domain = self._get_domain(url)

        # Try exact match first
        policy_data = self.policies.get(domain)

        # Try without www prefix
        if not policy_data and domain.startswith("www."):
            policy_data = self.policies.get(domain[4:])

        # Try with www prefix
        if not policy_data and not domain.startswith("www."):
            policy_data = self.policies.get(f"www.{domain}")

        # Merge with defaults
        merged = dict(self.default_policy)
        if policy_data:
            merged.update(policy_data)

        return FetchPolicy(
            timeout=merged.get("timeout", 30),
            ssl_verify=merged.get("ssl_verify", True),
            retry_count=merged.get("retry_count", 1),
            rate_limit_delay=merged.get("rate_limit_delay", 1.0),
            requires_headless=merged.get("requires_headless", False),
            skip_monitoring=merged.get("skip_monitoring", False),
            reason=merged.get("reason"),
        )

    def should_skip(self, url: str) -> tuple[bool, str | None]:
        """
        Check if a URL should be skipped based on policy.

        Note: As of Sprint 3, requires_headless no longer causes skipping
        since we now have Playwright support. Only skip_monitoring causes skipping.

        Returns (should_skip, reason).
        """
        policy = self.get_policy(url)
        if policy.skip_monitoring:
            return True, policy.reason
        # Note: requires_headless is now handled by WebsiteMonitor with Playwright fallback
        return False, None

    def get_blocked_domains(self) -> list[str]:
        """Get list of domains that are blocked or require headless."""
        blocked = []
        for domain, policy in self.policies.items():
            if policy.get("skip_monitoring") or policy.get("requires_headless"):
                blocked.append(domain)
        return blocked

    def get_stats(self) -> dict:
        """Get statistics about domain policies."""
        stats = {
            "total_policies": len(self.policies),
            "by_status": {},
            "blocked_count": 0,
            "requires_headless_count": 0,
        }

        for policy in self.policies.values():
            status = policy.get("status", "unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            if policy.get("skip_monitoring"):
                stats["blocked_count"] += 1
            if policy.get("requires_headless"):
                stats["requires_headless_count"] += 1

        return stats


@dataclass
class HeadlessDetectionResult:
    """Result of headless requirement detection."""

    requires_headless: bool
    confidence: float  # 0.0 to 1.0
    reasons: list[str]
    framework_detected: str | None = None


# Patterns indicating JS-heavy frameworks
JS_FRAMEWORK_PATTERNS = {
    "react": [
        r"<div\s+id=[\"']root[\"']\s*>\s*</div>",  # Empty React root
        r"<div\s+id=[\"']app[\"']\s*>\s*</div>",  # Empty app root
        r"__REACT_DEVTOOLS_GLOBAL_HOOK__",
        r"data-reactroot",
        r"react-app",
    ],
    "vue": [
        r"<div\s+id=[\"']app[\"']\s*>\s*</div>",
        r"__VUE_DEVTOOLS_GLOBAL_HOOK__",
        r"data-v-[a-f0-9]+",
        r"v-cloak",
    ],
    "angular": [
        r"<app-root[^>]*>\s*</app-root>",
        r"<app-root[^>]*>Loading",
        r"ng-version=",
        r"_ngcontent-",
        r"_nghost-",
    ],
    "next.js": [
        r"__NEXT_DATA__",
        r"_next/static",
        r"__next",
    ],
    "nuxt": [
        r"__NUXT__",
        r"_nuxt",
        r"nuxt-loading",
    ],
    "svelte": [
        r"__svelte",
        r"svelte-[a-z0-9]+",
    ],
}

# Patterns indicating minimal/loading HTML (requires JS to render)
MINIMAL_HTML_PATTERNS = [
    r"<body[^>]*>\s*<noscript>",  # Only noscript in body
    r"<body[^>]*>\s*<div[^>]*>\s*</div>\s*</body>",  # Empty div only
    r"<body[^>]*>\s*<div[^>]*>\s*Loading",  # Loading state
    r"<body[^>]*>\s*<script",  # Only scripts in body
    r"please\s+enable\s+javascript",
    r"javascript\s+(is\s+)?required",
    r"this\s+page\s+requires\s+javascript",
]

# Patterns indicating static HTML (doesn't require headless)
STATIC_HTML_INDICATORS = [
    r"<article[^>]*>",
    r"<main[^>]*>[\s\S]{500,}",  # Main with substantial content
    r"<section[^>]*>[\s\S]{300,}",  # Section with content
    r"<p[^>]*>[\s\S]{100,}",  # Paragraphs with content
    r"<table[^>]*>[\s\S]*<tr",  # Tables with rows
    r"wordpress",  # WordPress typically works without JS
    r"wp-content",
]


def detect_requires_headless(
    html: str,
    min_content_length: int = 500,
    log_reasoning: bool = True,
) -> HeadlessDetectionResult:
    """
    Detect if a page requires headless browser to render content.

    Analyzes HTML for indicators of JS-heavy frameworks and minimal content
    that suggest the page needs JavaScript execution.

    Args:
        html: The HTML content to analyze
        min_content_length: Minimum text content length to consider "rendered"
        log_reasoning: Whether to log detection reasoning

    Returns:
        HeadlessDetectionResult with detection outcome and reasoning
    """
    reasons = []
    confidence = 0.0
    framework_detected = None

    # Normalize HTML for analysis
    html_lower = html.lower()
    html_len = len(html)

    # Check 1: Detect JS frameworks first (even on short HTML)
    for framework, patterns in JS_FRAMEWORK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, html, re.IGNORECASE):
                framework_detected = framework
                reasons.append(f"{framework.title()} framework detected")
                confidence += 0.3
                break
        if framework_detected:
            break

    # Check 2: Extremely short HTML (likely not rendered)
    if html_len < 500:
        reasons.append(f"HTML too short ({html_len} chars)")
        confidence = max(confidence, 0.9)  # At least 0.9 for short HTML
        if log_reasoning:
            logger.debug(f"Headless detection: HTML too short ({html_len} chars)")
        return HeadlessDetectionResult(
            requires_headless=True,
            confidence=confidence,
            reasons=reasons,
            framework_detected=framework_detected,
        )

    # Check 2: Extract text content and check length
    # Simple text extraction (remove tags)
    text_content = re.sub(r"<[^>]+>", " ", html)
    text_content = re.sub(r"\s+", " ", text_content).strip()
    text_len = len(text_content)

    if text_len < min_content_length:
        reasons.append(f"Minimal text content ({text_len} chars)")
        confidence += 0.4

    # Check 3: Check for __NEXT_DATA__ with minimal content (framework already detected above)
    if "__NEXT_DATA__" in html:
        # Extract the JSON to see if it has rendered content
        next_data_match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        if next_data_match:
            next_data = next_data_match.group(1)
            # If Next.js data exists but page content is minimal, it needs JS
            if len(next_data) > 1000 and text_len < min_content_length:
                reasons.append("Next.js app with client-side rendering")
                framework_detected = "next.js"
                confidence += 0.3

    # Check 5: Minimal HTML patterns
    for pattern in MINIMAL_HTML_PATTERNS:
        if re.search(pattern, html_lower):
            reasons.append(f"Minimal/loading HTML pattern detected")
            confidence += 0.3
            break

    # Check 6: Static HTML indicators (reduce confidence)
    static_indicators_found = 0
    for pattern in STATIC_HTML_INDICATORS:
        if re.search(pattern, html_lower):
            static_indicators_found += 1

    if static_indicators_found >= 2:
        reasons.append(f"Static HTML indicators found ({static_indicators_found})")
        confidence -= 0.3

    # Normalize confidence
    confidence = max(0.0, min(1.0, confidence))

    # Determine result
    requires_headless = confidence >= 0.5

    if log_reasoning and reasons:
        logger.debug(
            f"Headless detection: requires={requires_headless}, "
            f"confidence={confidence:.2f}, reasons={reasons}"
        )

    return HeadlessDetectionResult(
        requires_headless=requires_headless,
        confidence=confidence,
        reasons=reasons,
        framework_detected=framework_detected,
    )


def update_domain_policy_headless(
    registry: "DomainPolicyRegistry",
    url: str,
    detection_result: HeadlessDetectionResult,
    auto_save: bool = False,
) -> bool:
    """
    Update domain policy based on headless detection result.

    Args:
        registry: The domain policy registry to update
        url: The URL that was analyzed
        detection_result: Result from detect_requires_headless
        auto_save: Whether to persist the update

    Returns:
        True if policy was updated
    """
    if not detection_result.requires_headless:
        return False

    if detection_result.confidence < 0.7:
        # Not confident enough to auto-update
        return False

    domain = urlparse(url).netloc.lower()

    # Check if policy already exists and has requires_headless set
    existing = registry.policies.get(domain, {})
    if existing.get("requires_headless"):
        return False  # Already marked

    # Update the policy
    reason = f"Auto-detected: {', '.join(detection_result.reasons[:2])}"
    if detection_result.framework_detected:
        reason = f"{detection_result.framework_detected.title()} app - {reason}"

    registry.policies[domain] = {
        **existing,
        "requires_headless": True,
        "reason": reason,
        "status": "requires_headless",
    }

    logger.info(f"Updated domain policy for {domain}: requires_headless=True ({reason})")

    return True


# Module-level registry instance
_registry: DomainPolicyRegistry | None = None


def get_domain_policy(domain_or_url: str) -> dict:
    """
    Get domain policy as a dict for a given domain or URL.

    Convenience function for scripts that need policy settings.

    Args:
        domain_or_url: Domain name or full URL

    Returns:
        Dict with policy settings (timeout, ssl_verify, retry_count, etc.)
    """
    global _registry

    if _registry is None:
        # Try to load from default location
        default_path = Path(__file__).parent.parent.parent.parent / "data" / "derived" / "domain_policies.json"
        _registry = DomainPolicyRegistry(default_path if default_path.exists() else None)

    # Make sure we have a URL-like string for the policy lookup
    if not domain_or_url.startswith(("http://", "https://")):
        domain_or_url = f"https://{domain_or_url}"

    policy = _registry.get_policy(domain_or_url)

    return {
        "timeout": policy.timeout,
        "ssl_verify": policy.ssl_verify,
        "retry_count": policy.retry_count,
        "rate_limit_delay": policy.rate_limit_delay,
        "requires_headless": policy.requires_headless,
        "skip_monitoring": policy.skip_monitoring,
        "reason": policy.reason,
    }
