"""
URL canonicalization utilities for consistent URL matching.

Used across:
- Snapshot indexing / url_index lookups
- final_url / redirect mapping
- Enrichment URL → latest HTML lookup
"""

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def canonical_url(url: str) -> str:
    """
    Canonicalize a URL for consistent matching.

    Transforms:
    - Lowercase scheme and host
    - Remove default ports (80 for http, 443 for https)
    - Remove trailing slash (except for root path)
    - Sort query parameters
    - Remove common tracking parameters
    - Strip www. prefix for matching (optional, controlled)
    - Normalize path (remove double slashes)

    Args:
        url: The URL to canonicalize

    Returns:
        Canonicalized URL string
    """
    if not url:
        return ""

    # Parse the URL
    parsed = urlparse(url)

    # Lowercase scheme and host
    scheme = parsed.scheme.lower() or "https"
    host = parsed.hostname.lower() if parsed.hostname else ""

    # Handle port
    port = parsed.port
    if port:
        # Remove default ports
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            port = None

    # Reconstruct netloc
    netloc = host
    if port:
        netloc = f"{host}:{port}"

    # Normalize path
    path = parsed.path or "/"
    # Remove double slashes
    while "//" in path:
        path = path.replace("//", "/")
    # Remove trailing slash for non-root paths
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Handle query parameters
    query = ""
    if parsed.query:
        # Parse and sort query params, filter out tracking params
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Filter out common tracking params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "gclsrc", "dclid", "msclkid",
            "_ga", "_gl", "_hsenc", "_hsmi", "mc_cid", "mc_eid",
            "ref", "source", "s", "t",
        }
        filtered = {k: v for k, v in params.items() if k.lower() not in tracking_params}
        if filtered:
            # Sort keys for consistency
            sorted_params = sorted(filtered.items())
            # Flatten values (take first if multiple)
            flat_params = [(k, v[0] if v else "") for k, v in sorted_params]
            query = urlencode(flat_params)

    # Reconstruct URL
    canonical = urlunparse((scheme, netloc, path, "", query, ""))

    return canonical


def canonical_url_variants(url: str) -> list[str]:
    """
    Generate URL variants that should be considered equivalent.

    Returns list including:
    - Canonical form
    - With/without trailing slash
    - With/without www prefix

    Useful for looking up snapshots that may have been stored with slight variations.

    Args:
        url: The URL to generate variants for

    Returns:
        List of URL variants to try for matching
    """
    canonical = canonical_url(url)
    if not canonical:
        return []

    variants = [canonical]
    parsed = urlparse(canonical)

    # Add trailing slash variant
    if parsed.path != "/" and not parsed.path.endswith("/"):
        with_slash = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path + "/", "", parsed.query, ""
        ))
        variants.append(with_slash)
    elif parsed.path.endswith("/") and parsed.path != "/":
        without_slash = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", parsed.query, ""
        ))
        variants.append(without_slash)

    # Add www variants
    host = parsed.hostname or ""
    if host.startswith("www."):
        # Add without www
        no_www_host = host[4:]
        no_www_netloc = no_www_host
        if parsed.port and parsed.port not in (80, 443):
            no_www_netloc = f"{no_www_host}:{parsed.port}"
        no_www = urlunparse((
            parsed.scheme, no_www_netloc, parsed.path, "", parsed.query, ""
        ))
        variants.append(no_www)
    else:
        # Add with www
        www_host = f"www.{host}"
        www_netloc = www_host
        if parsed.port and parsed.port not in (80, 443):
            www_netloc = f"{www_host}:{parsed.port}"
        with_www = urlunparse((
            parsed.scheme, www_netloc, parsed.path, "", parsed.query, ""
        ))
        variants.append(with_www)

    return variants


def extract_domain(url: str, *, strip_www: bool = True) -> str:
    """
    Extract the domain from a URL, normalized for comparison.

    Handles edge cases: bare domains without scheme, www. prefix, empty URLs.
    This is the SINGLE source of truth for domain extraction across the pipeline.

    Args:
        url: The URL to extract domain from.
        strip_www: If True (default), strip leading "www." for matching.

    Returns:
        Domain string (lowercase, www-stripped by default). Empty string if invalid.
    """
    if not url:
        return ""
    # Handle bare domains without scheme
    if not url.startswith(("http://", "https://", "//")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if strip_www and domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs point to the same domain (ignoring www. prefix).

    This is the SINGLE source of truth for domain comparison across the pipeline.
    Use this instead of inline domain extraction + comparison.

    Args:
        url1: First URL (or domain).
        url2: Second URL (or domain).

    Returns:
        True if both resolve to the same domain.
    """
    d1 = extract_domain(url1)
    d2 = extract_domain(url2)
    return bool(d1 and d2 and d1 == d2)


def urls_match(url1: str, url2: str) -> bool:
    """
    Check if two URLs are equivalent after canonicalization.

    Args:
        url1: First URL
        url2: Second URL

    Returns:
        True if URLs are equivalent
    """
    return canonical_url(url1) == canonical_url(url2)


def build_canonical_index(url_list: list[str]) -> dict[str, str]:
    """
    Build an index mapping canonical URLs to original URLs.

    Args:
        url_list: List of URLs to index

    Returns:
        Dict mapping canonical_url -> original_url
    """
    index = {}
    for url in url_list:
        canonical = canonical_url(url)
        if canonical and canonical not in index:
            index[canonical] = url
    return index
