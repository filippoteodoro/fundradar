#!/usr/bin/env python3
"""Apply Gemini audit corrections for 5 funds to portfolio_items.json."""
import json
import os
import shutil

PORTFOLIO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "derived", "portfolio_items.json")

with open(PORTFOLIO_PATH, "r") as f:
    data = json.load(f)

fund_portfolios = data["fund_portfolios"]

# ============================================================
# FUND 1: Clessidra Private Equity SGR
# ============================================================
slug = "clessidra-sgr"
if slug in fund_portfolios:
    entries = fund_portfolios[slug]

    # Names to REMOVE (duplicates and garbage)
    remove_names = {
        "Prenergy",           # duplicate
        "Elia",               # duplicate of F.lli Elia
        "SGI",                # duplicate of Società Gasdotti Italia
        "Euticals",           # duplicate of Euticals-AMRI
        "Bitolea",            # duplicate of Bitolea S.p.A.
        "Arredo Plast",       # duplicate of ABM Italia
        "DepoBank",           # duplicate of BFF / Depobank
        "Argea",              # duplicate of Argea S.p.A.
        "Impresoft",          # duplicate of Impresoft S.p.A (the correct one)
        "Everton",            # duplicate of Everton S.p.A.
        "Nicoli",             # duplicate of Molino Nicoli
        "Human Company",      # duplicate of Hu Holding
        "Scopri di più",      # garbage (navigation text)
        "Imprespot S.p.A",    # garbage (typo of Impresoft)
    }

    entries = [e for e in entries if e["name"] not in remove_names]

    # Sector and status fixes for kept entries
    fixes = {
        "Hu Holding S.p.A.": {"sector": "Hospitality & Tourism", "status": "current"},
        "Molino Nicoli": {"sector": "Food & Beverage", "status": "current"},
        "Everton S.p.A.": {"sector": "Food & Beverage", "status": "current"},
        "Viabizzuno S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Nexi S.p.A.": {"sector": "Fintech", "status": "exited"},
        "Argea S.p.A.": {"sector": "Food & Beverage", "status": "current"},
        "BFF / Depobank S.p.A.": {"sector": "Financial Services", "status": "exited"},
        "Società Gasdotti Italia S.p.A.": {"sector": "Energy & Utilities", "status": "exited"},
        "Sisal S.p.A.": {"sector": "Media & Entertainment", "status": "exited"},
        "Sirti S.p.A.": {"sector": "Telecommunications", "status": "exited"},
        "Moby S.p.A.": {"sector": "Transportation & Logistics", "status": "exited"},
        "Metalcam S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Giochi Preziosi S.p.A.": {"sector": "Consumer Goods", "status": "exited"},
        "F.lli Elia S.p.A.": {"sector": "Transportation & Logistics", "status": "exited"},
        "ABM Italia S.p.A.": {"sector": "Consumer Goods", "status": "exited"},
        "Bitolea S.p.A. Chimica Ecologica": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Euticals-AMRI": {"sector": "Biotech & Pharma", "status": "exited"},
        "L&S Italia S.p.A.": {"sector": "Industrial Manufacturing", "status": "exited"},
    }

    for entry in entries:
        if entry["name"] in fixes:
            for k, v in fixes[entry["name"]].items():
                entry[k] = v

    # Add Impresoft S.p.A. (correct spelling) if not already present
    impresoft_exists = any(e["name"] == "Impresoft S.p.A." for e in entries)
    if not impresoft_exists:
        entries.append({
            "name": "Impresoft S.p.A.",
            "sector": "Software",
            "status": "current",
            "confidence": 0.9,
            "website": None,
            "description": "Italian software group, acquired by Clessidra 2021.",
            "detail_page_url": None,
            "headquarters": "Milan, Italy",
            "investment_date": "2021-01-01",
            "data_source": "manual"
        })

    fund_portfolios[slug] = entries
    print(f"Clessidra: {len(entries)} entries after cleanup")


