# Fundradar URL Discovery Worker Prompt

Copy this entire prompt into a new Claude Code terminal to start working on URL discovery and extraction.

---

```
You are a Fundradar URL discovery worker. Your job is to find portfolio URLs and create extractors for funds.

## CURRENT STATUS

Actionable funds are grouped into three categories:
1. **Ready for extraction**: Have valid portfolio URLs - create extractors
2. **Need portfolio discovery**: Homepage works - find the portfolio page
3. **Need headless browser**: Requires Playwright - find portfolio and create extractor

## STEP 1: CHECK STATUS AND CLAIM A FUND

cd "/Users/filippoteodoro/Library/Mobile Documents/com~apple~CloudDocs/Code/Fundradar"
python3 scripts/url_discovery_worker.py status

# Claim a fund:
python3 scripts/url_discovery_worker.py claim claude-N  # Replace N with your terminal number

# Get details about your claimed fund:
python3 scripts/url_discovery_worker.py info YOUR_FUND_ID

## STEP 2: BASED ON TASK TYPE

### Task Type: create_extractor (Ready for extraction)
You have a valid portfolio URL. Go directly to STEP 3.

### Task Type: find_portfolio_url (Need portfolio discovery)
The homepage works but we don't know the portfolio page. Find it:

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from bs4 import BeautifulSoup

async def find_portfolio():
    url = 'HOMEPAGE_URL'  # Replace with homepage from info
    print(f'Scanning: {url}')

    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))
        soup = BeautifulSoup(res.html, 'html.parser')

        # Find portfolio-related links
        print('Portfolio-related links:')
        for link in soup.select('a[href]'):
            href = link.get('href', '')
            text = link.get_text(strip=True)[:40]
            if any(x in href.lower() or x in text.lower() for x in
                   ['portfolio', 'invest', 'partecip', 'companies', 'aziende', 'portafoglio']):
                print(f'  {text}: {href}')

        # Show all nav links
        print('\\nNavigation links:')
        for link in soup.select('nav a, header a, .menu a, .navbar a')[:15]:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            if text:
                print(f'  {text}: {href[:60]}')

asyncio.run(find_portfolio())
"

Once you find the portfolio URL, proceed to STEP 3.

### Task Type: headless_portfolio_discovery (Need headless browser)
The site blocks regular HTTP requests but works with Playwright. Use the same approach
as find_portfolio_url above - it already uses Playwright.

## STEP 3: ANALYZE THE PORTFOLIO PAGE

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from bs4 import BeautifulSoup

async def analyze():
    url = 'PORTFOLIO_URL'  # Replace with the portfolio URL
    print(f'Analyzing: {url}')

    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))
        print(f'Fetched {len(res.html)} bytes')

        soup = BeautifulSoup(res.html, 'html.parser')

        # Look for company containers
        print('\\nPotential company containers:')
        for selector in ['.portfolio-item', '.company', '.investment', 'article',
                        '.card', '.grid-item', '[data-company]', '.team-member']:
            items = soup.select(selector)
            if items:
                print(f'  {selector}: {len(items)} items')

        # Check for logos
        print('\\nImages with alt text:')
        for img in soup.select('img[alt]')[:15]:
            alt = img.get('alt', '').strip()
            if alt and len(alt) > 2:
                print(f'  {alt[:50]}')

        # Check headings
        print('\\nHeadings (potential company names):')
        for h in soup.select('h2, h3, h4')[:15]:
            text = h.get_text(strip=True)
            if text and len(text) < 60:
                print(f'  {h.name}: {text}')

asyncio.run(analyze())
"

## STEP 4: CREATE THE EXTRACTOR

File location: apps/worker/fundradar_worker/strategies/extractors/{fund_id_with_underscores}.py

CRITICAL: The DOMAIN must match exactly what the URL returns!
- If URL is https://www.example.com/ → DOMAIN = "www.example.com"
- If URL redirects to https://example.com/ → DOMAIN = "example.com"

Template:

```python
"""Site-specific extractors for {domain}."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "{exact.domain.from.url}"  # MUST match URL domain exactly!

def extract_portfolio(html: str, base_url: str) -> list[dict]:
    """Extract portfolio companies."""
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    seen = set()

    for item in soup.select("YOUR_SELECTOR"):
        name_el = item.select_one("NAME_SELECTOR")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Extract optional fields
        sector = None
        website = None
        description = None

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": description,
            "status": "current",
            "confidence": 0.85,
        })

    return companies

EXTRACTORS = {
    "portfolio": extract_portfolio,
}
```

## STEP 5: TEST YOUR EXTRACTOR

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from fundradar_worker.strategies.extractors.YOUR_MODULE import EXTRACTORS, DOMAIN

async def test():
    url = 'PORTFOLIO_URL'
    print(f'Testing {DOMAIN}')

    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))

        companies = EXTRACTORS['portfolio'](res.html, url)
        print(f'\\nExtracted {len(companies)} companies:')
        for c in companies[:10]:
            print(f'  - {c[\"name\"]}')

asyncio.run(test())
"

## STEP 6: MARK COMPLETE

cd /Users/filippoteodoro/Library/Mobile\ Documents/com~apple~CloudDocs/Code/Fundradar

# If successful (with portfolio URL if you discovered it):
python3 scripts/url_discovery_worker.py complete YOUR_FUND_ID https://portfolio-url

# If the site is broken/inaccessible/no portfolio:
python3 scripts/url_discovery_worker.py skip YOUR_FUND_ID "reason"

Then claim next: python3 scripts/url_discovery_worker.py claim claude-N

## CRITICAL RULES

1. **CLAIM FIRST**: Always run the claim command before starting work
2. **ONE FILE PER FUND**: Create extractors/{fund_id}.py
3. **DOMAIN MUST MATCH**: The DOMAIN constant must exactly match the URL's domain
4. **USE PLAYWRIGHT**: All fetching must use PlaywrightFetcher
5. **TEST BEFORE COMPLETE**: Verify your extractor returns data

## COMMON PATTERNS

**Companies in grid/cards:**
for item in soup.select(".portfolio-item, .company-card, article"):

**Companies from logo alt text:**
for img in soup.select("img[alt]"):
    if img.get("alt", "").startswith("logo "):
        name = img.get("alt").replace("logo ", "")

**Companies in data attributes:**
for el in soup.select("[data-company], [data-name]"):
    name = el.get("data-company") or el.get("data-name")

**Companies in table rows:**
for row in soup.select("table tr"):
    cells = row.select("td")
    if cells:
        name = cells[0].get_text(strip=True)
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `status` | Show queue status |
| `claim claude-N` | Claim next fund |
| `info fund-id` | Get fund details |
| `complete fund-id [url]` | Mark as done |
| `skip fund-id [reason]` | Skip fund |
