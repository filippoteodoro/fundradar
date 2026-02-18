#!/usr/bin/env python3
"""Apply Gemini audit corrections batch 2: CDP, Friulia, Investindustrial, Bridgepoint."""
import json
import os
import shutil

PORTFOLIO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "derived", "portfolio_items.json")

with open(PORTFOLIO_PATH, "r") as f:
    data = json.load(f)

fp = data["fund_portfolios"]

# ============================================================
# FUND 1: CDP Venture Capital SGR
# ============================================================
slug = "cdp-venture-capital"
if slug in fp:
    entries = fp[slug]

    # Remove garbage and duplicates
    remove_names = {
        "Connexa InsTech Srl e Connexa",
        "I'm ok Holding",
        "Volumeet S.r.l. - Musify",
        "Talent Garden Med",  # duplicate of Talent Garden
    }
    # Rename "Flyer Tech Srl - Transactionale" to "Flyer Tech"
    for e in entries:
        if e["name"] == "Flyer Tech Srl - Transactionale":
            e["name"] = "Flyer Tech"

    entries = [e for e in entries if e["name"] not in remove_names]

    cdp_fixes = {
        # NULL sector entries
        "3nd": {"sector": "Software"},
        "Altilia": {"sector": "Software"},
        "A Meras Annos": {"sector": "Food & Beverage"},
        "Arduino": {"sector": "Technology"},
        "Art Backers": {"sector": "Media & Entertainment"},
        "AWorld": {"sector": "Software"},
        "Axelera AI": {"sector": "Technology"},
        "Axyon AI": {"sector": "Fintech"},
        "Bedimensional": {"sector": "Industrial Manufacturing"},
        "Besafe Rate": {"sector": "Fintech"},
        "BrandOn Group": {"sector": "E-commerce"},
        "Buzzoole": {"sector": "Software"},
        "Cervellotik Education": {"sector": "Education"},
        "Confirmo": {"sector": "Healthcare"},
        "Cubbit": {"sector": "Software"},
        "Datafalls": {"sector": "Software"},
        "Develhope": {"sector": "Education"},
        "Dotx": {"sector": "Software"},
        "Edulia": {"sector": "Education"},
        "Eggtronic": {"sector": "Technology"},
        "Faba": {"sector": "Consumer Goods"},
        "FifthIngenium": {"sector": "Software"},
        "Flyer Tech": {"sector": "Software"},
        "FX12": {"sector": "Software"},
        "Genomeup": {"sector": "Healthcare"},
        "Genuino Blockchain Technologies": {"sector": "Software"},
        "Giffoni Innovation Hub": {"sector": "Media & Entertainment"},
        "Gility": {"sector": "Education"},
        "Gyala": {"sector": "Cybersecurity"},
        "Gymnasio": {"sector": "Software"},
        "Habacus": {"sector": "Fintech"},
        "Healthy Virtuoso": {"sector": "Software"},
        "Helmon": {"sector": "Software"},
        "Hevolus": {"sector": "Software"},
        "Hlpy": {"sector": "Insurance"},
        "HOPLIX": {"sector": "E-commerce"},
        "HT Materials Science Limited": {"sector": "Cleantech"},
        "Hydraink": {"sector": "Software"},
        "IEM": {"sector": "Software"},
        "Insight": {"sector": "Software"},
        "Italian Limited Edition": {"sector": "E-commerce"},
        "Laboratori Fabrici": {"sector": "Consumer Goods"},
        "Marshmallow Games": {"sector": "Education"},
        "Memento": {"sector": "Software"},
        "Multiverse Computing": {"sector": "Software"},
        "Mygrants S.r.l": {"sector": "Education"},
        "Naturbeads": {"sector": "Cleantech"},
        "Nextai": {"sector": "Software"},
        "Nexting": {"sector": "Software"},
        "Nexus": {"sector": "Software"},
        "Nouscom": {"sector": "Biotech & Pharma"},
        "Nozomi": {"sector": "Cybersecurity"},
        "Pedius": {"sector": "Software"},
        "Pharma Contact": {"sector": "Healthcare"},
        "Prestatech": {"sector": "Fintech"},
        "Qaplà": {"sector": "Software"},
        "Renewcast": {"sector": "Cleantech"},
        "SardexPay": {"sector": "Fintech"},
        "Shop Circle": {"sector": "Software"},
        "ShoppingAdvisor": {"sector": "E-commerce"},
        "Sibylla Biotech": {"sector": "Biotech & Pharma"},
        "Sqim": {"sector": "Industrial Manufacturing"},
        "StartupItalia": {"sector": "Media & Entertainment"},
        "Sweetguest Spa": {"sector": "Hospitality & Tourism"},
        "Talent Garden": {"sector": "Real Estate"},
        "The Portal": {"sector": "Software"},
        "TIEC": {"sector": "Software"},
        "Vection": {"sector": "Software"},
        "Viceversa": {"sector": "Fintech"},
        "WeSchool Srl": {"sector": "Education"},
        "Xoko": {"sector": "Software"},
        "YP Trainer": {"sector": "Software"},
        "Zaphiro": {"sector": "Energy & Utilities"},
        # Fix existing sectors
        "2Hire": {"sector": "Software"},
        "40 South Energy": {"sector": "Cleantech"},
        "Aether Fuels": {"sector": "Cleantech"},
        "Agade": {"sector": "Industrial Manufacturing"},
        "Babaco Market": {"sector": "Food & Beverage"},
        "CAEmate": {"sector": "Software"},
        "Caracol": {"sector": "Industrial Manufacturing"},
        "Codemotion": {"sector": "Education"},
        "Cyber Dyne": {"sector": "Software"},
        "DazeTechnology": {"sector": "Automotive"},
        "D-Orbit": {"sector": "Aerospace & Defense"},
        "Ekona Power": {"sector": "Cleantech"},
        "EnergyDome": {"sector": "Cleantech"},
        "Envision": {"sector": "Technology"},
        "Evja": {"sector": "Agriculture"},
        "HBI": {"sector": "Cleantech"},
        "Hexadrive": {"sector": "Industrial Manufacturing"},
        "IoAgri": {"sector": "Agriculture"},
        "Isaac": {"sector": "Construction"},
        "ITesla": {"sector": "Energy & Utilities"},
        "Leaf Space": {"sector": "Aerospace & Defense"},
        "Lean Team": {"sector": "Software"},
        "Macingo": {"sector": "Transportation & Logistics"},
        "Madeinadd": {"sector": "Industrial Manufacturing"},
        "Melaworks": {"sector": "Software"},
        "MOLE URBANA": {"sector": "Automotive"},
        "Next Generation Robotics": {"sector": "Industrial Manufacturing"},
        "Novac": {"sector": "Energy & Utilities"},
        "Otoqi": {"sector": "Transportation & Logistics"},
        "Phononic Vibes": {"sector": "Industrial Manufacturing"},
        "Prototipia": {"sector": "Industrial Manufacturing"},
        "Reefilla": {"sector": "Automotive"},
        "Rubber Conversion": {"sector": "Cleantech"},
        "Scuter": {"sector": "Automotive"},
        "Seares": {"sector": "Cleantech"},
        "Sidereus Space Dynamics": {"sector": "Aerospace & Defense"},
        "Soplaya": {"sector": "Food & Beverage"},
        "Soulkitchen": {"sector": "Food & Beverage"},
        "TAU": {"sector": "Industrial Manufacturing"},
        "Tziboo": {"sector": "Technology"},
        "Up2You": {"sector": "Environmental Services"},
        "Voidless": {"sector": "Industrial Manufacturing"},
        "WEART": {"sector": "Technology"},
        "WeMaintain": {"sector": "Real Estate"},
        "Wsense": {"sector": "Technology"},
        "Zerynth": {"sector": "Software"},
    }

    for entry in entries:
        if entry["name"] in cdp_fixes:
            for k, v in cdp_fixes[entry["name"]].items():
                entry[k] = v

    fp[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"CDP Venture: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# FUND 2: Friulia S.p.A.
# ============================================================
slug = "friulia"
if slug in fp:
    entries = fp[slug]

    # Remove garbage
    remove_names = {"First Cisl FVG"}
    entries = [e for e in entries if e["name"] not in remove_names]

    friulia_fixes = {
        # NULL sector entries
        "4DAYS S.R.L.": {"sector": "Professional Services"},
        "ALMA FOOD S.R.L.": {"sector": "Food & Beverage"},
        "ALVEO S.P.A.": {"sector": "Industrial Manufacturing"},
        "AMPLIA ENGINEERING & EQUIPMENT S.r.l.": {"sector": "Construction"},
        "BIOVALLEY INVESTMENTS S.P.A.": {"sector": "Biotech & Pharma"},
        "BIRRIFICIO 620 PASSI S.R.L.": {"sector": "Food & Beverage"},
        "CAFFARO INDUSTRIE S.P.A.": {"sector": "Industrial Manufacturing"},
        "CIVIBANK BANCA DI CIVIDALE S.P.A.": {"sector": "Financial Services", "status": "exited"},
        "DOM S.R.L.": {"sector": "Real Estate"},
        "EUROSERVIS S.R.L.": {"sector": "Professional Services"},
        "EUROTEL S.P.A.": {"sector": "Telecommunications"},
        "EVERTIS ITALIA S.P.A.": {"sector": "Industrial Manufacturing"},
        "FAMA S.R.L.": {"sector": "Industrial Manufacturing"},
        "FERRARI ING. FERRUCCIO S.R.L.": {"sector": "Transportation & Logistics"},
        "FINEST S.P.A.": {"sector": "Financial Services"},
        "FLORIAN S.P.A.": {"sector": "Industrial Manufacturing"},
        "GOOD MORNING ITALIA S.R.L.": {"sector": "Media & Entertainment"},
        "GUSTOCHEF S.R.L.": {"sector": "Food & Beverage"},
        "HOMY S.r.l.": {"sector": "Construction"},
        "INFO.ERA S.R.L.": {"sector": "Software"},
        "INTERPORTO DI TRIESTE S.P.A.": {"sector": "Transportation & Logistics"},
        "JULIA VITRUM S.P.A.": {"sector": "Industrial Manufacturing"},
        "MIDJ S.P.A.": {"sector": "Consumer Goods"},
        "MONDIAL COLOR SPA": {"sector": "Industrial Manufacturing"},
        "MULTIMEDIA S.R.L.": {"sector": "Software"},
        "MW FEP S.P.A.": {"sector": "Industrial Manufacturing"},
        "NEW LEAD S.R.L.": {"sector": "Professional Services"},
        "OFF.M.A. S.R.L.": {"sector": "Industrial Manufacturing"},
        "OFFICINE TECNOSIDER S.R.L.": {"sector": "Industrial Manufacturing"},
        "P&N S.R.L.": {"sector": "Industrial Manufacturing"},
        "PA GROUP S.P.A.": {"sector": "Professional Services"},
        "POETRONICART S.R.L.": {"sector": "Software"},
        "QUALITY FOOD GROUP S.P.A.": {"sector": "Food & Beverage"},
        "R.D.M. OVARO S.P.A.": {"sector": "Industrial Manufacturing"},
        "REAL ASCO S.P.A.": {"sector": "Real Estate"},
        "S.A.L.P. Societa' Appalto Lavori Pubblici S.P.A.": {"sector": "Construction"},
        "STI CORPORATE S.P.A.": {"sector": "Industrial Manufacturing"},
        "TIRSO S.P.A.": {"sector": "Industrial Manufacturing"},
        "TUBOTEC S.R.L.": {"sector": "Industrial Manufacturing"},
        "VBF NAUTICA S.R.L.": {"sector": "Industrial Manufacturing"},
        "VENCHIAREDO S.P.A.": {"sector": "Food & Beverage"},
        # Fix existing sectors
        "Allianz Torino Hub": {"sector": "Real Estate"},
        "AquafilSLO d.o.o": {"sector": "Industrial Manufacturing"},
        "CDA S.P.A.": {"sector": "Food & Beverage"},
        "F.I.S. S.P.A.": {"sector": "Biotech & Pharma"},
        "Net S.p.A.": {"sector": "Environmental Services"},
        "POLO TECNOLOGICO DI PORDENONE": {"sector": "Professional Services"},
        "Studio Galli Ingegneria S.p.A.": {"sector": "Professional Services"},
        "UNITS - Università degli Studi di Trieste": {"sector": "Education"},
    }

    for entry in entries:
        if entry["name"] in friulia_fixes:
            for k, v in friulia_fixes[entry["name"]].items():
                entry[k] = v

    fp[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"Friulia: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# FUND 3: Investindustrial
# ============================================================
slug = "investindustrial"
if slug in fp:
    entries = fp[slug]

    inv_fixes = {
        # NULL sector entries - Current
        "Arterex": {"sector": "Industrial Manufacturing"},
        "Bakelite Synthetics": {"sector": "Industrial Manufacturing"},
        "CEME": {"sector": "Industrial Manufacturing"},
        "CSM Ingredients": {"sector": "Food & Beverage"},
        "Delta Tecnic": {"sector": "Industrial Manufacturing"},
        "Flos B&B Italia Group": {"sector": "Consumer Goods"},
        "Dispensa Emilia": {"sector": "Hospitality & Tourism"},
        "Grupo Alacant": {"sector": "Food & Beverage"},
        "Italcanditi": {"sector": "Food & Beverage"},
        "Logic Group": {"sector": "Technology"},
        "Northius": {"sector": "Education"},
        "Omnia Technologies": {"sector": "Industrial Manufacturing"},
        "Ourvita": {"sector": "Healthcare"},
        "Vital": {"sector": "Healthcare"},
        "Windoria": {"sector": "Industrial Manufacturing"},
        # NULL sector entries - Exited
        "AEB Group": {"sector": "Industrial Manufacturing"},
        "Applus": {"sector": "Professional Services"},
        "Aston Martin": {"sector": "Automotive"},
        "Atida": {"sector": "E-commerce"},
        "Avincis": {"sector": "Aerospace & Defense"},
        "BPM": {"sector": "Financial Services"},
        "Benvic": {"sector": "Industrial Manufacturing"},
        "Castaldi": {"sector": "Industrial Manufacturing"},
        "Comax France": {"sector": "Industrial Manufacturing"},
        "Contenur": {"sector": "Environmental Services"},
        "Ducati": {"sector": "Automotive"},
        "Euskaltel": {"sector": "Telecommunications"},
        "Eutelsat": {"sector": "Telecommunications"},
        "Gardaland": {"sector": "Hospitality & Tourism"},
        "GeneraLife": {"sector": "Healthcare"},
        "Grupo Care": {"sector": "Healthcare"},
        "HTG": {"sector": "Technology"},
        "Johnson Radley": {"sector": "Industrial Manufacturing"},
        "lifebrain": {"sector": "Healthcare"},
        "Logic Control": {"sector": "Technology"},
        "Perfume Holding": {"sector": "Consumer Goods"},
        "RTS": {"sector": "Transportation & Logistics"},
        "Svenson": {"sector": "Healthcare"},
        "Zero9": {"sector": "Media & Entertainment"},
        # Fix existing entries with wrong/non-taxonomy sectors
        "Eataly": {"sector": "Retail & Consumer"},
        "Guala Closures": {"sector": "Industrial Manufacturing"},
        "Virospack": {"sector": "Industrial Manufacturing"},
        "Forgital Group": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Gruppo Coin": {"sector": "Retail & Consumer"},
        "Italmatch Chemicals": {"sector": "Industrial Manufacturing"},
        "Karrimor": {"sector": "Retail & Consumer"},
        "Mountain Warehouse": {"sector": "Retail & Consumer"},
        "Neolith": {"sector": "Industrial Manufacturing"},
        "Panda Security": {"sector": "Cybersecurity"},
        "Polynt-Reichhold": {"sector": "Industrial Manufacturing"},
        "Stroili Oro": {"sector": "Retail & Consumer"},
        "OKA": {"sector": "Retail & Consumer"},
    }

    for entry in entries:
        if entry["name"] in inv_fixes:
            for k, v in inv_fixes[entry["name"]].items():
                entry[k] = v

    fp[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"Investindustrial: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# FUND 4: Bridgepoint
# ============================================================
slug = "bridgepoint"
if slug in fp:
    entries = fp[slug]

    bp_fixes = {
        # NULL sector entries
        "Abion": {"sector": "Professional Services"},
        "ACT": {"sector": "Environmental Services"},
        "Anaveo": {"sector": "Technology"},
        "Axplora": {"sector": "Biotech & Pharma"},
        "Balt": {"sector": "Healthcare"},
        "Chime Software": {"sector": "Software"},
        "Condatis": {"sector": "Software"},
        "Cyrus Conseil": {"sector": "Financial Services"},
        "DataExpert": {"sector": "Technology"},
        "Diagnostiskt Centrum Hud": {"sector": "Healthcare"},
        "EVORIEL": {"sector": "Real Estate"},
        "Exile Group": {"sector": "Media & Entertainment"},
        "Finzzle Groupe": {"sector": "Financial Services"},
        "Forward Global": {"sector": "Professional Services"},
        "Groupe Sinari": {"sector": "Software"},
        "HBC": {"sector": "Retail & Consumer"},
        "Helio Intelligence": {"sector": "Software"},
        "Identicare": {"sector": "Technology"},
        "IDHL": {"sector": "Professional Services"},
        "Interpath": {"sector": "Professional Services"},
        "Kerv Group": {"sector": "Technology"},
        "Market Halls": {"sector": "Hospitality & Tourism"},
        "Matrix": {"sector": "Financial Services"},
        "MiQ": {"sector": "Media & Entertainment"},
        "Moneycorp": {"sector": "Financial Services"},
        "Monica Vinader": {"sector": "Retail & Consumer"},
        "MVF": {"sector": "Media & Entertainment"},
        "MyDefence": {"sector": "Aerospace & Defense"},
        "mydentist": {"sector": "Healthcare"},
        "NMi Group": {"sector": "Professional Services"},
        "Oris Dental": {"sector": "Healthcare"},
        "PDSVISION": {"sector": "Software"},
        "PEI Group": {"sector": "Media & Entertainment"},
        "PharmaReview": {"sector": "Professional Services"},
        "Plug In Digital": {"sector": "Media & Entertainment"},
        "Prescient Healthcare Group": {"sector": "Professional Services"},
        "Safe Life": {"sector": "Industrial Manufacturing"},
        "Samy Alliance": {"sector": "Media & Entertainment"},
        "Schuberg Philis": {"sector": "Technology"},
        "SK AeroSafety Group": {"sector": "Aerospace & Defense"},
        "Surikat": {"sector": "Software"},
        "The Dining Club Group": {"sector": "Hospitality & Tourism"},
        "TicTac": {"sector": "Education"},
        "Windar Renovables": {"sector": "Energy & Utilities"},
        "Zenith": {"sector": "Transportation & Logistics"},
        # Fix existing entries
        "Analysys Mason": {"sector": "Professional Services"},
        "Evac": {"sector": "Environmental Services"},
        "Fera Science": {"sector": "Professional Services"},
        "Qualitest": {"sector": "Technology"},
        "KGH Customs Services": {"sector": "Transportation & Logistics"},
        "Groupe Thom": {"sector": "Retail & Consumer"},
        "Private Sport Shop": {"sector": "Retail & Consumer"},
        "Rovensa": {"sector": "Agriculture"},
    }

    for entry in entries:
        if entry["name"] in bp_fixes:
            for k, v in bp_fixes[entry["name"]].items():
                entry[k] = v

    fp[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"Bridgepoint: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# Write back
# ============================================================
backup_path = PORTFOLIO_PATH + ".bak"
shutil.copy2(PORTFOLIO_PATH, backup_path)
print(f"\nBackup saved to {backup_path}")

with open(PORTFOLIO_PATH, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

with open(PORTFOLIO_PATH, "r") as f:
    json.load(f)
print("JSON validation passed")

# Summary stats
total_null = sum(
    1 for slug_entries in fp.values()
    for e in slug_entries
    if not e.get("sector")
)
total_entries = sum(len(v) for v in fp.values())
print(f"\nOverall: {total_entries} total entries, {total_null} null sectors ({100*total_null/total_entries:.1f}%)")
print("Done!")
