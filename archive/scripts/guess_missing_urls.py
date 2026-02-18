#!/usr/bin/env python3
"""
Guess missing URLs for funds using AI (OpenAI or Gemini), then test them.

This script:
1. Loads funds with no URLs from extractor_work_queue.json
2. Uses AI to guess potential website URLs for each fund
3. Tests each guessed URL to see if it's valid
4. Outputs results for manual review
"""

import json
import os
import time
import requests
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
DERIVED_DIR = DATA_DIR / "derived"
OUTPUT_FILE = DERIVED_DIR / "guessed_urls_results.json"
MARKDOWN_FILE = DERIVED_DIR / "guessed_urls_results.md"

# API Keys (from environment or .env)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = "REDACTED_GEMINI_KEY"

# API URLs
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"

# Request settings
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def load_env():
    """Load environment variables from .env file."""
    env_path = SCRIPT_DIR.parent / "apps" / "worker" / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)


def ask_gemini(prompt: str) -> str:
    """Call Gemini API with a prompt."""
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 2048,
        }
    }

    response = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

    result = response.json()
    return result["candidates"][0]["content"]["parts"][0]["text"]


def ask_openai(prompt: str) -> str:
    """Call OpenAI API with a prompt."""
    global OPENAI_API_KEY
    if not OPENAI_API_KEY:
        OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    if not OPENAI_API_KEY:
        raise Exception("No OpenAI API key available")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    data = {
        "model": "gpt-5-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_completion_tokens": 2048,
    }

    response = requests.post(
        OPENAI_API_URL,
        headers=headers,
        json=data,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

    result = response.json()
    return result["choices"][0]["message"]["content"]


def ask_ai(prompt: str, prefer_openai: bool = True) -> str:
    """Call AI API with a prompt, trying OpenAI first if preferred."""
    if prefer_openai:
        try:
            return ask_openai(prompt)
        except Exception as e:
            print(f"    OpenAI failed ({e}), trying Gemini...")
            return ask_gemini(prompt)
    else:
        try:
            return ask_gemini(prompt)
        except Exception as e:
            print(f"    Gemini failed ({e}), trying OpenAI...")
            return ask_openai(prompt)


def test_url(url: str) -> dict:
    """Test if a URL is accessible and returns valid content."""
    result = {
        "url": url,
        "valid": False,
        "status_code": None,
        "redirect_url": None,
        "error": None,
        "content_type": None,
    }

    if not url or not url.startswith("http"):
        result["error"] = "Invalid URL format"
        return result

    try:
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        result["status_code"] = response.status_code
        result["content_type"] = response.headers.get("Content-Type", "")

        # Track redirects
        if response.url != url:
            result["redirect_url"] = response.url

        # Check if valid response
        if response.status_code == 200:
            content_type = result["content_type"].lower()
            if "text/html" in content_type or "application/xhtml" in content_type:
                result["valid"] = True
            else:
                result["error"] = f"Non-HTML content type: {content_type}"
        else:
            result["error"] = f"HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
    except requests.exceptions.SSLError as e:
        result["error"] = f"SSL error: {str(e)[:50]}"
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"Connection error: {str(e)[:50]}"
    except Exception as e:
        result["error"] = str(e)[:100]

    return result


def guess_urls_for_fund(fund: dict) -> dict:
    """Use AI to guess URLs for a fund."""
    fund_id = fund["fund_id"]
    fund_name = fund["name"]
    existing_website = fund.get("website", "")
    reason = fund.get("reason", "")

    prompt = f"""You are helping find website URLs for an Italian private equity or venture capital fund.

Fund name: {fund_name}
Fund ID: {fund_id}
Existing info: {existing_website if existing_website else "No website known"}
Issue: {reason}

Please provide your best guesses for this fund's:
1. Main website URL (homepage)
2. Portfolio/Investments page URL (where they list their portfolio companies)

Consider common patterns for Italian PE/VC fund websites:
- Common domains: .it, .com, .eu
- Common naming: fundname.it, fundnamesgr.it, www.fundname.com
- Portfolio pages: /portfolio, /investments, /investimenti, /portafoglio

Respond ONLY with valid JSON in this exact format, no other text:
{{
    "homepage": "https://example.com" or null,
    "portfolio": "https://example.com/portfolio" or null,
    "confidence": "high", "medium", or "low",
    "notes": "brief explanation of your reasoning"
}}"""

    try:
        response = ask_ai(prompt, prefer_openai=True)

        # Clean up response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

        return json.loads(response.strip())
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}", "raw_response": response[:200]}
    except Exception as e:
        return {"error": str(e)}


def process_fund(fund: dict) -> dict:
    """Process a single fund: guess URLs and test them."""
    fund_id = fund["fund_id"]
    fund_name = fund["name"]

    print(f"  Processing: {fund_name}...")

    result = {
        "fund_id": fund_id,
        "name": fund_name,
        "original_website": fund.get("website", ""),
        "original_reason": fund.get("reason", ""),
        "ai_guesses": None,
        "tested_urls": [],
    }

    # Get AI guesses
    guesses = guess_urls_for_fund(fund)
    result["ai_guesses"] = guesses

    if "error" in guesses:
        print(f"    AI error: {guesses['error']}")
        return result

    # Test each guessed URL
    urls_to_test = []
    if guesses.get("homepage"):
        urls_to_test.append(("homepage", guesses["homepage"]))
    if guesses.get("portfolio"):
        urls_to_test.append(("portfolio", guesses["portfolio"]))

    for url_type, url in urls_to_test:
        print(f"    Testing {url_type}: {url}...", end=" ")
        test_result = test_url(url)
        test_result["type"] = url_type
        result["tested_urls"].append(test_result)

        if test_result["valid"]:
            print("✓ VALID")
        else:
            print(f"✗ {test_result.get('error', 'invalid')}")

    return result