# ============================================================
# FUND 2: H.I.G. European Capital Partners Italy
# ============================================================
slug = "h-i-g-capital"
if slug in fund_portfolios:
    entries = fund_portfolios[slug]

    hig_fixes = {
        "A.L.A. (Advanced Logistics for Aerospace)": {"sector": "Aerospace & Defense", "status": "current"},
        "AIRCOM": {"sector": "Telecommunications", "status": "exited"},
        "ALTEO": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Andwis": {"sector": "Construction", "status": "current"},
        "Anvis Group": {"sector": "Automotive", "status": "exited"},
        "ARMetallizing": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Aspire Pharma": {"sector": "Biotech & Pharma", "status": "current"},
        "Avanta Salud": {"sector": "Healthcare", "status": "current"},
        "Aviapartner": {"sector": "Transportation & Logistics", "status": "exited"},
        "Axis CLC": {"sector": "Construction", "status": "current"},
        "Beinbauer Group": {"sector": "Industrial Manufacturing", "status": "current"},
        "Berardi": {"sector": "Industrial Manufacturing", "status": "current"},
        "Brand Addition": {"sector": "Professional Services", "status": "exited"},
        "CONET": {"sector": "Technology", "status": "exited"},
        "Coriant": {"sector": "Telecommunications", "status": "current"},
        "Deenova": {"sector": "Healthcare", "status": "exited"},
        "DGS": {"sector": "Technology", "status": "exited"},
        "Diam International": {"sector": "Industrial Manufacturing", "status": "exited"},
        "DSD": {"sector": "Environmental Services", "status": "exited"},
        "DX Group": {"sector": "Transportation & Logistics", "status": "current"},
        "Ecore": {"sector": "Environmental Services", "status": "exited"},
        "Europa": {"sector": "Insurance", "status": "exited"},
        "Exterior Plus": {"sector": "Media & Entertainment", "status": "exited"},
        "Fibercore": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Fluo Group": {"sector": "Industrial Manufacturing", "status": "current"},
        "FNZ": {"sector": "Fintech", "status": "exited"},
        "Groupe CTI": {"sector": "Industrial Manufacturing", "status": "exited"},
        "H\u2022C\u2022S Group": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Highbourne Group": {"sector": "Industrial Manufacturing", "status": "current"},
        "ICG Group": {"sector": "Telecommunications", "status": "exited"},
        "Infinigate": {"sector": "Technology", "status": "exited"},
        "Interpath": {"sector": "Professional Services", "status": "current"},
        "Kondor": {"sector": "Consumer Goods", "status": "exited"},
        "Losberger": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Maillis Group": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Metalprint": {"sector": "Industrial Manufacturing", "status": "current"},
        "Netexial": {"sector": "Technology", "status": "current"},
        "Office People": {"sector": "Professional Services", "status": "current"},
        "Project Informatica": {"sector": "Technology", "status": "exited"},
        "Protos S.p.A.": {"sector": "Professional Services", "status": "current"},
        "Puerto de Indias": {"sector": "Food & Beverage", "status": "exited"},
        "Royo Group": {"sector": "Industrial Manufacturing", "status": "exited"},
        "SIAT Group": {"sector": "Industrial Manufacturing", "status": "current"},
        "Silentnight Group": {"sector": "Consumer Goods", "status": "current"},
        "SPORTFIVE": {"sector": "Media & Entertainment", "status": "exited"},
        "STH Standard Hidraulica": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Synseal": {"sector": "Industrial Manufacturing", "status": "exited"},
        "Tres60": {"sector": "Media & Entertainment", "status": "exited"},
        "VM Industries": {"sector": "Industrial Manufacturing", "status": "exited"},
        "VNU Media": {"sector": "Media & Entertainment", "status": "exited"},
        "WERU": {"sector": "Industrial Manufacturing", "status": "exited"},
        "WPS": {"sector": "Industrial Manufacturing", "status": "current"},
        "Xtera": {"sector": "Telecommunications", "status": "current"},
        "Zmarta": {"sector": "Fintech", "status": "exited"},
        # Entries with other sectors that need correction
        "7(S) Personal": {"sector": "Professional Services", "status": "exited"},
        "Acqua & Sapone": {"sector": "Retail & Consumer", "status": "current"},
        "Cadica": {"sector": "Fashion & Luxury", "status": "current"},
        "Centros Único": {"sector": "Healthcare", "status": "exited"},
        "Compañía del Tropico": {"sector": "Hospitality & Tourism", "status": "exited"},
        "International Schools of Europe": {"sector": "Education", "status": "exited"},
        "Looping": {"sector": "Hospitality & Tourism", "status": "exited"},
        "Naturalia Tantum": {"sector": "Consumer Goods", "status": "current"},
        "Pinalli": {"sector": "Retail & Consumer", "status": "current"},
        "Quick": {"sector": "Food & Beverage", "status": "current"},
        "Smallsteps": {"sector": "Education", "status": "exited"},
    }

    for entry in entries:
        if entry["name"] in hig_fixes:
            for k, v in hig_fixes[entry["name"]].items():
                entry[k] = v

    fund_portfolios[slug] = entries
    print(f"HIG: {len(entries)} entries, {sum(1 for e in entries if e.get('sector') == 'Professional Services')} still Professional Services")


