#!/usr/bin/env python3
"""
RSS feed monitor for Italian PE/VC news.

Fetches Italian financial news RSS feeds, matches articles to tracked funds
using local text matching, then classifies matched articles via LLM.
Appends resulting signals to detected_signals.json.

Two-stage processing to minimize API cost:
  Stage 1 — Local pre-filter: fast text matching against fund/company names
  Stage 2 — LLM classification: gpt-5-mini batch classification for matched articles

Usage:
    python -m fundradar_worker.rss_monitor              # full run
    python -m fundradar_worker.rss_monitor --dry-run    # preview matches, no writes
    python -m fundradar_worker.rss_monitor --feed BeBeez  # single feed only
    python -m fundradar_worker.rss_monitor --force       # ignore seen URLs, reprocess all
"""

import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
from dotenv import dotenv_values, load_dotenv

from .io_utils import backup_before_write, safe_json_write, sanitize_text, sanitize_url
from .slug_normalizer import get_slug_normalizer

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "derived"
FEEDS_CONFIG = PROJECT_ROOT / "data" / "rss_feeds.json"
SIGNALS_FILE = DATA_DIR / "detected_signals.json"
STATE_FILE = DATA_DIR / "rss_state.json"
DB_PATH = PROJECT_ROOT / "data" / "db.json"
PORTFOLIO_PATH = DATA_DIR / "portfolio_items.json"

# Load .env for OpenAI key
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)
if ENV_PATH.exists() and not os.environ.get("OPENAI_API_KEY"):
    env_vars = dotenv_values(ENV_PATH)
    if env_vars.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = env_vars["OPENAI_API_KEY"]

from fundradar_worker.paths import OPENAI_MODEL as MODEL
BATCH_SIZE = 5  # model uses ~500 tokens per article (incl. reasoning)
API_DELAY = 1.5  # seconds between API calls

# Quality scores by feed tier
TIER_QUALITY = {1: 85, 2: 80}

# Signal type mapping from LLM output to our signal types
# The LLM may return non-standard types; map them to canonical ones
LLM_TYPE_MAP = {
    "deal_announced": "deal_announced",
    "deal": "deal_announced",
    "acquisition": "deal_announced",
    "investment": "deal_announced",
    "exit_announced": "exit_announced",
    "exit": "exit_announced",
    "divestiture": "exit_announced",
    "sale": "exit_announced",
    "fundraise_announced": "fundraise_announced",
    "fundraise": "fundraise_announced",
    "fundraise_closed": "fundraise_closed",
    "fund_launch": "fund_launch",
    "people_move": "people_move",
    "hiring": "people_move",
    "appointment": "people_move",
    "debt_financing": "debt_financing",
    "debt": "debt_financing",
    "bond_issuance": "debt_financing",
    "financing": "debt_financing",
    "report": "report",
    "portfolio": "portfolio_update",
    "portfolio_update": "portfolio_update",
    "partnership": "partnership",
    "job_posting": "job_posting",
    "other": "other",
}

# Prospective/candidate language ("interested bidders", "in the running", rumors)
# can mention many funds that are not confirmed active transaction parties.
_STRONG_SPECULATIVE_CONTEXT_RE = re.compile(
    r"\b(?:among|fra|tra)\s+(?:the\s+)?(?:interested|potential)\s+(?:bidders|buyers|parties|investors)\b"
    r"|\b(?:interested|potential)\s+(?:bidders|buyers|parties|investors)\b"
    r"|\bin\s+the\s+running\b"
    r"|\bin\s+corsa\b"
    r"|\bgli\s+interessati\b"
    r"|\btra\s+gli\s+interessati\b"
    r"|\bfra\s+gli\s+interessati\b"
    r"|\b(?:vying|in\s+talks?|consider(?:ing)?)\b",
    re.IGNORECASE,
)
_SPECULATIVE_CONTEXT_RE = re.compile(
    r"\b(?:rumou?r(?:ed|s)?|reported(?:ly)?|could|might|may|possibly|potentially"
    r"|in\s+talks?|consider(?:ing)?|valuta|negozia|studia|ipotesi)\b",
    re.IGNORECASE,
)
_ACTIVE_PARTY_CONTEXT_RE = re.compile(
    r"\b(?:acqui(?:res|red|ring|sition)|sell(?:s|ing)?|sold|sale|exit(?:s|ed)?"
    r"|divest(?:s|ed)?|invest(?:s|ed|ing|ment)|back(?:ed)?|lead(?:s|ing)?"
    r"|co[-\s]?invest(?:or|ors)?|together\s+with|with\s+participation"
    r"|with\s+co[-\s]?investors?|guidat[oa]|partecipazion(?:e|i)"
    r"|acquisisc(?:e|ono)|acquista(?:no)?|vende(?:re|no)?|cessione|uscita)\b",
    re.IGNORECASE,
)
_LEGAL_SUFFIX_RE = re.compile(
    r"\s*(S\.?p\.?A\.?|S\.?r\.?l\.?|SGR|SICAF|SIM|S\.?A\.?|Ltd\.?|Inc\.?|GmbH|LLP|LP)\s*$",
    re.IGNORECASE,
)


