"""Extractor regression: bridgepoint and apheon must reject caption/description
text that previously slipped into portfolio_items as company names.

Root cause: img alt and h3/h4 text on these fund websites sometimes carries
editorial captions ("Photo - team members in conversation") or marketing
descriptions ("Sustainability generates long-term and higher value"), not
company names. The Gemini portfolio enricher then perma-fails on them.
"""

from fundradar_worker.strategies.extractors import apheon, bridgepoint


# ─────────────────────────── Bridgepoint ────────────────────────────

def test_bridgepoint_rejects_photo_caption_in_img_alt():
    html = """
    <html><body>
      <img src="/portfolio/photos/team-meeting.jpg"
           alt="Photo - team members in conversation" />
      <img src="/portfolio/realcompany-logo.png" alt="RealCo" />
    </body></html>
    """
    companies = bridgepoint.extract_portfolio(html, "https://www.bridgepointgroup.com")
    names = [c["name"] for c in companies]
    assert "Photo - team members in conversation" not in names
    assert "RealCo" in names


def test_bridgepoint_rejects_long_description_heading():
    html = """
    <html><body>
      <h3>Acme</h3>
      <h3>A leading European provider of specialty chemicals for the food industry</h3>
    </body></html>
    """
    companies = bridgepoint.extract_portfolio(html, "https://www.bridgepointgroup.com")
    names = [c["name"] for c in companies]
    assert "Acme" in names
    assert all(len(n) <= 50 for n in names)


def test_bridgepoint_rejects_caption_prefix_variants():
    """Caption-prefix detection should match Photo:, Image -, Picture -, Figure –."""
    html = """
    <html><body>
      <h3>Photo: founders at the office</h3>
      <h3>Image - team off-site retreat</h3>
      <h3>Picture: signing ceremony</h3>
      <h3>Figure – revenue growth chart</h3>
      <h3>RealCo</h3>
    </body></html>
    """
    companies = bridgepoint.extract_portfolio(html, "https://www.bridgepointgroup.com")
    names = [c["name"] for c in companies]
    assert names == ["RealCo"]


# ──────────────────────────────── Apheon ────────────────────────────────

def test_apheon_rejects_marketing_description_in_link_heading():
    html = """
    <html><body>
      <a href="/investment/realco/"><h3>RealCo</h3></a>
      <a href="/investment/sustainability-page/">
        <h3>Sustainability generates long-term and higher value</h3>
      </a>
    </body></html>
    """
    companies = apheon.extract_portfolio(html, "https://www.apheon.com")
    names = [c["name"] for c in companies]
    assert "RealCo" in names
    assert "Sustainability generates long-term and higher value" not in names


def test_apheon_rejects_long_heading_strategy2():
    """Strategy 2 (fallback to non-link headings) must also apply the guard."""
    html = """
    <html><body>
      <h3>Brand</h3>
      <h3>An end-to-end provider of industrial automation services across Europe</h3>
    </body></html>
    """
    companies = apheon.extract_portfolio(html, "https://www.apheon.com")
    names = [c["name"] for c in companies]
    # Note: Strategy 2 only fires when fewer than 5 link-based companies were found
    assert "Brand" in names
    assert all(len(n) <= 50 for n in names)
