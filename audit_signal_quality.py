#!/usr/bin/env python3
"""
Comprehensive signal quality audit script.
Checks ALL signals for ALL quality issues without fixing anything.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# Source names to check for
SOURCE_NAMES = [
    "Finance Community",
    "BeBeez",
    "Il Sole 24 Ore",
    "FinanceCommunity",
    "Private Equity International",
    "Reuters",
    "Bloomberg",
    "Financial Times",
    "MF Milano Finanza",
    "Class CNBC",
    "Corriere della Sera",
    "La Repubblica",
    "ANSA",
]

# Italian monetary expressions to flag
ITALIAN_MONEY_PATTERNS = [
    r'\bmilioni di euro\b',
    r'\bmln euro\b',
    r'\bmiliardi?\b',
    r'\boltre\s+\d',  # "oltre 50 milioni"
    r'\bcirca\s+\d',  # "circa 100 milioni"
    r'\bmilioni\b(?!\s+euros?\b)',  # "milioni" without English context
]

# Truncation indicators
TRUNCATION_PATTERNS = [
    r'\.\.\.$',  # Ends with ...
    r'[a-z]$',  # Ends with lowercase (no punctuation)
    r'\b(di|da|a|in|con|per|il|la|i|le|un|una|and|or|the|of|to|in|with|for|at)$',  # Ends with preposition/article
]

# Portfolio company operation keywords
PORTFOLIO_OPERATION_KEYWORDS = [
    'portfolio company',
    'portfolio companies',
    'acquisisce',
    'acquires',
    'revenue',
    'ricavi',
    'fatturato',
    'espansione',
    'expansion',
    'bolt-on',
    'add-on acquisition',
]

def load_signals(file_path: str) -> List[Dict[str, Any]]:
    """Load enriched signals from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('signals', [])

def check_source_prefix(summary: str) -> str | None:
    """Check if summary starts with source name prefix."""
    if not summary:
        return None

    # Check for any source name followed by colon
    for source in SOURCE_NAMES:
        pattern = rf'^{re.escape(source)}\s*:\s*'
        if re.search(pattern, summary, re.IGNORECASE):
            return source

    # Also check for generic patterns like "SourceName:"
    match = re.match(r'^([A-Z][A-Za-z\s]+):\s+', summary)
    if match:
        prefix = match.group(1).strip()
        # Filter out false positives (proper nouns at start of sentence)
        if len(prefix.split()) <= 3 and prefix not in ['CEO', 'CFO', 'Managing Director']:
            return prefix

    return None

def check_fund_prefix(summary: str, fund_slug: str) -> bool:
    """Check if summary starts with fund name derived from slug."""
    if not summary or not fund_slug:
        return False

    # Convert slug to likely fund name (e.g., "clessidra-sgr" -> "Clessidra SGR")
    fund_name_parts = fund_slug.replace('-', ' ').split()
    fund_name_variations = [
        ' '.join([p.upper() if p.upper() in ['SGR', 'SIM', 'KKR', 'EQT', 'AVM'] else p.capitalize() for p in fund_name_parts]),
        ' '.join([p.capitalize() for p in fund_name_parts]),
        fund_slug.replace('-', ' ').upper(),
    ]

    for variation in fund_name_variations:
        pattern = rf'^{re.escape(variation)}\s*:\s*'
        if re.search(pattern, summary, re.IGNORECASE):
            return True

    return False

def check_italian_money(summary: str) -> List[str]:
    """Check for Italian monetary expressions."""
    if not summary:
        return []

    found = []
    for pattern in ITALIAN_MONEY_PATTERNS:
        matches = re.findall(pattern, summary, re.IGNORECASE)
        if matches:
            found.extend(matches)

    return found

def check_truncation(summary: str) -> str | None:
    """Check for truncated text."""
    if not summary:
        return None

    # Check for explicit truncation indicators
    for pattern in TRUNCATION_PATTERNS:
        if re.search(pattern, summary, re.IGNORECASE):
            return pattern

    # Check if ends mid-sentence (no final punctuation)
    if len(summary) > 50 and not re.search(r'[.!?"]$', summary.strip()):
        return "no_final_punctuation"

    return None