def load_feeds(feed_name: str | None = None) -> list[dict]:
    """Load feed configuration from rss_feeds.json."""
    if not FEEDS_CONFIG.exists():
        logger.error(f"Feed config not found: {FEEDS_CONFIG}")
        return []
    with open(FEEDS_CONFIG) as f:
        config = json.load(f)
    feeds = config.get("feeds", [])
    if feed_name:
        feeds = [f for f in feeds if f["name"].lower() == feed_name.lower()]
        if not feeds:
            logger.warning(f"No feed found with name: {feed_name}")
    return feeds


def load_state() -> dict:
    """Load RSS processing state (seen URLs, last fetch times)."""
    if not STATE_FILE.exists():
        return {"seen_urls": {}, "last_fetch": {}, "signal_counter": 0}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"seen_urls": {}, "last_fetch": {}, "signal_counter": 0}


def _prune_seen_urls(state: dict, max_age_days: int = 30) -> int:
    """Remove seen URLs older than max_age_days to prevent unbounded growth."""
    seen = state.get("seen_urls", {})
    if not seen:
        return 0
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    cutoff_str = cutoff_dt.isoformat()
    pruned = 0
    to_remove = []
    for url, ts in seen.items():
        if isinstance(ts, str) and ts < cutoff_str:
            to_remove.append(url)
    for url in to_remove:
        del seen[url]
        pruned += 1
    return pruned


def save_state(state: dict) -> None:
    """Persist RSS processing state, pruning old seen URLs."""
    pruned = _prune_seen_urls(state)
    if pruned:
        logger.info(f"Pruned {pruned} seen URLs older than 30 days")
    safe_json_write(STATE_FILE, state)


def fetch_feed(url: str, timeout: int = 30) -> list[dict]:
    """Fetch and parse an RSS feed, returning list of entry dicts."""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "Fundradar/1.0"})
        if feed.bozo and not feed.entries:
            logger.warning(f"Feed parse error for {url}: {feed.bozo_exception}")
            return []
        entries = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            # Extract description/summary
            description = ""
            if hasattr(entry, "summary"):
                description = entry.summary
            elif hasattr(entry, "description"):
                description = entry.description
            # Clean HTML from description
            description = sanitize_text(description, max_length=2000) or ""
            # Extract published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                except Exception:
                    pass
            elif hasattr(entry, "published"):
                published = entry.published
            entries.append({
                "title": sanitize_text(title, max_length=300) or title[:300],
                "link": sanitize_url(link) or link,
                "description": description,
                "published": published,
            })
        return entries
    except Exception as e:
        logger.error(f"Failed to fetch feed {url}: {e}")
        return []


def _load_funds() -> list[dict]:
    """Load fund records from db.json."""
    if not DB_PATH.exists():
        return []
    try:
        with open(DB_PATH) as f:
            data = json.load(f)
        return data.get("funds", []) if isinstance(data, dict) else []
    except Exception:
        return []


