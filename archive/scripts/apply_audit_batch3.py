#!/usr/bin/env python3
"""Apply Gemini audit corrections - Batch 3: 9 Italian funds.
Charme, Consilium, Nextalia, Wise Equity, Itago, Neva, PM Partners, Sienna, Zest.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = REPO / "data" / "derived" / "portfolio_items.json"

def backup(path: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_suffix(f".json.bak_batch3_{ts}")
    shutil.copy2(path, dst)
    print(f"Backup: {dst}")

def apply_fixes(data: dict) -> dict:
    funds = data["fund_portfolios"]

    # =====================================================
    # FUND 1: Charme Capital
    # =====================================================
    slug = "charme-capital"
    entries = funds.get(slug, [])

    # Remove garbage entries
    garbage = {"Tata", "Medtronic", "Ima", "Livingbridge"}
    # Remove duplicates (sub-brands of Poltronafraugroup)
    duplicates = {"Poltronafrau", "Cassina", "Cappellini", "Bellco Hoxen", "Prismmedical"}
    remove = garbage | duplicates
    entries = [e for e in entries if e["name"] not in remove]

    # Apply sector and status fixes
    fixes = {
        "Poltronafraugroup": {"sector": "Consumer Goods", "status": "exited"},
        "Octotelematics": {"sector": "Technology", "status": "current"},
        "Bellco": {"sector": "Healthcare", "status": "exited"},
        "Igenomix": {"sector": "Biotech & Pharma", "status": "exited"},
        "Atopwinding": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Witherslackgroup": {"sector": "Education", "status": "current"},
        "Glovaladvisory": {"sector": "Professional Services", "status": "current"},
        "Fiocchi": {"sector": "Consumer Goods", "status": "current"},
        "Ocsnet": {"sector": "Fintech", "status": "current"},
        "Veritasint": {"sector": "Healthcare", "status": "current"},
        "Bianalisi": {"sector": "Healthcare", "status": "current"},
        "Indiba": {"sector": "Healthcare", "status": "current"},
        "Prismhealthcare": {"sector": "Healthcare", "status": "current"},
        "Temasinergie": {"sector": "Healthcare", "status": "current"},
        "Brightfuturescare": {"sector": "Education", "status": "current"},
        "Gruppoanimalia": {"sector": "Healthcare", "status": "current"},
        "Universae": {"sector": "Education", "status": "current"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    # Add missing entry: Carthusia
    entries.append({
        "name": "Carthusia",
        "sector": "Fashion & Luxury",
        "status": "current",
        "confidence": 0.9,
        "website": "https://www.carthusia.com",
        "description": "Italian luxury perfume brand from Capri.",
        "detail_page_url": None,
        "headquarters": "Capri, Italy",
        "investment_date": None
    })

    funds[slug] = entries
    print(f"Charme: {len(entries)} entries (removed {len(remove)} garbage/dupes, added Carthusia)")

    # =====================================================
    # FUND 2: Consilium SGR
    # =====================================================
    slug = "consilium-sgr"
    entries = funds.get(slug, [])

    fixes = {
        "Gruppo Manifatture Italiane": {"sector": "Fashion & Luxury"},
        "Dino Corsini": {"sector": "Food & Beverage"},
        "Music Center": {"sector": "Industrial Manufacturing"},
        "Fonderia Boccacci": {"sector": "Industrial Manufacturing"},
        "Cela": {"sector": "Industrial Manufacturing"},
        "Celli group": {"sector": "Industrial Manufacturing"},
        "Gelit": {"sector": "Food & Beverage"},
        "Macron": {"sector": "Consumer Goods"},
        "Rollon": {"sector": "Industrial Manufacturing"},
        "Gruppo Douglas": {"sector": "Retail"},
        "Nutkao": {"sector": "Food & Beverage"},
        "Ion Trading": {"sector": "Fintech"},
        "Marsilli": {"sector": "Industrial Manufacturing"},
        "MFU": {"sector": "Industrial Manufacturing"},
        "Bouty Healthcare": {"sector": "Biotech & Pharma"},
        "BBI Electric": {"sector": "Industrial Manufacturing"},
        "GMM": {"sector": "Industrial Manufacturing"},
        "Faccin": {"sector": "Industrial Manufacturing"},
        "Manifattura Riese": {"sector": "Fashion & Luxury"},
        "Tucano urbano": {"sector": "Consumer Goods"},
        "De Fonseca": {"sector": "Consumer Goods"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Consilium: {len(entries)} entries, {null_after} null sectors remaining")

    # =====================================================
    # FUND 3: Nextalia SGR
    # =====================================================
    slug = "nextalia-sgr"
    entries = funds.get(slug, [])

    fixes = {
        "Firstance": {"sector": "Fintech"},
        "Digited": {"sector": "Education"},
        "Deltatre": {"sector": "Media & Entertainment"},
        "Diagramgroup": {"sector": "Software"},
        "Regardia": {"sector": "Professional Services"},
        "Westrafo": {"sector": "Industrial Manufacturing"},
        "Tinexta": {"sector": "Professional Services"},
        "Hlpy": {"sector": "Insurance"},
        "Shopcircle": {"sector": "E-commerce"},
        "Rainapp": {"sector": "Fintech"},
        "Sovranai": {"sector": "Software"},
        "Tadapower": {"sector": "Energy & Utilities"},
        "Lingokids": {"sector": "Education"},
        "Underdogsgroup": {"sector": "Professional Services"},
        "Builder": {"sector": "Software"},
        "Cazampa": {"sector": "Healthcare"},
        "Flogroup": {"sector": "Food & Beverage"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    # Add missing: Igea Digital Health
    entries.append({
        "name": "Igea Digital Health",
        "sector": "Healthcare",
        "status": "current",
        "confidence": 0.9,
        "website": None,
        "description": "Digital health technology.",
        "detail_page_url": None,
        "headquarters": "Italy",
        "investment_date": None
    })

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Nextalia: {len(entries)} entries, {null_after} null sectors (added Igea Digital Health)")

    # =====================================================
    # FUND 4: Wise Equity SGR
    # =====================================================
    slug = "wise-equity-sgr"
    entries = funds.get(slug, [])

    fixes = {
        "Marullo": {"sector": "Food & Beverage"},
        "Absolute": {"sector": "Industrial Manufacturing"},
        "Casa della Piada": {"sector": "Food & Beverage"},
        "Greenexta": {"sector": "Environmental Services"},
        "NTC": {"sector": "Biotech & Pharma"},
        "Onetag": {"sector": "Media & Entertainment"},  # was Software, now AdTech
        "Almac": {"sector": "Industrial Manufacturing"},
        "Special Flanges": {"sector": "Industrial Manufacturing"},
        "Fi.Mo.Tec.": {"sector": "Telecommunications"},
        "Waycap": {"sector": "Fashion & Luxury"},
        "Innovery": {"sector": "Cybersecurity"},
        "Imprima": {"sector": "Fashion & Luxury"},
        "Aleph": {"sector": "Industrial Manufacturing"},
        "Cantiere del Pardo": {"sector": "Industrial Manufacturing"},
        "Tatuus": {"sector": "Automotive"},
        "Tapì": {"sector": "Industrial Manufacturing"},
        "Alpitour": {"sector": "Hospitality & Tourism"},
        "Controls Group": {"sector": "Industrial Manufacturing"},
        # Remaining nulls not in audit - fill with best guess from context
        "Primat": {"sector": "Industrial Manufacturing"},
        "Colcom": {"sector": "Industrial Manufacturing"},
        "Util Industries": {"sector": "Industrial Manufacturing"},
        "Selective Beauty": {"sector": "Consumer Goods"},
        "Totobit Informatica": {"sector": "Software"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Wise Equity: {len(entries)} entries, {null_after} null sectors remaining")

    # =====================================================
    # FUND 5: Itago Partners
    # =====================================================
    slug = "itago"
    entries = funds.get(slug, [])

    # Itago entries have S.R.L./S.P.A. suffixes, match accordingly
    fixes = {
        "VERNICI CALDART S.R.L.": {"sector": "Industrial Manufacturing"},
        "IDROSTUDI S.R.L.": {"sector": "Professional Services"},
        "APICE S.R.L.": {"sector": "Professional Services"},
        "ECO-TECHNO S.R.L.": {"sector": "Cleantech"},
        "OPERAMED S.R.L.": {"sector": "Healthcare"},
        "TEKNOICE S.R.L.": {"sector": "Industrial Manufacturing"},
        "SPRAYTECH S.R.L.": {"sector": "Industrial Manufacturing"},
        "SR MECATRONIC S.R.L.": {"sector": "Technology"},
        "CVS FERRARI S.P.A.": {"sector": "Industrial Manufacturing"},
        "PANIFICIO SAN FRANCESCO S.P.A.": {"sector": "Food & Beverage"},
        "SCAME FORNI INDUSTRIALI S.P.A.": {"sector": "Industrial Manufacturing"},
        "ISA – ALTANOVA S.R.L.": {"sector": "Technology"},
        "ABL S.P.A.": {"sector": "Industrial Manufacturing"},
        "FORNO D'ASOLO S.P.A.": {"sector": "Food & Beverage", "status": "exited"},
        "LAFERT S.P.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "NUOVA GIUNGAS S.R.L.": {"sector": "Industrial Manufacturing"},
        "VIMEC S.R.L.": {"sector": "Industrial Manufacturing"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    # ABL wasn't in the audit, adding sector
    # Check if ABL was handled
    abl_fixed = any(e["name"] == "ABL S.P.A." and e.get("sector") for e in entries)

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Itago: {len(entries)} entries, {null_after} null sectors, Forno d'Asolo+Lafert→exited")

    # =====================================================
    # FUND 6: Neva SGR
    # =====================================================
    slug = "neva-sgr"
    entries = funds.get(slug, [])

    fixes = {
        "Stylus Medicine": {"sector": "Biotech & Pharma"},
        "Nuclidium": {"sector": "Biotech & Pharma"},
        "CFS": {"sector": "Cleantech"},
        "Phosphorus": {"sector": "Biotech & Pharma"},
        "Kamau": {"sector": "Professional Services"},
        "NeoPhore": {"sector": "Biotech & Pharma"},
        "Energy Dome": {"sector": "Cleantech"},  # was Renewable Energy
        "Caracol": {"sector": "Industrial Manufacturing"},
        "Cool Planet Technologies": {"sector": "Cleantech"},
        "Tr1x": {"sector": "Biotech & Pharma"},
        "xFarm": {"sector": "Agriculture"},
        "Mirta": {"sector": "E-commerce"},
        "BetaGlue": {"sector": "Biotech & Pharma"},
        "Coro": {"sector": "Cybersecurity"},
        "CyberInt exit": {"sector": "Cybersecurity", "status": "exited"},
        # Remaining nulls not in audit
        "Seed X": {"sector": "Agriculture"},
        "Ternary": {"sector": "Software"},
        "Xnext": {"sector": "Technology"},
        "Xstream": {"sector": "Software"},
        "MatiPay": {"sector": "Fintech"},
        # Fix "exit" entries that should be exited status
        "Blubrake exit": {"status": "exited"},
        "Hazy exit": {"status": "exited"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Neva: {len(entries)} entries, {null_after} null sectors, CyberInt/Blubrake/Hazy→exited")

    # =====================================================
    # FUND 7: PM & Partners SGR
    # =====================================================
    slug = "pm-partners-sgr"
    entries = funds.get(slug, [])

    fixes = {
        "Bia": {"sector": "Food & Beverage"},
        "Montanaspa": {"sector": "Food & Beverage"},
        "Cognitive": {"sector": "Software"},
        "Italtergi": {"sector": "Automotive"},
        "Finlogic": {"sector": "Industrial Manufacturing"},  # was Software, now labeling systems
        "Cosmelux": {"sector": "Industrial Manufacturing"},
        "Cytech": {"sector": "Consumer Goods"},
        "Plastiape": {"sector": "Healthcare"},
        "Monviso": {"sector": "Food & Beverage"},
        "La Patria": {"sector": "Professional Services"},
        "Relevi": {"sector": "Consumer Goods"},
        "Maccorp": {"sector": "Financial Services"},
        "Vimec": {"sector": "Industrial Manufacturing"},
        "Argenta": {"sector": "Retail"},
        "Alfatherm": {"sector": "Industrial Manufacturing"},
        "Aeb": {"sector": "Industrial Manufacturing"},
        # Not in audit
        "Aive": {"sector": "Technology"},
        "Eco": {"sector": "Environmental Services"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"PM Partners: {len(entries)} entries, {null_after} null sectors remaining")

    # =====================================================
    # FUND 8: (Sienna Investment Managers Italia SGR — removed from db, no longer tracked)
    # =====================================================

    # =====================================================
    # FUND 9: Zest Group
    # =====================================================
    slug = "zest-group"
    entries = funds.get(slug, [])

    fixes = {
        "Gevi": {"sector": "Technology"},
        "Elai": {"sector": "Software"},
        "SartiQ": {"sector": "Software"},
        "Apside": {"sector": "Fintech"},
        "Open T": {"sector": "Software"},
    }
    for e in entries:
        if e["name"] in fixes:
            for k, v in fixes[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Zest: {len(entries)} entries, {null_after} null sectors remaining")

    return data


def main():
    print(f"Loading {PORTFOLIO_FILE}")
    with open(PORTFOLIO_FILE) as f:
        data = json.load(f)

    # Count nulls before
    total = sum(len(v) for v in data["fund_portfolios"].values())
    null_before = sum(1 for entries in data["fund_portfolios"].values() for e in entries if not e.get("sector"))
    print(f"Before: {total} total entries, {null_before} null sectors ({null_before*100/total:.1f}%)")
    print()

    backup(PORTFOLIO_FILE)
    data = apply_fixes(data)

    # Count nulls after
    total = sum(len(v) for v in data["fund_portfolios"].values())
    null_after = sum(1 for entries in data["fund_portfolios"].values() for e in entries if not e.get("sector"))
    print(f"\nAfter: {total} total entries, {null_after} null sectors ({null_after*100/total:.1f}%)")
    print(f"Fixed: {null_before - null_after} null sectors")

    # Write
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nWritten to {PORTFOLIO_FILE}")

    # Validate
    with open(PORTFOLIO_FILE) as f:
        json.load(f)
    print("JSON validation passed.")


if __name__ == "__main__":
    main()
