# Fundradar Signal Worker Prompt

Copy this entire prompt into a new Claude Code terminal to start improving signal quality.

---

```
You are a Fundradar signal worker. Your job is to ADD or FIX `extract_news()` functions in fund extractors to improve signal quality scores. You must NOT touch `extract_portfolio()` or `extract_team()` functions.

## CURRENT STATUS

- Many funds have extractors without `extract_news()` (Priority A — add the function)
- Some funds have `extract_news()` but 0 signals detected (Priority B — fix broken extraction)
- Some funds have no extractor at all (Priority C — create from scratch)
- Goal: Every fund with a news/press page should have a working `extract_news()`

## STEP 1: CLAIM A FUND (RUN THIS FIRST)

cd "$(git rev-parse --show-toplevel)"
FUND=$(python3 scripts/claim_signal_fund.py claim claude-N)  # Replace N with your terminal number
echo "Working on: $FUND"

# Get details about your fund:
python3 scripts/claim_signal_fund.py info $FUND

This uses file locking — no race conditions. The claim script uses signal_work_queue.json, which is completely separate from the portfolio extractor_work_queue.json.

Priority order: A (add news fn) → B (fix broken) → C (new extractor). You can also claim by priority:
python3 scripts/claim_signal_fund.py claim claude-N A   # Only Priority A
python3 scripts/claim_signal_fund.py claim claude-N B   # Only Priority B

## STEP 2: INVESTIGATE THE NEWS PAGE

Look up the fund's website from the `info` output, then find the news/press page.

Common news page URL patterns:
- /news, /news/, /en/news
- /press, /press-releases
- /media, /media-room
- /comunicati, /comunicati-stampa (Italian)
- /notizie, /in-evidenza (Italian)
- /insights, /blog

### 2a. Fetch the news page to analyze structure:

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from bs4 import BeautifulSoup

async def analyze():
    url = 'FUND_NEWS_URL'  # Replace with actual news page URL
    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))
        print(f'Fetched {len(res.html)} bytes')

        soup = BeautifulSoup(res.html, 'html.parser')

        # Look for news-like containers
        print('\nPotential news containers:')
        for selector in ['article', '.news-item', '.press-release', '.post', '.card',
                         'li.news', '.media-item', '.comunicato', '.entry', '[class*=news]',
                         '[class*=press]', '[class*=post]', '[class*=article]']:
            items = soup.select(selector)
            if items:
                print(f'  {selector}: {len(items)} items')
                # Show first item text preview
                first = items[0]
                text = first.get_text(strip=True)[:100]
                print(f'    preview: {text}')

        # Show headings that might be news titles
        print('\nHeadings (potential titles):')
        for tag in ['h2', 'h3', 'h4']:
            headings = soup.select(tag)
            for h in headings[:5]:
                text = h.get_text(strip=True)
                if len(text) > 15:
                    link = h.find_parent('a') or h.find('a')
                    href = link.get('href', '') if link else ''
                    print(f'  <{tag}>: {text[:60]} -> {href[:50]}')

        # Show time/date elements
        print('\nDate elements:')
        for el in soup.select('time, [datetime], .date, [class*=date]')[:5]:
            dt = el.get('datetime', '')
            text = el.get_text(strip=True)
            print(f'  {el.name}: datetime=\"{dt}\" text=\"{text}\"')

asyncio.run(analyze())
"

### 2b. If the page is small (<10KB) or empty, the site may be JS-rendered:

Try different approaches:
1. Check if there's a static HTML alternative URL
2. Check for JSON API endpoints (common: /wp-json/wp/v2/posts, /api/news)
3. If completely blocked, skip the fund

## STEP 3: UNDERSTAND SIGNAL CLASSIFICATION

The signals pipeline classifies news items by title keywords. To score well, news items should trigger these categories:

### Signal Types (from differ.py):

**deal_announced** (highest value):
  Italian: acquisisce, acquisizione, rileva, rilevato, investe in, entra nel capitale
  English: acquisition, acquire, portfolio company, deal, transaction, minority stake, majority stake

**exit_announced** (highest value):
  Italian: cede, ceduto, cessione, dismette, disinveste, vendita di
  English: exit, exits, sale of, sold, ipo, divest, divestment, listing

**fundraise_announced**:
  fund raise, fundraise, raising, close, closing, commit, committed

**people_move**:
  Italian: nomina, nominato, entra nel team, nuovo partner, nuovo direttore
  English: appoint, appointed, join, joins, joined, hire, hired, welcome, welcomes

**Noise — REJECTED if title matches:**
  English: cookie, privacy, gdpr, terms of service
  Italian: successivo, precedente, pagina, menu, contatti, chi siamo, governance

**Also rejected:**
  - Titles under 20 characters
  - Single-word titles (no spaces)

### What Makes Signals Score Well (from fundQuality.ts):

**Quantity & Diversity (40 pts):**
  - Has any signals: 10 pts
  - Count 10+: 10 pts (5-9: 6 pts, 1-4: 3 pts)
  - 4+ different signal types: 10 pts
  - Has deal_announced or exit_announced: 10 pts

**Quality (35 pts):**
  - Avg quality_score >= 70: 10 pts (>= 85: +5 pts)
  - Italy-relevant >= 50%: 10 pts
  - Avg relevance_score >= 0.2: 5 pts
  - what_changed > 30 chars: 5 pts

**Freshness (25 pts):**
  - Signal within 6 months: 15 pts (within 12 months: 5 pts)
  - All have source_url: 5 pts

**Practical target:** Extract 5-10+ news items with descriptive titles (>30 chars), include dates and URLs, and cover multiple categories (deals, exits, hires, fundraises).

## STEP 4: ADD OR FIX extract_news()

### 4a. Priority A: Add extract_news() to existing extractor

The fund already has an extractor file. Read it:

cat apps/worker/fundradar_worker/strategies/extractors/FILENAME.py

Then add the `extract_news()` function and register it in `EXTRACTORS`:

```python
def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from FUND_NAME news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select("YOUR_SELECTOR"):  # article, .news-item, li, etc.
        # Extract title
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        # Extract URL
        url = None
        link = item.select_one("a[href]")
        if not link:
            link = title_el if title_el.name == "a" else title_el.find_parent("a")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        # Extract date
        date = None
        date_el = item.select_one("time, [datetime], .date, [class*='date']")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        # Extract summary
        summary = None
        summary_el = item.select_one("p, .summary, .excerpt, .description")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news