def _load_portfolio_companies() -> dict[str, str]:
    """Load known portfolio company names from portfolio_items.json.

    Returns dict mapping lowercase company name -> fund slug.
    Filters out names that are common Italian/English words to reduce false positives.
    """
    # Common words that happen to be portfolio company names — skip them
    # Also includes well-known consumer brands owned by PE funds (Valentino, Moncler, etc.)
    # that generate massive false positives from fashion/art articles
    COMMON_WORD_BLOCKLIST = {
        # Common Italian/English words
        "unica", "europa", "vital", "persona", "vision", "tessi", "quali",
        "compre", "april", "concept", "merit", "field", "token", "impact",
        "builder", "squad", "anima", "festa", "novem", "sahar", "modifi",
        "esperi", "ensio", "ontinue", "supera", "entando", "trime", "scuter",
        "falcon", "agate", "talan", "magis", "diamanti", "metallo", "sofico",
        "pioneer", "camfin", "renaissance",
        # Consumer brands that appear frequently in fashion/art/sports media
        "valentino", "moncler", "missoni", "pittarosso", "paul & shark",
        "fincantieri", "citterio", "startupitalia", "bending spoons",
        # Common Italian words that are also portfolio company names
        "vittoria", "germani", "futura",
    }
    MIN_COMPANY_NAME_LEN = 6

    if not PORTFOLIO_PATH.exists():
        return {}
    try:
        with open(PORTFOLIO_PATH) as f:
            data = json.load(f)
        names: dict[str, str] = {}
        for fund_slug, companies in data.get("fund_portfolios", {}).items():
            for company in companies:
                name = company.get("name", "").strip()
                lower_name = name.lower()
                if (
                    name
                    and len(name) >= MIN_COMPANY_NAME_LEN
                    and lower_name not in COMMON_WORD_BLOCKLIST
                ):
                    names[lower_name] = fund_slug
        return names
    except Exception:
        return {}


def build_fund_name_index(funds: list[dict]) -> dict[str, str]:
    """
    Build a lookup mapping from text patterns to fund slugs.

    Includes: fund name, legal_name, slug variants, common abbreviations.
    Returns: dict mapping lowercase search term -> canonical slug.
    """
    index: dict[str, str] = {}
    # Track which keys were added as "short prefix" keys (vs full/legal names).
    # Used in post-processing to prune ambiguous prefix keys.
    short_keys: set[str] = set()

    for fund in funds:
        slug = fund.get("slug", "")
        name = fund.get("name", "")
        legal_name = fund.get("legal_name", "")
        if not slug or not name:
            continue

        # Full name (lowercase)
        index[name.lower()] = slug

        # Legal name
        if legal_name:
            index[legal_name.lower()] = slug

        # Slug as-is (some articles use slug-like references)
        index[slug] = slug

        # Name without legal suffixes for broader matching
        clean = re.sub(
            r"\s*(S\.?p\.?A\.?|S\.?r\.?l\.?|SGR|SICAF|SIM|S\.?A\.?|Ltd\.?|Inc\.?|GmbH|LLP|LP)\s*$",
            "",
            name,
            flags=re.IGNORECASE,
        ).strip()
        if clean and clean.lower() != name.lower() and len(clean) >= 4:
            index[clean.lower()] = slug

        # Legal name without legal suffixes
        if legal_name:
            clean_legal = re.sub(
                r"\s*(S\.?p\.?A\.?|S\.?r\.?l\.?|SGR|SICAF|SIM|S\.?A\.?|Ltd\.?|Inc\.?|GmbH|LLP|LP)\s*$",
                "",
                legal_name,
                flags=re.IGNORECASE,
            ).strip()
            if clean_legal and clean_legal.lower() != legal_name.lower() and len(clean_legal) >= 4:
                index[clean_legal.lower()] = slug

        # Handle common patterns:
        # "Fondo Italiano d'Investimento SGR" -> also match "Fondo Italiano"
        # But only if the shortened version is unique enough (>= 8 chars)
        words = name.split()
        if len(words) >= 3:
            short = " ".join(words[:2])
            if len(short) >= 8:
                # Don't add if it's too generic (e.g., "Private Equity", "Capital Partners")
                generic = {"private equity", "capital partners", "asset management", "venture capital"}
                if short.lower() not in generic:
                    index.setdefault(short.lower(), slug)
                    short_keys.add(short.lower())

    # Post-processing: remove ambiguous short-prefix keys.
    #
    # A 2-word short key is ambiguous when it is a strict prefix of another fund's
    # full registered key (for a different fund slug).  Example: "fondo italiano"
    # maps to fondo-italiano-d-investimento-sgr, but "fondo italiano per
    # l'efficienza energetica" maps to fiee-sgr.  Any article that starts with
    # FIEE's full legal name will also match "fondo italiano", incorrectly tagging
    # FII.  Removing the short key prevents the false match; FII articles still
    # match via their longer, unambiguous key ("fondo italiano d'investimento").
    ambiguous: set[str] = set()
    for short_key in short_keys:
        short_slug = index.get(short_key)
        for long_key, long_slug in index.items():
            if long_key == short_key:
                continue
            if long_key.startswith(short_key + " ") and long_slug != short_slug:
                # short_key is a prefix of a different fund's name — ambiguous
                ambiguous.add(short_key)
                break
    for key in ambiguous:
        logger.debug(
            "Removed ambiguous fund-name prefix key %r (conflicts with longer key for a different fund)",
            key,
        )
        del index[key]

    return index