def check_all_caps(summary: str) -> List[str]:
    """Check for 3+ consecutive ALL CAPS words that aren't acronyms."""
    if not summary:
        return []

    # Find sequences of 3+ ALL CAPS words
    words = summary.split()
    all_caps_sequences = []
    current_sequence = []

    for word in words:
        # Remove punctuation for checking
        clean_word = re.sub(r'[^\w]', '', word)

        # Check if ALL CAPS and longer than 3 chars (to exclude acronyms)
        if clean_word.isupper() and len(clean_word) > 3:
            current_sequence.append(word)
        else:
            if len(current_sequence) >= 3:
                all_caps_sequences.append(' '.join(current_sequence))
            current_sequence = []

    # Don't forget last sequence
    if len(current_sequence) >= 3:
        all_caps_sequences.append(' '.join(current_sequence))

    return all_caps_sequences

def check_portfolio_misclassification(signal: Dict[str, Any]) -> bool:
    """Check if signal about portfolio company operations is misclassified."""
    signal_type = signal.get('signal_type', '')
    summary = (signal.get('enriched_summary', '') or '').lower()
    title = (signal.get('enriched_title', '') or signal.get('title', '')).lower()

    # Only check if NOT already classified as portfolio_update
    if signal_type == 'portfolio_update':
        return False

    # Check for portfolio company keywords
    text = f"{title} {summary}"
    for keyword in PORTFOLIO_OPERATION_KEYWORDS:
        if keyword in text:
            # Likely about portfolio company, not fund-level deal
            return True

    return False

def check_report_misclassification(signal: Dict[str, Any]) -> str | None:
    """Check if signal classified as 'report' is actually something else."""
    signal_type = signal.get('signal_type', '')

    if signal_type != 'report':
        return None

    summary = (signal.get('enriched_summary', '') or '').lower()
    title = (signal.get('enriched_title', '') or signal.get('title', '')).lower()
    text = f"{title} {summary}"

    # Check for people_move indicators
    people_keywords = ['appoints', 'nomina', 'hire', 'joins', 'nuovo', 'new ceo', 'new cfo', 'managing director', 'partner']
    if any(kw in text for kw in people_keywords):
        return "likely_people_move"

    # Check for deal indicators
    deal_keywords = ['acquisition', 'acquires', 'acquisisce', 'investment', 'investe', 'deal']
    if any(kw in text for kw in deal_keywords):
        return "likely_deal"

    # Check for exit indicators
    exit_keywords = ['exit', 'sells', 'sold', 'vende', 'venduto', 'cessione']
    if any(kw in text for kw in exit_keywords):
        return "likely_exit"

    # Check if actually about reports
    report_keywords = ['annual report', 'sustainability report', 'esg report', 'financial results', 'bilancio', 'relazione annuale']
    if not any(kw in text for kw in report_keywords):
        return "not_a_report"

    return None

def check_redundant_summary(signal: Dict[str, Any]) -> bool:
    """Check if enriched_summary just restates the title."""
    title = (signal.get('enriched_title', '') or signal.get('title', '')).strip().lower()
    summary = (signal.get('enriched_summary', '') or '').strip().lower()

    if not title or not summary:
        return False

    # Remove punctuation for comparison
    title_clean = re.sub(r'[^\w\s]', '', title)
    summary_clean = re.sub(r'[^\w\s]', '', summary)

    # Check if summary is just title repeated
    if title_clean == summary_clean:
        return True

    # Check if summary starts with title (allowing minor variations)
    title_words = set(title_clean.split())
    summary_words = summary_clean.split()[:len(title_clean.split()) + 3]  # Allow few extra words
    summary_word_set = set(summary_words)

    # If 90%+ overlap in first N words, likely redundant
    if len(title_words) > 0:
        overlap = len(title_words & summary_word_set) / len(title_words)
        if overlap > 0.9 and len(summary.split()) < len(title.split()) + 5:
            return True

    return False

