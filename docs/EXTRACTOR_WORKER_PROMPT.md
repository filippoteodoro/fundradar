# Fundradar Extractor Worker Prompt

Copy this entire prompt into a new Claude Code terminal to start working on extractors.

---

```
You are a Fundradar extractor worker. Your job is to FIX broken extractors or CREATE new ones for PE/VC fund websites.

## CURRENT STATUS

- Some extractors need FIXING (exist but return 0 data or low quality)
- Some funds need NEW extractors
- Goal: Get all funds to 90%+ extraction quality

## STEP 1: CLAIM A FUND (RUN THIS FIRST)

cd "/Users/filippoteodoro/Code/Fundradar"
FUND=$(python3 scripts/claim_fund.py claim claude-N)  # Replace N with your terminal number
echo "Working on: $FUND"

# Get details about your fund:
python3 scripts/claim_fund.py info $FUND

This uses file locking - no race conditions. The script will give you either a FIX task (broken extractor) or NEW task (no extractor exists).

## STEP 2: UNDERSTAND THE PROBLEM

For FIX tasks - check the existing extractor:
ls apps/worker/fundradar_worker/strategies/extractors/ | grep -i "$FUND"

# If found, read it:
cat apps/worker/fundradar_worker/strategies/extractors/FILENAME.py

For NEW tasks - there's no extractor yet. You need to create one.

## STEP 3: FETCH AND ANALYZE THE PAGE

Test the current extraction by fetching the page:

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from bs4 import BeautifulSoup

async def analyze():
    url = 'PORTFOLIO_URL_FROM_INFO'  # Replace with actual URL
    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))
        print(f'Fetched {len(res.html)} bytes')

        soup = BeautifulSoup(res.html, 'html.parser')

        # Look for common portfolio patterns
        print('\\nPotential company containers:')
        for selector in ['.portfolio-item', '.company', '.investment', 'article', '.card', '[data-company]']:
            items = soup.select(selector)
            if items:
                print(f'  {selector}: {len(items)} items')

        # Show sample links
        print('\\nSample links containing portfolio/company:')
        for link in soup.select('a[href]')[:30]:
            href = link.get('href', '')
            text = link.get_text(strip=True)[:40]
            if any(x in href.lower() for x in ['portfolio', 'company', 'investment', 'partecip']):
                print(f'  {href}: {text}')

asyncio.run(analyze())
"

## STEP 4: CREATE/FIX THE EXTRACTOR

Extractor file location: apps/worker/fundradar_worker/strategies/extractors/{fund_id_with_underscores}.py

CRITICAL: The DOMAIN must match exactly what the URL returns. For example:
- URL https://www.liftt.com/portfolio/ → DOMAIN = "www.liftt.com"
- URL https://aksiasgr.com/portfolio/ → DOMAIN = "aksiasgr.com" (no www)

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

    # Find company containers - adjust selector based on site structure
    for item in soup.select("YOUR_SELECTOR"):
        # Extract name
        name_el = item.select_one("NAME_SELECTOR")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        # Dedupe
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        # Extract optional fields
        sector = None
        sector_el = item.select_one(".sector, .industry")
        if sector_el:
            sector = sector_el.get_text(strip=True)

        website = None
        link = item.select_one("a[href^='http']")
        if link and 'linkedin' not in link.get('href', ''):
            website = link.get('href')

        companies.append({
            "name": name,
            "sector": sector,
            "website": website,
            "description": None,
            "status": "current",
            "confidence": 0.85,
        })

    return companies

def extract_team(html: str, base_url: str) -> list[dict]:
    """Extract team members."""
    soup = BeautifulSoup(html, "html.parser")
    members = []
    seen = set()

    for item in soup.select("YOUR_SELECTOR"):
        name_el = item.select_one("NAME_SELECTOR")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        if not name or len(name) < 3 or name.lower() in seen:
            continue
        seen.add(name.lower())

        title = None
        title_el = item.select_one(".title, .role, .position")
        if title_el:
            title = title_el.get_text(strip=True)

        members.append({
            "name": name,
            "title": title,
            "role": None,
            "linkedin": None,
            "confidence": 0.85,
        })

    return members

EXTRACTORS = {
    "portfolio": extract_portfolio,
    "team": extract_team,
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
            print(f\"  - {c['name']} ({c.get('sector', 'no sector')})\")

        if len(companies) > 10:
            print(f'  ... and {len(companies) - 10} more')

asyncio.run(test())
"

Target: Extract at least as many items as the old audit showed, with confidence >= 0.85

## STEP 6: MARK COMPLETE

cd /Users/filippoteodoro/Code/Fundradar
python3 scripts/claim_fund.py complete $FUND

# If the site is blocked/broken/no data available:
python3 scripts/claim_fund.py skip $FUND

Then claim next: FUND=$(python3 scripts/claim_fund.py claim claude-N)

## CRITICAL RULES

1. **CLAIM FIRST**: Always run the claim command before starting work
2. **ONE FILE PER FUND**: Create/edit only extractors/{fund_id}.py
3. **NEVER EDIT**: site_specific.py or other extractors/*.py files
4. **DOMAIN MUST MATCH**: The DOMAIN constant must exactly match the URL's domain
5. **TEST BEFORE COMPLETE**: Verify your extractor returns data
6. **USE 0.85 CONFIDENCE**: For well-structured extractions

## COMMON ISSUES

**Extractor returns 0 items:**
- Check DOMAIN matches URL exactly (www vs non-www matters!)
- Check if page is JS-heavy (may need different selectors)
- Check if site blocks scrapers (small HTML = blocked)

**Page returns small HTML (<10KB):**
- Site may be blocking - mark as skip
- Try a different URL pattern

**Can't find company containers:**
- Look for JSON-LD data in <script type="application/ld+json">
- Check for data attributes like data-company, data-name
- Look at image alt texts for company names

## CHECK STATUS ANYTIME

python3 scripts/claim_fund.py status
```

---

## Quick Start for New Terminals

1. Open new terminal
2. Paste the prompt above
3. Run the claim command with your terminal number (claude-1, claude-2, etc.)
4. Work on your assigned fund
5. Mark complete and claim next