def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _fund_name_variants_for_match(slug: str, fund_meta: dict[str, Any] | None) -> list[str]:
    """Build normalized fund-name variants for context checks."""
    variants: list[str] = []
    seen: set[str] = set()

    def _add(raw: str | None) -> None:
        if not raw or not isinstance(raw, str):
            return
        norm = _normalize_for_match(raw)
        if len(norm) < 4 or norm in seen:
            return
        seen.add(norm)
        variants.append(norm)

        clean = _normalize_for_match(_LEGAL_SUFFIX_RE.sub("", raw).strip())
        if len(clean) >= 4 and clean not in seen:
            seen.add(clean)
            variants.append(clean)

    if slug:
        _add(slug.replace("-", " "))
    meta = fund_meta or {}
    _add(meta.get("name"))
    _add(meta.get("legal_name"))
    return variants


def _is_speculative_only_fund_mention(
    article_text: str,
    slug: str,
    fund_meta: dict[str, Any] | None,
) -> bool:
    """True when all occurrences of a fund mention are in speculative context."""
    text = _normalize_for_match(article_text)
    if not text:
        return False

    variants = _fund_name_variants_for_match(slug, fund_meta)
    saw_match = False

    for name in variants:
        for match in re.finditer(r"\b" + re.escape(name) + r"\b", text):
            saw_match = True
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 60)
            context = text[start:end]
            if _STRONG_SPECULATIVE_CONTEXT_RE.search(context):
                continue
            is_speculative = bool(_SPECULATIVE_CONTEXT_RE.search(context))
            has_active_evidence = bool(_ACTIVE_PARTY_CONTEXT_RE.search(context))
            # If any occurrence is not speculative (or has active evidence), keep slug.
            if not is_speculative or has_active_evidence:
                return False

    return saw_match


def pre_filter_articles(
    entries: list[dict],
    fund_index: dict[str, str],
    portfolio_companies: dict[str, str],
) -> list[dict]:
    """
    Stage 1: Fast local text matching.

    For each article, check if title + description mentions any tracked
    fund name or known portfolio company. Returns articles with matched
    fund slugs attached.

    Fund name matches are prioritized over portfolio company matches.
    """
    matched = []
    for entry in entries:
        text = _normalize_for_match(f"{entry['title']} {entry['description']}")
        matched_slugs: set[str] = set()
        fund_name_matched_slugs: set[str] = set()

        # Check fund names (higher priority — always use word boundary matching)
        for pattern, slug in fund_index.items():
            if len(pattern) < 4:
                continue
            if re.search(r"\b" + re.escape(pattern) + r"\b", text):
                matched_slugs.add(slug)
                fund_name_matched_slugs.add(slug)

        # Check portfolio company names (word boundary matching to reduce false positives)
        matched_companies: list[str] = []
        for company_name, fund_slug in portfolio_companies.items():
            # Always use word boundary matching for company names
            if re.search(r"\b" + re.escape(company_name) + r"\b", text):
                matched_companies.append(company_name)
                # Also add the fund slug this company belongs to
                matched_slugs.add(fund_slug)

        if matched_slugs or matched_companies:
            entry["matched_fund_slugs"] = list(matched_slugs)
            entry["matched_companies"] = matched_companies
            # Track which slugs came from fund name matches (not just portfolio company)
            entry["_fund_name_matched_slugs"] = list(fund_name_matched_slugs)
            matched.append(entry)

    return matched