# ============================================================
# FUND 3: Vertis SGR
# ============================================================
slug = "vertis-sgr"
if slug in fund_portfolios:
    entries = fund_portfolios[slug]

    vertis_fixes = {
        "Titan4": {"sector": "Technology"},
        "Live Story": {"sector": "Software"},
        "Scuter": {"sector": "Transportation & Logistics"},
        "Tuidi": {"sector": "Software"},
        "Xbooks": {"sector": "Software"},
        "Timeflow": {"sector": "Software"},
        "Focoos Ai": {"sector": "Software"},
        "Wellhub": {"sector": "Technology"},
        "Starting Finance": {"sector": "Media & Entertainment"},
        "Ncore Hr": {"sector": "Software"},
        "Coverzen": {"sector": "Fintech"},
        "Deliveristo": {"sector": "E-commerce"},
        "Aindo": {"sector": "Software"},
        "Smallpixels": {"sector": "Software"},
        "Quicklypro": {"sector": "Healthcare"},
        "Skinlabo": {"sector": "Retail & Consumer"},
        "FitPrime": {"sector": "Technology"},
        "Zerynth": {"sector": "Software"},
        "Hexadrive Engineering": {"sector": "Industrial Manufacturing"},
        "Radical Storage Formerly BagBNB": {"sector": "Transportation & Logistics"},
        "Radical Storage": {"sector": "Transportation & Logistics"},
        "Entando": {"sector": "Software"},
        "Sibylla Biotech": {"sector": "Biotech & Pharma"},
        "Often Medical": {"sector": "Healthcare"},
        "Intendime": {"sector": "Technology"},
        "Buzzoole": {"sector": "Technology"},
        "Heaxel": {"sector": "Healthcare"},
        "Vr Media": {"sector": "Technology"},
        "Milkman": {"sector": "Transportation & Logistics"},
        "Credimi": {"sector": "Fintech", "status": "exited"},
        "Cyber Dyne": {"sector": "Software"},
        "Sclak": {"sector": "Technology"},
        "ToothPic": {"sector": "Cybersecurity"},
        "Selematic": {"sector": "Industrial Manufacturing"},
        "Preziosi Food": {"sector": "Food & Beverage"},
        "Giplast Group": {"sector": "Industrial Manufacturing"},
        "Wib": {"sector": "Industrial Manufacturing"},
        "Plugg": {"sector": "Consumer Goods", "status": "exited"},
        "Chef Dovunque": {"sector": "Food & Beverage"},
        "Titano": {"sector": "Technology"},
        "Jusp": {"sector": "Fintech", "status": "exited"},
        "Arav Fashion": {"sector": "Fashion & Luxury"},
        "Fluidotecnica Sanseverino": {"sector": "Industrial Manufacturing"},
        "Cosigen": {"sector": "Energy & Utilities"},
        "Linkpass": {"sector": "Technology", "status": "exited"},
        "Paperlit": {"sector": "Software", "status": "exited"},
        "Vivocha": {"sector": "Software", "status": "exited"},
        "Karalit": {"sector": "Software", "status": "exited"},
        "Derev": {"sector": "Media & Entertainment"},
        "Wisco": {"sector": "Industrial Manufacturing"},
        "Blomming": {"sector": "E-commerce", "status": "exited"},
        "Promoqui": {"sector": "Media & Entertainment", "status": "exited"},
        "Autoxy": {"sector": "Automotive", "status": "exited"},
        "Optimares": {"sector": "Industrial Manufacturing"},
        "Biouniversa": {"sector": "Biotech & Pharma"},
        "Money 360": {"sector": "Fintech", "status": "exited"},
        "Glomeria Therapeutics": {"sector": "Biotech & Pharma"},
        "Personal Factory": {"sector": "Industrial Manufacturing"},
        "Mosaicoon": {"sector": "Media & Entertainment", "status": "exited"},
    }

    for entry in entries:
        if entry["name"] in vertis_fixes:
            for k, v in vertis_fixes[entry["name"]].items():
                entry[k] = v

    fund_portfolios[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"Vertis: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# FUND 4: SEFEA Impact SGR
# ============================================================
slug = "sefea-impact-sgr"
if slug in fund_portfolios:
    # ALL entries are garbage — replace with real portfolio
    fund_portfolios[slug] = [
        {
            "name": "PerMicro",
            "sector": "Financial Services",
            "status": "current",
            "confidence": 0.9,
            "website": "https://www.permicro.it",
            "description": "Leading Italian microcredit institution, major holding of SEFEA Impact.",
            "detail_page_url": None,
            "headquarters": "Turin, Italy",
            "investment_date": None,
            "data_source": "manual"
        },
        {
            "name": "Banca Etica",
            "sector": "Financial Services",
            "status": "current",
            "confidence": 0.85,
            "website": "https://www.bancaetica.it",
            "description": "Italian ethical banking institution, strategic partner of SEFEA.",
            "detail_page_url": None,
            "headquarters": "Padova, Italy",
            "investment_date": None,
            "data_source": "manual"
        },
    ]
    print(f"SEFEA: replaced 15 garbage entries with 2 real companies")


# ============================================================
# FUND 5: Eureka! Venture SGR
# ============================================================
slug = "eureka-venture-sgr"
if slug in fund_portfolios:
    entries = fund_portfolios[slug]

    eureka_fixes = {
        "ALTERECO PULP": {"sector": "Industrial Manufacturing"},
        "ASTRADYNE": {"sector": "Aerospace & Defense"},
        "SPOKI": {"sector": "Software"},
        "RE4REAL": {"sector": "Cleantech"},
        "BENEWTRAL": {"sector": "Cleantech"},
        "3DNEXTECH": {"sector": "Industrial Manufacturing"},
        "INFLEAD": {"sector": "Software"},
        "BeDimensional": {"sector": "Industrial Manufacturing"},
        "Shop Circle": {"sector": "E-commerce"},
        "Bloxy": {"sector": "Education"},
        "Reflex": {"sector": "Technology"},
        "BLENDEE": {"sector": "Software"},
        "PLANCKIAN": {"sector": "Technology"},
        "I-TES": {"sector": "Cleantech"},
        "Beyond Criopura": {"sector": "Cleantech"},
        "ILICO2SEP": {"sector": "Cleantech"},
        "E-CO2SYNT": {"sector": "Cleantech"},
        "Alice": {"sector": "Technology"},
        "Roibox": {"sector": "Software"},
        "Connected Stories": {"sector": "Software"},
        "Novac": {"sector": "Energy & Utilities"},
        "Perovsky": {"sector": "Energy & Utilities"},
        "T-REM3DIE": {"sector": "Healthcare"},
        "ANONYMISED": {"sector": "Software"},
        "SCIBIDS": {"sector": "Software", "status": "exited"},
        "EYE4NIR": {"sector": "Technology"},
        "Aquaseek": {"sector": "Cleantech"},
        "Caracol": {"sector": "Industrial Manufacturing"},
        "ENDOSTART": {"sector": "Healthcare"},
        "INTA Systems": {"sector": "Healthcare"},
        "FLEEP Technologies": {"sector": "Industrial Manufacturing"},
        "Phononic Vibes": {"sector": "Industrial Manufacturing"},
        "WISE": {"sector": "Healthcare"},
        # Fix existing entries with better sectors
        "Mamacrowd": {"sector": "Fintech"},
        "Banca AideXa": {"sector": "Fintech"},
        "BigProfiles": {"sector": "Software"},
    }

    for entry in entries:
        if entry["name"] in eureka_fixes:
            for k, v in eureka_fixes[entry["name"]].items():
                entry[k] = v

    fund_portfolios[slug] = entries
    null_count = sum(1 for e in entries if not e.get("sector"))
    print(f"Eureka: {len(entries)} entries, {null_count} still null sector")


# ============================================================
# Write back
# ============================================================
# Backup first
backup_path = PORTFOLIO_PATH + ".bak"
shutil.copy2(PORTFOLIO_PATH, backup_path)
print(f"Backup saved to {backup_path}")

with open(PORTFOLIO_PATH, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# Validate
with open(PORTFOLIO_PATH, "r") as f:
    json.load(f)
print("JSON validation passed")
print("Done!")