```

Then update the EXTRACTORS dict at the bottom of the file:

```python
EXTRACTORS = {
    "portfolio": extract_portfolio,   # KEEP existing
    "team": extract_team,             # KEEP existing (if present)
    "news": extract_news,             # ADD this line
}
```

### 4b. Priority B: Fix broken extract_news()

The function exists but returns 0 items. Common problems:
1. **Wrong CSS selectors** — the site was redesigned. Analyze the current DOM and update selectors.
2. **JS-rendered content** — items load via AJAX. Look for JSON API endpoints or __NEXT_DATA__ scripts.
3. **Wrong page URL** — the news page moved. Update the URL in the site config.
4. **Domain mismatch** — DOMAIN constant doesn't match what Playwright fetches (www vs non-www).

### 4c. Priority C: Create new extractor from scratch

Copy the template and implement:

```python
"""Site-specific extractors for {domain}."""
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOMAIN = "{exact.domain.from.url}"  # MUST match URL domain exactly!


def extract_news(html: str, base_url: str) -> list[dict]:
    """Extract news/press items from {fund name} news page."""
    soup = BeautifulSoup(html, "html.parser")
    news = []
    seen_titles = set()

    for item in soup.select("YOUR_SELECTOR"):
        title_el = item.select_one("h2, h3, h4, .title, a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 10 or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        url = None
        link = item.select_one("a[href]")
        if not link:
            link = title_el if title_el.name == "a" else title_el.find_parent("a")
        if link and link.get("href"):
            url = urljoin(base_url, link["href"])

        date = None
        date_el = item.select_one("time, [datetime], .date, [class*='date']")
        if date_el:
            date = date_el.get("datetime") or date_el.get_text(strip=True)

        summary = None
        summary_el = item.select_one("p, .summary, .excerpt")
        if summary_el and summary_el != title_el:
            summary = summary_el.get_text(strip=True)[:300]

        news.append({
            "title": title,
            "url": url,
            "date": date,
            "summary": summary,
            "confidence": 0.85,
        })

    return news


EXTRACTORS = {
    "news": extract_news,
}
```

IMPORTANT: For Priority C, ONLY add `extract_news`. Do NOT implement portfolio or team — that's separate work.

## STEP 5: TEST YOUR EXTRACTOR

### 5a. Quick import test:

cd apps/worker && python3 -c "
from fundradar_worker.strategies.extractors.YOUR_MODULE import EXTRACTORS, DOMAIN
print(f'DOMAIN: {DOMAIN}')
print(f'Functions: {list(EXTRACTORS.keys())}')
assert 'news' in EXTRACTORS, 'Missing news extractor!'
print('OK - news extractor registered')
"

### 5b. Full extraction test:

cd apps/worker && python3 -c "
import asyncio
from fundradar_worker.playwright_fetcher import PlaywrightFetcher, FetchOptions
from fundradar_worker.strategies.extractors.YOUR_MODULE import EXTRACTORS, DOMAIN

async def test():
    url = 'FUND_NEWS_URL'  # Replace with news page URL
    print(f'Testing {DOMAIN} → {url}')

    async with PlaywrightFetcher() as fetcher:
        res = await fetcher.fetch(url, FetchOptions(wait_for_network_idle=True))
        print(f'Fetched {len(res.html)} bytes')

        news_fn = EXTRACTORS.get('news')
        if not news_fn:
            print('ERROR: No news extractor!')
            return

        items = news_fn(res.html, url)
        print(f'\nExtracted {len(items)} news items:')
        for item in items:
            title = item['title'][:60]
            date = item.get('date', 'no date')
            has_url = 'URL' if item.get('url') else 'no URL'
            print(f'  [{date}] {title}... ({has_url})')

        # Quality check
        print(f'\n--- Quality Check ---')
        print(f'Items: {len(items)} (target: 5+)')
        with_url = sum(1 for i in items if i.get('url'))
        print(f'With URL: {with_url}/{len(items)}')
        with_date = sum(1 for i in items if i.get('date'))
        print(f'With date: {with_date}/{len(items)}')
        avg_title_len = sum(len(i['title']) for i in items) / max(len(items), 1)
        print(f'Avg title length: {avg_title_len:.0f} chars (target: 30+)')

asyncio.run(test())
"

### 5c. Verify signal classification would work:

cd apps/worker && python3 -c "
from fundradar_worker.differ import classify_news_signal

test_titles = [
    # Paste actual extracted titles here
    'Example Company acquisisce Startup Italiana per 50 milioni',
    'Nomina del nuovo Managing Partner',
]

for title in test_titles:
    keep, stype = classify_news_signal(title)
    status = '✓' if keep else '✗'
    print(f'  {status} [{stype:20s}] {title[:60]}')
"

## STEP 6: MARK COMPLETE

cd "$(git rev-parse --show-toplevel)"
python3 scripts/claim_signal_fund.py complete $FUND

# If the fund has no news page at all, or is completely blocked:
python3 scripts/claim_signal_fund.py skip $FUND

Then claim next:
FUND=$(python3 scripts/claim_signal_fund.py claim claude-N)
echo "Working on: $FUND"
python3 scripts/claim_signal_fund.py info $FUND

## CRITICAL RULES

1. **CLAIM FIRST**: Always run the claim command before starting work
2. **ONLY MODIFY extract_news()**: Do NOT touch extract_portfolio() or extract_team()
3. **ONLY ADD "news" to EXTRACTORS**: Do NOT remove or change existing keys
4. **DOMAIN MUST MATCH**: The DOMAIN constant must exactly match the URL's domain (www vs non-www matters!)
5. **TEST BEFORE COMPLETE**: Verify your extractor returns items with titles, URLs, and dates
6. **USE 0.85 CONFIDENCE**: For well-structured CSS selector extractions
7. **ONE FUND AT A TIME**: Claim → fix → test → complete → next
8. **NEVER EDIT these files**: differ.py, noise_filter.py, monitor.py, fundQuality.ts, pipeline.py
9. **NEVER EDIT other extractors**: Only modify the file for your claimed fund
10. **SKIP if no news page**: Not all funds have news/press sections — that's OK

## COMMON ISSUES

**Extractor returns 0 items:**
- Check DOMAIN matches URL exactly (www vs non-www)
- Check if page is JS-heavy (small HTML = content loaded via JS)
- Try different CSS selectors — inspect the DOM more carefully
- Check for JSON data in <script> tags (__NEXT_DATA__, JSON-LD)

**Page returns small HTML (<10KB):**
- Site may be blocking scrapers — try with wait_for_network_idle=True
- Site may require JavaScript — Playwright should handle this
- If still empty, mark as skip

**Titles are too short or generic:**
- You may be selecting navigation items instead of news titles
- Add length filters (>20 chars) and dedup by title
- Check parent container — narrow your selector

**Date parsing issues:**
- Return dates as-is (string) — the pipeline handles normalization
- Common formats: "2025-01-15", "15 Gen 2025", "January 15, 2025"
- If no date element exists, set date to None (still valid)

**News on multiple pages / paginated:**
- Just extract from the first page — that's sufficient
- Don't follow pagination links

## CHECK STATUS ANYTIME

python3 scripts/claim_signal_fund.py status
```

---

## Quick Start for New Terminals

1. Open new terminal
2. Paste the prompt above
3. Run the claim command with your terminal number (claude-1, claude-2, etc.)
4. Work on your assigned fund
5. Mark complete and claim next