def classify_batch(
    articles: list[dict],
    client: Any,
    fund_index: dict[str, str],
) -> list[dict]:
    """
    Stage 2: LLM batch classification via gpt-5-mini.

    Sends batches of articles to the LLM for structured classification.
    Returns classified articles with signal_type, fund associations, etc.
    """
    if not articles:
        return []

    normalizer = get_slug_normalizer()
    classified = []

    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i : i + BATCH_SIZE]

        # Build article descriptions for the prompt
        article_texts = []
        for idx, article in enumerate(batch):
            article_texts.append(
                f"Article {idx + 1}:\n"
                f"Title: {article['title']}\n"
                f"Description: {article.get('description', '')[:500]}\n"
                f"Pre-matched funds: {', '.join(article.get('matched_fund_slugs', []))}\n"
                f"Pre-matched companies: {', '.join(article.get('matched_companies', []))}\n"
            )

        prompt = (
            "Classify each article for Italian PE/VC relevance.\n\n"
            "Return JSON: {\"articles\": [{\"fund_names\": [str], "
            "\"signal_type\": \"deal_announced|exit_announced|fundraise_announced|"
            "fundraise_closed|fund_launch|people_move|other\", "
            "\"is_rumor\": bool, "
            "\"italy_relevant\": bool, \"summary\": \"max 60 words, include key details: "
            "deal amount, company names, sector, Italian connection\", "
            "\"companies\": [str], \"amount\": str|null}]}\n\n"
            "IMPORTANT classification rules:\n"
            "- is_rumor=true when article describes negotiations, potential deals, "
            "rumors, or unconfirmed plans (words like: tratta, valuta, potrebbe, "
            "negozia, considera, in corsa, ipotesi, studia)\n"
            "- is_rumor=false when deal is confirmed/completed (words like: "
            "acquisisce, ha acquisito, perfeziona, chiude, rileva, firma)\n"
            "- signal_type=other for articles about fashion campaigns, art exhibitions, "
            "stock market commentary, sports, or politics — even if they mention a "
            "company owned by a PE fund\n"
            "- Only use deal_announced/exit_announced for actual PE/VC transactions\n"
            "- CRITICAL: Only include a fund in fund_names if it is an ACTIVE PARTY "
            "in the transaction (buyer, seller, investor, fund manager). "
            "Do NOT include a fund merely because its portfolio company is mentioned "
            "in an article about someone else's deal. "
            "Example: 'Fountain Vest buys Egla' — do NOT include Tikehau just because "
            "Egla was once a Tikehau portfolio company.\n\n"
            + "\n---\n".join(article_texts)
        )

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify Italian PE/VC news articles. "
                            "Return valid JSON only. Summaries should be 40-60 words with key details "
                            "(deal amount, company names, sector, Italian connection). "
                            "Use exact fund names from the article text. "
                            "Distinguish confirmed deals from rumors/negotiations. "
                            "Articles about fashion, art, sports, or stock prices "
                            "mentioning a PE-owned brand are NOT PE deals — classify as other."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=4000,
            )

            text = response.choices[0].message.content
            if not text:
                refusal = getattr(response.choices[0].message, "refusal", None)
                logger.warning(
                    f"LLM returned empty content for batch {i // BATCH_SIZE + 1}"
                    + (f" (refusal: {refusal})" if refusal else "")
                )
                # Fall back to pre-filter data
                for article in batch:
                    article["classified"] = {
                        "fund_slugs": article.get("matched_fund_slugs", []),
                        "signal_type": "other",
                        "italy_relevant": True,
                        "summary": article["title"],
                        "companies": article.get("matched_companies", []),
                        "amount": None,
                    }
                    classified.append(article)
                if i + BATCH_SIZE < len(articles):
                    time.sleep(API_DELAY)
                continue
            result = json.loads(text)
            llm_articles = result.get("articles", [])

            for idx, article in enumerate(batch):
                if idx < len(llm_articles):
                    llm = llm_articles[idx]
                    # Resolve fund names to canonical slugs
                    resolved_slugs: set[str] = set()
                    for fund_name in llm.get("fund_names", []):
                        norm_result = normalizer.normalize(name=fund_name)
                        if norm_result.slug:
                            resolved_slugs.add(norm_result.slug)

                    # Track LLM-confirmed slugs before merging pre-matched
                    llm_confirmed = set(resolved_slugs)

                    # Also keep pre-matched slugs
                    for slug in article.get("matched_fund_slugs", []):
                        resolved_slugs.add(slug)

                    article["classified"] = {
                        "fund_slugs": list(resolved_slugs),
                        "_llm_confirmed_slugs": list(llm_confirmed),
                        "signal_type": LLM_TYPE_MAP.get(
                            llm.get("signal_type", "other"), "other"
                        ),
                        "is_rumor": llm.get("is_rumor", False),
                        "italy_relevant": llm.get("italy_relevant", True),
                        "summary": llm.get("summary", ""),
                        "companies": llm.get("companies", []),
                        "amount": llm.get("amount"),
                    }
                    classified.append(article)

        except Exception as e:
            logger.error(f"LLM classification failed for batch {i // BATCH_SIZE + 1}: {e}")
            # Fall back: use pre-matched data without LLM enrichment
            for article in batch:
                article["classified"] = {
                    "fund_slugs": article.get("matched_fund_slugs", []),
                    "signal_type": "other",
                    "italy_relevant": True,
                    "summary": article["title"],
                    "companies": article.get("matched_companies", []),
                    "amount": None,
                }
                classified.append(article)

        if i + BATCH_SIZE < len(articles):
            time.sleep(API_DELAY)

    return classified


