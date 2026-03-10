"""
LinkedIn posts scraper for company feeds.

Extracts posts from company LinkedIn pages and converts them to
a standardized format for signal classification.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .apify_client import ApifyClient, ApifyConfig, ActorRunResult, save_raw_data
from ..io_utils import safe_json_write

logger = logging.getLogger(__name__)


@dataclass
class LinkedInPost:
    """Standardized LinkedIn post data."""

    post_id: str
    company_slug: str
    company_name: str
    text: str
    post_type: str  # article, update, job, celebration, share
    published_at: str | None
    engagement: dict[str, int] = field(default_factory=dict)
    media_urls: list[str] = field(default_factory=list)
    mentioned_companies: list[str] = field(default_factory=list)
    mentioned_people: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    source_url: str | None = None
    raw_data: dict[str, Any] | None = None


def _extract_post_id(item: dict[str, Any]) -> str:
    """Extract a unique post identifier."""
    # Try various fields that might contain the ID
    for key in ("urn", "id", "postId", "activityId"):
        if key in item and item[key]:
            return str(item[key])

    # Fallback: hash of URL or content
    url = item.get("url", item.get("postUrl", ""))
    text = item.get("text", item.get("content", ""))[:100]
    return f"post-{hash(url + text) & 0xFFFFFFFF:08x}"


def _extract_post_type(item: dict[str, Any]) -> str:
    """Determine the type of post."""
    post_type = item.get("type", item.get("postType", "")).lower()

    if post_type:
        type_mapping = {
            "article": "article",
            "share": "share",
            "job": "job",
            "celebration": "celebration",
            "milestone": "celebration",
            "video": "video",
            "image": "update",
            "document": "document",
        }
        return type_mapping.get(post_type, "update")

    # Infer from content
    text = item.get("text", item.get("content", "")).lower()
    if "hiring" in text or "job opening" in text or "we're looking" in text:
        return "job"
    if "congratulations" in text or "celebrating" in text or "milestone" in text:
        return "celebration"
    if item.get("articleUrl") or item.get("sharedArticle"):
        return "article"

    return "update"


def _extract_engagement(item: dict[str, Any]) -> dict[str, int]:
    """Extract engagement metrics."""
    engagement = {}

    # Different actor formats
    for likes_key in ("numLikes", "likes", "likeCount", "reactions"):
        if likes_key in item:
            engagement["likes"] = int(item[likes_key] or 0)
            break

    for comments_key in ("numComments", "comments", "commentCount"):
        if comments_key in item:
            engagement["comments"] = int(item[comments_key] or 0)
            break

    for shares_key in ("numShares", "shares", "shareCount", "reposts"):
        if shares_key in item:
            engagement["shares"] = int(item[shares_key] or 0)
            break

    return engagement


def _extract_media_urls(item: dict[str, Any]) -> list[str]:
    """Extract media URLs from post."""
    urls = []

    # Images
    images = item.get("images", item.get("media", []))
    if isinstance(images, list):
        for img in images:
            if isinstance(img, str):
                urls.append(img)
            elif isinstance(img, dict):
                urls.append(img.get("url", img.get("src", "")))

    # Video
    video_url = item.get("videoUrl", item.get("video", ""))
    if video_url:
        urls.append(video_url)

    return [u for u in urls if u]


def _extract_mentions(text: str) -> tuple[list[str], list[str]]:
    """Extract mentioned companies and people from post text."""
    companies = []
    people = []

    # LinkedIn mentions are typically formatted as @[Name](url)
    # Or just @Name
    mention_pattern = r"@\[?([^\]\n]+)\]?"
    mentions = re.findall(mention_pattern, text)

    for mention in mentions:
        mention = mention.strip()
        # Heuristic: company names often contain Inc, LLC, Ltd, etc.
        if any(suffix in mention for suffix in ("Inc", "LLC", "Ltd", "S.p.A", "SGR", "SpA")):
            companies.append(mention)
        else:
            people.append(mention)

    return companies, people


def _extract_hashtags(text: str) -> list[str]:
    """Extract hashtags from post text."""
    hashtag_pattern = r"#(\w+)"
    return re.findall(hashtag_pattern, text)


def _parse_timestamp(item: dict[str, Any]) -> str | None:
    """Parse post timestamp to ISO format."""
    for key in ("postedAt", "publishedAt", "date", "timestamp", "time"):
        if key in item and item[key]:
            value = item[key]

            # Already ISO format
            if isinstance(value, str) and "T" in value:
                return value

            # Unix timestamp (milliseconds)
            if isinstance(value, (int, float)) and value > 1e12:
                return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()

            # Unix timestamp (seconds)
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, timezone.utc).isoformat()

            # Try parsing common formats
            if isinstance(value, str):
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y"):
                    try:
                        dt = datetime.strptime(value, fmt)
                        return dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        continue

    return None


def normalize_post(
    item: dict[str, Any],
    company_slug: str,
    company_name: str,
) -> LinkedInPost:
    """
    Convert raw Apify post data to standardized LinkedInPost.

    Args:
        item: Raw post data from Apify
        company_slug: Fund slug for this company
        company_name: Company display name

    Returns:
        Normalized LinkedInPost object
    """
    text = item.get("text", item.get("content", item.get("body", "")))
    mentioned_companies, mentioned_people = _extract_mentions(text)

    return LinkedInPost(
        post_id=_extract_post_id(item),
        company_slug=company_slug,
        company_name=company_name,
        text=text,
        post_type=_extract_post_type(item),
        published_at=_parse_timestamp(item),
        engagement=_extract_engagement(item),
        media_urls=_extract_media_urls(item),
        mentioned_companies=mentioned_companies,
        mentioned_people=mentioned_people,
        hashtags=_extract_hashtags(text),
        source_url=item.get("url", item.get("postUrl")),
        raw_data=item,
    )


class LinkedInPostsScraper:
    """
    Scraper for LinkedIn company posts.

    Uses Apify to fetch posts and normalizes them for signal detection.
    """

    def __init__(
        self,
        client: ApifyClient | None = None,
        output_dir: Path | None = None,
    ):
        self.client = client or ApifyClient()
        self.output_dir = output_dir or Path("data/derived/linkedin")

    def scrape_company_posts(
        self,
        company_url: str,
        company_slug: str,
        company_name: str,
        max_posts: int = 10,
        save_raw: bool = True,
    ) -> list[LinkedInPost]:
        """
        Scrape posts from a single company's LinkedIn page.

        Args:
            company_url: LinkedIn company URL
            company_slug: Fund slug identifier
            company_name: Human-readable company name
            max_posts: Maximum posts to retrieve
            save_raw: Whether to save raw API response

        Returns:
            List of normalized LinkedInPost objects
        """
        logger.info(f"Scraping posts for {company_name} ({company_url})")

        result = self.client.scrape_company_posts(company_url, max_posts)

        if result.error:
            logger.error(f"Failed to scrape posts for {company_name}: {result.error}")
            return []

        if save_raw and result.items:
            raw_path = self.output_dir / "raw" / f"{company_slug}_posts.json"
            save_raw_data(result.items, raw_path, "company_posts")

        posts = []
        for item in result.items:
            try:
                post = normalize_post(item, company_slug, company_name)
                posts.append(post)
            except Exception as e:
                logger.warning(f"Failed to normalize post: {e}")
                continue

        logger.info(f"Scraped {len(posts)} posts from {company_name}")
        return posts

    def scrape_batch(
        self,
        companies: list[dict[str, str]],
        max_posts_per_company: int = 10,
        save_raw: bool = True,
    ) -> dict[str, list[LinkedInPost]]:
        """
        Scrape posts from multiple companies.

        Args:
            companies: List of dicts with 'slug', 'name', 'linkedin_url'
            max_posts_per_company: Max posts per company
            save_raw: Whether to save raw responses

        Returns:
            Dict mapping fund_slug to list of posts
        """
        all_posts = {}
        total_posts = 0
        total_cost = 0.0

        for company in companies:
            slug = company["slug"]
            name = company.get("name", slug)
            url = company.get("linkedin_url")

            if not url:
                logger.warning(f"No LinkedIn URL for {name}, skipping")
                continue

            posts = self.scrape_company_posts(
                company_url=url,
                company_slug=slug,
                company_name=name,
                max_posts=max_posts_per_company,
                save_raw=save_raw,
            )

            all_posts[slug] = posts
            total_posts += len(posts)

        logger.info(f"Batch complete: {total_posts} posts from {len(all_posts)} companies")
        return all_posts

    def save_posts(self, posts: list[LinkedInPost], filename: str = "linkedin_posts.json") -> Path:
        """Save normalized posts to JSON file."""
        output_path = self.output_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "post_count": len(posts),
            "posts": [asdict(p) for p in posts],
        }

        # Remove raw_data from output to keep file size reasonable
        for post in data["posts"]:
            post.pop("raw_data", None)

        safe_json_write(output_path, data)

        logger.info(f"Saved {len(posts)} posts to {output_path}")
        return output_path

    def load_posts(self, filename: str = "linkedin_posts.json") -> list[LinkedInPost]:
        """Load previously saved posts from JSON file."""
        input_path = self.output_dir / filename

        if not input_path.exists():
            logger.warning(f"Posts file not found: {input_path}")
            return []

        with open(input_path) as f:
            data = json.load(f)

        posts = []
        for item in data.get("posts", []):
            posts.append(LinkedInPost(**item))

        logger.info(f"Loaded {len(posts)} posts from {input_path}")
        return posts
