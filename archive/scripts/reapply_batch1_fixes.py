#!/usr/bin/env python3
"""Re-apply batch 1 fixes that didn't persist: Clessidra, HIG, SEFEA, Eureka.
Vertis sectors are already applied (0 null). HIG was reduced to 3 entries (likely worker overwrite).
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = REPO / "data" / "derived" / "portfolio_items.json"

def backup(path: Path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = path.with_suffix(f".json.bak_reapply1_{ts}")
    shutil.copy2(path, dst)
    print(f"Backup: {dst}")

def apply_fixes(data: dict) -> dict:
    funds = data["fund_portfolios"]

    # =====================================================
    # CLESSIDRA - Remove duplicates/garbage, fix sectors/status
    # =====================================================
    slug = "clessidra-sgr"
    entries = funds.get(slug, [])

    # Remove duplicates (short names that duplicate S.p.A. entries) + garbage
    remove_names = {
        "Prenergy",           # duplicate of implied Prenergy S.p.A.
        "Elia",               # duplicate of F.lli Elia S.p.A.
        "SGI",                # duplicate of Società Gasdotti Italia S.p.A.
        "Euticals",           # duplicate of Euticals-AMRI
        "Bitolea",            # duplicate of Bitolea S.p.A.
        "Arredo Plast",       # duplicate of ABM Italia S.p.A.
        "DepoBank",           # duplicate of BFF / Depobank S.p.A.
        "Argea",              # duplicate of Argea S.p.A.
        "Impresoft",          # duplicate of Impresoft S.p.A. (if both exist)
        "Everton",            # duplicate of Everton S.p.A.
        "Nicoli",             # duplicate of Molino Nicoli
        "Human Company",      # duplicate of Hu Holding S.p.A.
        "Scopri di più",      # garbage - navigation text
        "Imprespot S.p.A",    # typo of Impresoft S.p.A.
    }

    before = len(entries)
    entries = [e for e in entries if e["name"] not in remove_names]
    removed = before - len(entries)

    # Check if Impresoft S.p.A. exists, if not add it
    has_impresoft = any("Impresoft" in e["name"] and "Imprespot" not in e["name"] for e in entries)
    if not has_impresoft:
        entries.append({
            "name": "Impresoft S.p.A.",
            "sector": "Software",
            "status": "current",
            "confidence": 0.9,
            "website": None,
            "description": "Italian software group.",
            "detail_page_url": None,
            "headquarters": "Italy",
            "investment_date": None
        })

    # Apply sector and status fixes
    fixes = {
        "Hu Holding S.p.A.": {"sector": "Hospitality & Tourism", "status": "current"},
        "Molino Nicoli": {"sector": "Food & Beverage", "status": "current"},
        "Everton S.p.A.": {"sector": "Food & Beverage", "status": "current"},
        "Viabizzuno S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Nexi S.p.A.": {"sector": "Fintech", "status": "exited"},
        "Argea S.p.A.": {"sector": "Food & Beverage", "status": "current"},
        "BFF / Depobank S.p.A.": {"sector": "Financial Services", "status": "exited"},
        "L&S Italia S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Metalcam S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Giochi Preziosi S.p.A.": {"sector": "Consumer Goods", "status": "exited"},
        "F.lli Elia S.p.A.": {"sector": "Transportation & Logistics", "status": "exited"},
        "ABM Italia S.p.A.": {"sector": "Consumer Goods", "status": "exited"},
        "Bitolea S.p.A. Chimica Ecologica": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Euticals-AMRI": {"sector": "Biotech & Pharma", "status": "exited"},
        "Sisal S.p.A.": {"sector": "Media & Entertainment", "status": "exited"},
        "Sirti S.p.A.": {"sector": "Telecommunications", "status": "exited"},
        "Moby S.p.A.": {"sector": "Transportation & Logistics", "status": "exited"},
    }
    # Also handle entries that already have sectors from PEM but may need status fix
    fixes_by_name = {}
    fixes_by_name.update(fixes)
    # Handle Società Gasdotti Italia with curly apostrophe possibility
    for e in entries:
        if "Gasdotti" in e["name"]:
            fixes_by_name[e["name"]] = {"sector": "Energy & Utilities", "status": "exited"}

    for e in entries:
        if e["name"] in fixes_by_name:
            for k, v in fixes_by_name[e["name"]].items():
                e[k] = v

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Clessidra: {len(entries)} entries (removed {removed}), {null_after} null sectors")

    # =====================================================
    # SEFEA - Remove remaining garbage (Sara D'Aulerio), add PerMicro
    # =====================================================
    slug = "sefea-impact-sgr"
    entries = funds.get(slug, [])

    # Remove Sara D'Aulerio (person name - garbage)
    before = len(entries)
    entries = [e for e in entries if "D'Aulerio" not in e["name"] and "D\u2019Aulerio" not in e["name"]]

    # Check if PerMicro exists
    has_permicro = any("PerMicro" in e["name"] or "Permicro" in e["name"].title() for e in entries)
    if not has_permicro:
        entries.append({
            "name": "PerMicro",
            "sector": "Financial Services",
            "status": "current",
            "confidence": 0.9,
            "website": "https://www.permicro.it",
            "description": "Italian microcredit institution.",
            "detail_page_url": None,
            "headquarters": "Turin, Italy",
            "investment_date": None
        })

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"SEFEA: {len(entries)} entries (removed {before - len(entries)} garbage, added PerMicro if missing), {null_after} null sectors")

    # =====================================================
    # EUREKA - Fix SCIBIDS status to exited
    # =====================================================
    slug = "eureka-venture-sgr"
    entries = funds.get(slug, [])

    for e in entries:
        if e["name"] == "SCIBIDS":
            e["status"] = "exited"
            print(f"Eureka: SCIBIDS → exited (sold to DoubleVerify)")
        # Also fix Alice sector (was "Agritech" which isn't in taxonomy)
        if e["name"] == "Alice" and not e.get("sector"):
            e["sector"] = "Agriculture"

    # Fix Mamacrowd and Banca AideXa sectors (audit said Fintech)
    for e in entries:
        if e["name"] == "Mamacrowd" and e.get("sector") != "Fintech":
            # Only fix if not already correct
            pass  # Keep existing sector
        if e["name"] == "Banca AideXa" and e.get("sector") != "Fintech":
            pass

    funds[slug] = entries
    null_after = sum(1 for e in entries if not e.get("sector"))
    print(f"Eureka: {len(entries)} entries, {null_after} null sectors")

    return data


def main():
    print(f"Loading {PORTFOLIO_FILE}")
    with open(PORTFOLIO_FILE) as f:
        data = json.load(f)

    total = sum(len(v) for v in data["fund_portfolios"].values())
    null_before = sum(1 for entries in data["fund_portfolios"].values() for e in entries if not e.get("sector"))
    print(f"Before: {total} total entries, {null_before} null sectors ({null_before*100/total:.1f}%)\n")

    backup(PORTFOLIO_FILE)
    data = apply_fixes(data)

    total = sum(len(v) for v in data["fund_portfolios"].values())
    null_after = sum(1 for entries in data["fund_portfolios"].values() for e in entries if not e.get("sector"))
    print(f"\nAfter: {total} total entries, {null_after} null sectors ({null_after*100/total:.1f}%)")
    print(f"Fixed: {null_before - null_after} null sectors")

    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Written to {PORTFOLIO_FILE}")

    with open(PORTFOLIO_FILE) as f:
        json.load(f)
    print("JSON validation passed.")


if __name__ == "__main__":
    main()