def articles_to_signals(
    classified: list[dict],
    feed: dict,
    state: dict,
    funds_by_slug: dict[str, dict],
) -> list[dict]:
    """
    Convert classified articles to signal dicts.

    Creates one signal per (article, fund_slug) pair.
    """
    signals = []
    now = datetime.now(timezone.utc).isoformat()
    counter = state.get("signal_counter", 0)

    for article in classified:
        classification = article.get("classified", {})
        fund_slugs = classification.get("fund_slugs", [])

        if not fund_slugs:
            continue

        # Which slugs came from fund-name text matching (not just portfolio company)
        fund_name_matched = set(article.get("_fund_name_matched_slugs", []))
        llm_confirmed = set(classification.get("_llm_confirmed_slugs", []))

        # Keep only accepted slugs after portfolio-only guard.
        # Use raw title+description for context checks (not LLM summary), so we
        # evaluate the original article language around each fund mention.
        article_text = " ".join(
            filter(
                None,
                [
                    article.get("title", ""),
                    article.get("description", ""),
                ],
            )
        )
        candidate_slugs: list[str] = []
        for slug in fund_slugs:
            # Skip if this slug was matched only via portfolio company name (not fund name)
            # AND the LLM didn't independently confirm it as relevant
            if slug not in fund_name_matched and slug not in llm_confirmed:
                logger.debug(
                    f"Skipping portfolio-only match: {slug} for '{article['title'][:60]}'"
                )
                continue
            if slug not in candidate_slugs:
                candidate_slugs.append(slug)

        if not candidate_slugs:
            continue

        speculative_only: dict[str, bool] = {}
        for slug in candidate_slugs:
            speculative_only[slug] = _is_speculative_only_fund_mention(
                article_text=article_text,
                slug=slug,
                fund_meta=funds_by_slug.get(slug),
            )

        # If at least one active/non-speculative slug is present (e.g. seller),
        # suppress speculative-only candidates (e.g. "in the running" bidders).
        # If all slugs are speculative, keep them (pure rumor article).
        has_non_speculative = any(not speculative_only[s] for s in candidate_slugs)
        accepted_slugs: list[str] = []
        for slug in candidate_slugs:
            if has_non_speculative and speculative_only.get(slug, False):
                logger.debug(
                    "Skipping speculative-only fund mention: %s for '%s'",
                    slug,
                    article.get("title", "")[:80],
                )
                continue
            accepted_slugs.append(slug)

        if not accepted_slugs:
            continue

        accepted_slugs = sorted(accepted_slugs)

        for slug in accepted_slugs:
            counter += 1

            is_rumor = classification.get("is_rumor", False)
            summary = classification.get("summary", article["title"])

            # NOTE: rss_monitor is the only producer of `related_fund_slugs`.
            # monitor.py signals don't write this field — the web layer re-derives
            # tags from text via signalFundTags.ts for those signals.
            signal = {
                "id": f"rss-signal-{counter:05d}",
                "fund_id": "",
                "fund_slug": slug,
                "related_fund_slugs": list(accepted_slugs),
                "signal_type": classification.get("signal_type", "other"),
                "title": article["title"],
                "what_changed": summary,
                "source_url": article["link"],
                "source_name": feed["name"],
                "published_at": article.get("published"),
                "observed_at": now,
                "created_at": now,
                "page_category": "NEWS",
                "page_type": "RSS_ITEM",
                "extraction_source": "rss_monitor",
                "italy_relevant": classification.get("italy_relevant", True),
                "quality_score": TIER_QUALITY.get(feed.get("tier", 2), 80),
                "is_rumor": is_rumor,
                "extracted_entities": {
                    "companies": classification.get("companies", []),
                    "people": [],
                    "locations": [],
                },
            }

            # Add amount if present
            amount = classification.get("amount")
            if amount:
                signal["deal_amount"] = amount

            signals.append(signal)

    state["signal_counter"] = counter
    return signals