def check_html_artifacts(summary: str) -> List[str]:
    """Check for HTML tags, CSS, or navigation text."""
    if not summary:
        return []

    artifacts = []

    # HTML tags
    if re.search(r'<[^>]+>', summary):
        artifacts.append("html_tags")

    # CSS
    if re.search(r'\{[^}]*:[^}]*\}', summary):
        artifacts.append("css")

    # Common navigation/UI text
    nav_patterns = [
        r'\bcookie\s+notice\b',
        r'\baccept\s+cookies\b',
        r'\bprivacy\s+policy\b',
        r'\bterms\s+of\s+service\b',
        r'\bsign\s+in\b',
        r'\blog\s+in\b',
        r'\bsubscribe\b',
        r'\bnewsletter\b',
        r'\bmenu\b.*\bhome\b',
    ]

    for pattern in nav_patterns:
        if re.search(pattern, summary, re.IGNORECASE):
            artifacts.append(f"nav_text:{pattern}")

    return artifacts

def check_italian_text(summary: str) -> bool:
    """Check if summary is mostly Italian instead of English."""
    if not summary or len(summary) < 20:
        return False

    # Common Italian words/patterns that indicate Italian text
    italian_indicators = [
        r'\bnel\b', r'\bnella\b', r'\bnello\b', r'\bnei\b', r'\bnelle\b',
        r'\bdel\b', r'\bdella\b', r'\bdello\b', r'\bdei\b', r'\bdelle\b',
        r'\bal\b', r'\balla\b', r'\ballo\b', r'\bai\b', r'\balle\b',
        r'\bcon\b', r'\bper\b', r'\bda\b', r'\bsu\b',
        r'\bche\b', r'\bcome\b', r'\banche\b',
        r'\bha\b', r'\bhanno\b', r'\bè\b', r'\bsono\b',
        r'\bmilioni\b', r'\bmiliardi\b', r'\banno\b', r'\bmese\b',
    ]

    # Count Italian indicators
    count = 0
    words = summary.split()

    for pattern in italian_indicators:
        matches = re.findall(pattern, summary, re.IGNORECASE)
        count += len(matches)

    # If 20%+ of words are Italian indicators, flag it
    if len(words) > 0 and count / len(words) > 0.2:
        return True

    # Also check for characteristic Italian verb endings
    italian_verbs = re.findall(r'\b\w+(ano|ono|ato|ito|are|ere|ire)\b', summary, re.IGNORECASE)
    if len(italian_verbs) > len(words) * 0.15:
        return True

    return False