def load_funds_without_urls() -> list:
    """Load funds that don't have URLs from the work queue."""
    work_queue_path = DERIVED_DIR / "extractor_work_queue.json"

    if not work_queue_path.exists():
        raise FileNotFoundError(f"Work queue not found: {work_queue_path}")

    with open(work_queue_path) as f:
        data = json.load(f)

    return data.get("no_urls", [])


def generate_markdown_report(results: list) -> str:
    """Generate a markdown report of the results."""
    lines = ["# Missing URL Guesses - Results\n"]
    lines.append(f"Generated from AI URL guessing. Review and add valid URLs manually.\n")

    # Summary
    total = len(results)
    valid_homepage = sum(1 for r in results if any(t.get("valid") and t.get("type") == "homepage" for t in r.get("tested_urls", [])))
    valid_portfolio = sum(1 for r in results if any(t.get("valid") and t.get("type") == "portfolio" for t in r.get("tested_urls", [])))
    ai_errors = sum(1 for r in results if r.get("ai_guesses", {}).get("error"))

    lines.append("## Summary\n")
    lines.append(f"- Total funds processed: {total}")
    lines.append(f"- Valid homepages found: {valid_homepage}")
    lines.append(f"- Valid portfolio pages found: {valid_portfolio}")
    lines.append(f"- AI errors: {ai_errors}\n")

    # Valid URLs to add
    lines.append("## ✓ Valid URLs Found (Add These)\n")
    lines.append("| Fund | Homepage | Portfolio |")
    lines.append("|------|----------|-----------|")

    for r in results:
        valid_home = next((t for t in r.get("tested_urls", []) if t.get("valid") and t.get("type") == "homepage"), None)
        valid_port = next((t for t in r.get("tested_urls", []) if t.get("valid") and t.get("type") == "portfolio"), None)

        if valid_home or valid_port:
            home_url = valid_home["url"] if valid_home else "-"
            port_url = valid_port["url"] if valid_port else "-"
            lines.append(f"| {r['name']} | {home_url} | {port_url} |")

    lines.append("")

    # Needs manual verification
    lines.append("## ⚠ Needs Manual Verification\n")
    lines.append("These URLs got non-200 responses or had issues but might still be valid:\n")
    lines.append("| Fund | URL | Issue |")
    lines.append("|------|-----|-------|")

    for r in results:
        for t in r.get("tested_urls", []):
            if not t.get("valid") and t.get("status_code") and t["status_code"] < 500:
                lines.append(f"| {r['name']} | {t['url']} | {t.get('error', 'Unknown')} |")

    lines.append("")

    # AI couldn't find
    lines.append("## ✗ No Valid URLs Found\n")
    lines.append("These funds need manual URL research:\n")

    no_valid = [r for r in results if not any(t.get("valid") for t in r.get("tested_urls", []))]
    for r in no_valid:
        guesses = r.get("ai_guesses", {})
        notes = guesses.get("notes", "No notes")
        lines.append(f"- **{r['name']}**: {notes}")

    return "\n".join(lines)


def main():
    """Main function."""
    load_env()

    print("=" * 60)
    print("GUESS MISSING URLs FOR FUNDS")
    print("=" * 60)

    # Load funds
    print("\nLoading funds without URLs...")
    funds = load_funds_without_urls()
    print(f"Found {len(funds)} funds without URLs")

    # Process each fund
    print("\nProcessing funds with AI...")
    results = []

    for i, fund in enumerate(funds):
        print(f"\n[{i+1}/{len(funds)}]", end="")
        result = process_fund(fund)
        results.append(result)
        time.sleep(0.5)  # Rate limiting

    # Save JSON results
    print(f"\n\nSaving results to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_funds": len(funds),
            "results": results,
        }, f, indent=2)

    # Generate and save markdown report
    print(f"Generating markdown report to {MARKDOWN_FILE}...")
    md_report = generate_markdown_report(results)
    with open(MARKDOWN_FILE, "w") as f:
        f.write(md_report)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    valid_homepage = sum(1 for r in results if any(t.get("valid") and t.get("type") == "homepage" for t in r.get("tested_urls", [])))
    valid_portfolio = sum(1 for r in results if any(t.get("valid") and t.get("type") == "portfolio" for t in r.get("tested_urls", [])))

    print(f"Total funds: {len(funds)}")
    print(f"Valid homepages found: {valid_homepage}")
    print(f"Valid portfolio pages found: {valid_portfolio}")
    print(f"\nResults saved to:")
    print(f"  JSON: {OUTPUT_FILE}")
    print(f"  Markdown: {MARKDOWN_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