def merge_into_signals(new_signals: list[dict]) -> int:
    """
    Append new RSS signals to detected_signals.json.

    Deduplicates by source_url within the existing signals file.
    Returns count of newly added signals.
    """
    if not new_signals:
        return 0

    # Load existing signals
    existing_data = {"signals": []}
    if SIGNALS_FILE.exists():
        try:
            with open(SIGNALS_FILE) as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = {"signals": []}

    existing_signals = existing_data.get("signals", [])

    # Build set of existing source URLs + fund_slug for dedup.
    # NOTE: Dedup key is source_url::fund_slug, so re-running RSS on an article
    # already in detected_signals.json will skip it — stale `related_fund_slugs`
    # on existing entries won't be updated. A full pipeline re-run from scratch
    # is needed to refresh all tags.
    existing_keys: set[str] = set()
    for s in existing_signals:
        url = s.get("source_url", "")
        slug = s.get("fund_slug", "")
        existing_keys.add(f"{url}::{slug}")

    # Filter out duplicates
    added = 0
    for signal in new_signals:
        key = f"{signal['source_url']}::{signal['fund_slug']}"
        if key not in existing_keys:
            existing_signals.append(signal)
            existing_keys.add(key)
            added += 1

    if added > 0:
        backup_before_write(SIGNALS_FILE)
        existing_data["signals"] = existing_signals
        safe_json_write(SIGNALS_FILE, existing_data)

    return added