def audit_signals(signals: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Run all audit checks on all signals."""
    issues = defaultdict(list)

    for signal in signals:
        signal_id = signal.get('id', 'unknown')
        fund_slug = signal.get('fund_slug', 'unknown')
        summary = signal.get('enriched_summary', '')

        # 1. Source name prefix
        source_prefix = check_source_prefix(summary)
        if source_prefix:
            issues['source_prefix'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'prefix': source_prefix,
                'summary': summary[:100]
            })

        # 2. Fund name prefix
        if check_fund_prefix(summary, fund_slug):
            issues['fund_prefix'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'summary': summary[:100]
            })

        # 3. Italian monetary expressions
        italian_money = check_italian_money(summary)
        if italian_money:
            issues['italian_money'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'expressions': italian_money,
                'summary': summary[:100]
            })

        # 4. Truncated text
        truncation = check_truncation(summary)
        if truncation:
            issues['truncation'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'pattern': truncation,
                'summary': summary[-100:] if len(summary) > 100 else summary
            })

        # 5. ALL CAPS words
        all_caps = check_all_caps(summary)
        if all_caps:
            issues['all_caps'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'sequences': all_caps,
                'summary': summary[:100]
            })

        # 6. Portfolio misclassification
        if check_portfolio_misclassification(signal):
            issues['portfolio_misclass'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'current_type': signal.get('signal_type', ''),
                'title': signal.get('enriched_title', signal.get('title', ''))[:100],
                'summary': summary[:100]
            })

        # 7. Wrong signal_type "report"
        report_issue = check_report_misclassification(signal)
        if report_issue:
            issues['report_misclass'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'issue': report_issue,
                'title': signal.get('enriched_title', signal.get('title', ''))[:100],
                'summary': summary[:100]
            })

        # 8. Redundant enriched_summary
        if check_redundant_summary(signal):
            issues['redundant_summary'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'title': signal.get('enriched_title', signal.get('title', ''))[:100],
                'summary': summary[:100]
            })

        # 9. HTML artifacts
        html_artifacts = check_html_artifacts(summary)
        if html_artifacts:
            issues['html_artifacts'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'artifacts': html_artifacts,
                'summary': summary[:100]
            })

        # 10. Italian text
        if check_italian_text(summary):
            issues['italian_text'].append({
                'id': signal_id,
                'fund_slug': fund_slug,
                'summary': summary[:200]
            })

    return dict(issues)

def print_report(issues: Dict[str, List[Dict[str, Any]]], total_signals: int):
    """Print formatted audit report."""
    print("=" * 80)
    print("SIGNAL QUALITY AUDIT REPORT")
    print("=" * 80)
    print(f"\nTotal signals checked: {total_signals}")
    print(f"Total issues found: {sum(len(v) for v in issues.values())}")
    print()

    issue_descriptions = {
        'source_prefix': 'SOURCE NAME PREFIX (should be stripped)',
        'fund_prefix': 'FUND NAME PREFIX (should be stripped)',
        'italian_money': 'ITALIAN MONETARY EXPRESSIONS',
        'truncation': 'TRUNCATED TEXT',
        'all_caps': 'ALL CAPS WORDS (3+)',
        'portfolio_misclass': 'PORTFOLIO COMPANY MISCLASSIFICATION',
        'report_misclass': 'WRONG SIGNAL TYPE "report"',
        'redundant_summary': 'REDUNDANT SUMMARY (restates title)',
        'html_artifacts': 'HTML ARTIFACTS / GARBAGE TEXT',
        'italian_text': 'ITALIAN TEXT (should be English)',
    }

    for issue_type, description in issue_descriptions.items():
        if issue_type in issues:
            print("=" * 80)
            print(f"{description}")
            print(f"Count: {len(issues[issue_type])}")
            print("=" * 80)
            print()

            for item in issues[issue_type]:
                print(f"Signal ID: {item['id']}")
                print(f"Fund: {item['fund_slug']}")

                # Print issue-specific details
                if issue_type == 'source_prefix':
                    print(f"Prefix: {item['prefix']}")
                elif issue_type == 'italian_money':
                    print(f"Expressions: {', '.join(item['expressions'])}")
                elif issue_type == 'truncation':
                    print(f"Pattern: {item['pattern']}")
                elif issue_type == 'all_caps':
                    print(f"Sequences: {', '.join(item['sequences'])}")
                elif issue_type == 'portfolio_misclass':
                    print(f"Current type: {item['current_type']}")
                    print(f"Title: {item['title']}")
                elif issue_type == 'report_misclass':
                    print(f"Issue: {item['issue']}")
                    print(f"Title: {item['title']}")
                elif issue_type == 'redundant_summary':
                    print(f"Title: {item['title']}")
                elif issue_type == 'html_artifacts':
                    print(f"Artifacts: {', '.join(item['artifacts'])}")

                print(f"Summary: {item['summary']}")
                print()
        else:
            print(f"\n{description}: No issues found ✓\n")

def main():
    """Main audit execution."""
    signals_file = Path(__file__).parent / 'data' / 'derived' / 'detected_signals_enriched.json'

    print(f"Loading signals from: {signals_file}")
    signals = load_signals(str(signals_file))
    print(f"Loaded {len(signals)} signals\n")

    print("Running comprehensive audit...")
    issues = audit_signals(signals)

    print_report(issues, len(signals))

    # Summary
    print("=" * 80)
    print("SUMMARY BY ISSUE TYPE")
    print("=" * 80)
    issue_descriptions = {
        'source_prefix': 'Source name prefix',
        'fund_prefix': 'Fund name prefix',
        'italian_money': 'Italian monetary expressions',
        'truncation': 'Truncated text',
        'all_caps': 'ALL CAPS words',
        'portfolio_misclass': 'Portfolio misclassification',
        'report_misclass': 'Wrong "report" type',
        'redundant_summary': 'Redundant summary',
        'html_artifacts': 'HTML artifacts',
        'italian_text': 'Italian text',
    }

    for issue_type, description in issue_descriptions.items():
        count = len(issues.get(issue_type, []))
        print(f"{description:.<50} {count:>3}")

    print(f"{'TOTAL':.<50} {sum(len(v) for v in issues.values()):>3}")
    print()

if __name__ == '__main__':
    main()