def main(
    dry_run: bool = False,
    feed_name: str | None = None,
    force: bool = False,
) -> dict:
    """
    Main RSS monitor entry point.

    Returns summary dict with counts.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(f"\n{'=' * 60}")
    print("  Fundradar RSS Monitor")
    print(f"{'=' * 60}")

    # Load config
    feeds = load_feeds(feed_name)
    if not feeds:
        print("  No feeds configured. Check data/rss_feeds.json")
        return {"feeds": 0, "articles": 0, "matched": 0, "classified": 0, "signals": 0}

    # Load state
    state = load_state()

    # Load fund data
    funds = _load_funds()
    funds_by_slug = {f["slug"]: f for f in funds if f.get("slug")}
    fund_index = build_fund_name_index(funds)
    portfolio_companies = _load_portfolio_companies()

    print(f"  Feeds: {len(feeds)}")
    print(f"  Fund names indexed: {len(fund_index)}")
    print(f"  Portfolio companies indexed: {len(portfolio_companies)}")

    # Initialize OpenAI client (only if not dry-run)
    client = None
    if not dry_run:
        try:
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                print("  WARNING: OPENAI_API_KEY not set. Using pre-filter matches only.")
            else:
                client = OpenAI(api_key=api_key)
        except ImportError:
            print("  WARNING: openai package not installed. Using pre-filter matches only.")

    stats = {
        "feeds": len(feeds),
        "articles_total": 0,
        "articles_new": 0,
        "matched": 0,
        "classified": 0,
        "signals_created": 0,
        "signals_merged": 0,
    }

    all_new_signals: list[dict] = []

    # --- Parallel feed fetching ---
    # Fetch all feeds concurrently (network I/O bound), then process sequentially
    feed_entries: dict[str, list[dict]] = {}
    print(f"\n  Fetching {len(feeds)} feeds in parallel...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(feeds), 8)) as executor:
        future_to_feed = {
            executor.submit(fetch_feed, feed["url"]): feed
            for feed in feeds
        }
        for future in concurrent.futures.as_completed(future_to_feed):
            feed = future_to_feed[future]
            try:
                entries = future.result()
            except Exception as e:
                logger.error(f"Feed fetch failed for {feed['name']}: {e}")
                entries = []
            feed_entries[feed["name"]] = entries
            print(f"    {feed['name']}: {len(entries)} articles")

    for feed in feeds:
        entries = feed_entries.get(feed["name"], [])
        print(f"\n  --- {feed['name']} (Tier {feed.get('tier', '?')}) ---")
        stats["articles_total"] += len(entries)
        print(f"  Articles fetched: {len(entries)}")

        if not entries:
            continue

        # Filter out already-seen URLs
        seen_urls = state.get("seen_urls", {})
        if force:
            new_entries = entries
        else:
            new_entries = [e for e in entries if e["link"] not in seen_urls]
        stats["articles_new"] += len(new_entries)
        print(f"  New articles: {len(new_entries)} (skipped {len(entries) - len(new_entries)} seen)")

        if not new_entries:
            continue

        # Stage 1: Local pre-filter
        matched = pre_filter_articles(new_entries, fund_index, portfolio_companies)
        stats["matched"] += len(matched)
        print(f"  Pre-filter matches: {len(matched)}/{len(new_entries)}")

        if dry_run:
            for m in matched:
                slugs = ", ".join(m.get("matched_fund_slugs", []))
                companies = ", ".join(m.get("matched_companies", []))
                print(f"    MATCH: {m['title'][:80]}")
                if slugs:
                    print(f"           Funds: {slugs}")
                if companies:
                    print(f"           Companies: {companies}")
        else:
            # Stage 2: LLM classification
            if client and matched:
                classified = classify_batch(matched, client, fund_index)
                stats["classified"] += len(classified)
                print(f"  LLM classified: {len(classified)}")
            elif matched:
                # No LLM: use pre-filter matches directly
                for article in matched:
                    article["classified"] = {
                        "fund_slugs": article.get("matched_fund_slugs", []),
                        "signal_type": "other",
                        "italy_relevant": True,
                        "summary": article["title"],
                        "companies": article.get("matched_companies", []),
                        "amount": None,
                    }
                classified = matched
                stats["classified"] += len(classified)
            else:
                classified = []

            # Convert to signals
            new_signals = articles_to_signals(classified, feed, state, funds_by_slug)
            stats["signals_created"] += len(new_signals)
            all_new_signals.extend(new_signals)

            for s in new_signals:
                print(f"    SIGNAL [{s['signal_type']}] {s['fund_slug']}: {s['title'][:70]}")

        # Mark all fetched URLs as seen (even unmatched ones)
        for entry in entries:
            seen_urls[entry["link"]] = datetime.now(timezone.utc).isoformat()

        # Update last fetch time
        state.setdefault("last_fetch", {})[feed["name"]] = (
            datetime.now(timezone.utc).isoformat()
        )

        if not dry_run:
            # Commit this feed's signals and seen_urls immediately.
            # If the pipeline kills rss mid-run, already-processed feeds
            # won't be re-processed next time (no spiral of repeated work).
            merged_feed = merge_into_signals(new_signals)
            stats["signals_merged"] = stats.get("signals_merged", 0) + merged_feed
            state["seen_urls"] = seen_urls
            save_state(state)

    if not dry_run:
        # Final save to ensure last_fetch is written (feeds without new signals
        # still update last_fetch above but we flush once more for safety).
        state["seen_urls"] = seen_urls
        save_state(state)

    # Summary
    print(f"\n{'=' * 60}")
    print("  RSS Monitor Summary")
    print(f"{'=' * 60}")
    print(f"  Feeds processed: {stats['feeds']}")
    print(f"  Articles fetched: {stats['articles_total']}")
    print(f"  New articles: {stats['articles_new']}")
    print(f"  Pre-filter matches: {stats['matched']}")
    if not dry_run:
        print(f"  LLM classified: {stats['classified']}")
        print(f"  Signals created: {stats['signals_created']}")
        print(f"  Signals merged (new): {stats['signals_merged']}")

    return stats


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    feed_name = None

    i = 0
    while i < len(args):
        if args[i] == "--feed" and i + 1 < len(args):
            feed_name = args[i + 1]
            i += 2
        elif args[i].startswith("--feed="):
            feed_name = args[i].split("=", 1)[1]
            i += 1
        else:
            i += 1

    main(dry_run=dry_run, feed_name=feed_name, force=force)
