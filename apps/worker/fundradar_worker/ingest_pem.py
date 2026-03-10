"""
PEM PDF ingest for Fundradar.

Two-lane processing:
- Lane 1 (text): Use pdfplumber for text-extractable PDFs
- Lane 2 (OCR): Render to PNG and OCR for scanned/image PDFs
"""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import pdfplumber
from .io_utils import safe_json_write
from .paths import PROJECT_ROOT
from .slug_normalizer import get_slug_normalizer

# Optional OCR imports - only needed for scanned PDFs
try:
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class PdfConfig(TypedDict):
    """Configuration for a PEM PDF file."""

    start_page: int  # 1-indexed page number where table starts
    is_scanned: bool  # True if OCR needed, False for text extraction
    max_pages: int  # Number of pages to process (default 4)


# Configuration map: filename -> PdfConfig
# Pages are 1-indexed as they appear in the PDF viewer
PEM_TABLE_START_PAGE: dict[str, PdfConfig] = {
    # OCR lane (scanned/image PDFs)
    "PEM-2000_2001.pdf": {"start_page": 16, "is_scanned": True, "max_pages": 4},
    "PEM_2010.pdf": {"start_page": 22, "is_scanned": True, "max_pages": 4},
    # Text lane (pdfplumber extraction)
    "PEM_2002.pdf": {"start_page": 20, "is_scanned": False, "max_pages": 4},
    "PEM_2003.pdf": {"start_page": 20, "is_scanned": False, "max_pages": 4},
    "PEM_2004.pdf": {"start_page": 20, "is_scanned": False, "max_pages": 4},
    "PEM_2005.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2006.pdf": {"start_page": 24, "is_scanned": False, "max_pages": 4},
    "PEM_2007.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2008.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2009.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2011.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2012.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2013.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2014.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2015.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2016.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2017.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2018.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2019.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "PEM_2020.pdf": {"start_page": 22, "is_scanned": False, "max_pages": 4},
    "Rapporto-PEM_Ita2021.pdf": {"start_page": 20, "is_scanned": False, "max_pages": 4},
    "PEM_2022-Report.pdf": {"start_page": 20, "is_scanned": False, "max_pages": 4},
    "PEM_2023-Deals.pdf": {"start_page": 2, "is_scanned": False, "max_pages": 20},
    "Deals-PEM_2024.pdf": {"start_page": 2, "is_scanned": False, "max_pages": 20},
}


class DealRecord(TypedDict):
    """A deal extracted from PEM PDF."""

    id: str
    target_company: str
    lead_investor: str
    lead_investor_slug: str
    co_investors: list[str] | None
    invested_amount_eur_mln: float | None
    acquired_stake_pct: float | None
    investment_stage: str | None
    deal_origination: str | None
    region: str | None
    sector: str | None
    sector_detail: str | None
    source_file: str
    source_year: int


def infer_year_from_filename(filename: str) -> int | None:
    """Extract year from PEM filename patterns like PEM_2024.pdf or Deals-PEM_2024.pdf"""
    match = re.search(r"(\d{4})", filename)
    if match:
        year = int(match.group(1))
        if 1990 <= year <= 2030:
            return year
    return None


def compute_sha256(filepath: Path) -> str:
    """Compute SHA256 hash of file contents."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def slugify(name: str) -> str:
    """Convert a fund name to a URL-safe slug."""
    # Normalize unicode characters
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    # Lowercase and replace non-alphanumeric with hyphens
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower())
    # Remove leading/trailing hyphens
    name = name.strip("-")
    return name


_SLUG_NORMALIZER = get_slug_normalizer()


def canonicalize_investor_slug(name: str) -> str:
    """Map a PEM investor name to a canonical fund slug if possible."""
    raw_slug = slugify(name)
    result = _SLUG_NORMALIZER.normalize(slug=raw_slug, name=name)
    return result.slug or "unknown"


def parse_amount(value: str | None) -> float | None:
    """Parse invested amount from PEM format (e.g., '6,4' or '800,0' or 'n.a.')."""
    if not value or value.strip().lower() in ("n.a.", "-", ""):
        return None
    # Replace comma with period for decimal
    value = value.replace(",", ".").strip()
    try:
        return float(value)
    except ValueError:
        return None


def parse_stake(value: str | None) -> float | None:
    """Parse acquired stake percentage (e.g., '100%', '>50%', 'n.a.')."""
    if not value or value.strip().lower() in ("n.a.", "-", ""):
        return None
    # Remove % and > symbols
    value = value.replace("%", "").replace(">", "").replace("<", "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def parse_co_investors(value: str | None) -> list[str] | None:
    """Parse co-investors field (comma or semicolon separated, or single '-')."""
    if not value or value.strip() in ("-", ""):
        return None
    # Split by common delimiters
    investors = re.split(r"[,;]", value)
    investors = [inv.strip() for inv in investors if inv.strip() and inv.strip() != "-"]
    return investors if investors else None


def get_cell(row: list, col_map: dict, key: str) -> str | None:
    """Safely get a cell value from a row using column mapping."""
    idx = col_map.get(key)
    if idx is None or idx < 0 or idx >= len(row):
        return None
    return row[idx]


def map_columns_from_header(header: list) -> dict[str, int]:
    """Map column names to indices from a table header row."""
    col_map = {}
    for i, h in enumerate(header):
        h_lower = str(h or "").lower()
        if "target" in h_lower:
            col_map["target"] = i
        elif "lead" in h_lower and "investor" in h_lower:
            col_map["lead_investor"] = i
        elif "investor" in h_lower and "lead" not in h_lower and "co" not in h_lower:
            # Fallback for just "investor" column
            if "lead_investor" not in col_map:
                col_map["lead_investor"] = i
        elif "co-investor" in h_lower or "co investor" in h_lower:
            col_map["co_investors"] = i
        elif "amount" in h_lower or "invested" in h_lower:
            col_map["amount"] = i
        elif "stake" in h_lower:
            col_map["stake"] = i
        elif "stage" in h_lower:
            col_map["stage"] = i
        elif "origination" in h_lower:
            col_map["origination"] = i
        elif "region" in h_lower or "area" in h_lower:
            col_map["region"] = i
        elif "sector" in h_lower and "1" in h_lower:
            col_map["sector"] = i
        elif "sector" in h_lower and ("sic" in h_lower or "detail" in h_lower):
            col_map["sector_detail"] = i
        elif "sector" in h_lower:
            if "sector" not in col_map:
                col_map["sector"] = i
    return col_map


def parse_row_to_deal(
    row: list,
    col_map: dict[str, int],
    deal_id: str,
    source_file: str,
    source_year: int,
) -> DealRecord | None:
    """Parse a table row into a DealRecord."""
    if not row or len(row) < 2:
        return None

    # Get target company
    target_col = col_map.get("target", 0)
    target = str(row[target_col] or "").strip() if target_col < len(row) else ""
    if not target or target.lower() in ("n.a.", "-", "target"):
        return None

    # Get lead investor
    inv_col = col_map.get("lead_investor", 1)
    lead_investor = str(row[inv_col] or "").strip() if inv_col < len(row) else ""
    if not lead_investor or lead_investor.lower() in ("n.a.", "-", "lead investor"):
        lead_investor = "Unknown"

    # Extract fields using helper
    co_inv_cell = get_cell(row, col_map, "co_investors")
    amount_cell = get_cell(row, col_map, "amount")
    stake_cell = get_cell(row, col_map, "stake")
    stage_cell = get_cell(row, col_map, "stage")
    orig_cell = get_cell(row, col_map, "origination")
    region_cell = get_cell(row, col_map, "region")
    sector_cell = get_cell(row, col_map, "sector")
    sector_detail_cell = get_cell(row, col_map, "sector_detail")

    deal: DealRecord = {
        "id": deal_id,
        "target_company": target,
        "lead_investor": lead_investor,
        "lead_investor_slug": canonicalize_investor_slug(lead_investor),
        "co_investors": parse_co_investors(co_inv_cell),
        "invested_amount_eur_mln": parse_amount(amount_cell),
        "acquired_stake_pct": parse_stake(stake_cell),
        "investment_stage": str(stage_cell or "").strip() or None,
        "deal_origination": str(orig_cell or "").strip() or None,
        "region": str(region_cell or "").strip() or None,
        "sector": str(sector_cell or "").strip() or None,
        "sector_detail": str(sector_detail_cell or "").strip() or None,
        "source_file": source_file,
        "source_year": source_year,
    }
    return deal


# =============================================================================
# Lane 1: Text extraction using pdfplumber
# =============================================================================


def extract_deals_text_lane(
    pdf_path: Path,
    source_year: int,
    start_page: int,
    max_pages: int,
) -> list[DealRecord]:
    """
    Extract deals from a text-based PEM PDF using pdfplumber.

    Args:
        pdf_path: Path to the PDF file
        source_year: Year for the source
        start_page: 1-indexed page number where table starts
        max_pages: Number of pages to process

    Returns list of DealRecord dicts.
    """
    deals: list[DealRecord] = []
    source_file = pdf_path.name
    deal_counter = 0

    # Convert to 0-indexed for pdfplumber
    start_idx = start_page - 1
    end_idx = start_idx + max_pages

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx in range(start_idx, min(end_idx, len(pdf.pages))):
            page = pdf.pages[page_idx]
            tables = page.extract_tables()

            if not tables:
                continue

            for table in tables:
                if not table or len(table) < 2:
                    continue

                # First row is header
                header = table[0]
                if not header or len(header) < 2:
                    continue

                # Check for expected column headers
                header_text = " ".join(str(h or "").lower() for h in header)
                if "target" not in header_text and "investor" not in header_text:
                    continue

                col_map = map_columns_from_header(header)

                # Process data rows
                for row in table[1:]:
                    deal_counter += 1
                    deal_id = f"pem-{source_year}-{deal_counter:04d}"
                    deal = parse_row_to_deal(row, col_map, deal_id, source_file, source_year)
                    if deal:
                        deals.append(deal)

    return deals


# =============================================================================
# Lane 2: OCR extraction for scanned/image PDFs
# =============================================================================


def ocr_page_to_text(image: "Image.Image") -> str:
    """Run OCR on a single page image and return text."""
    if not OCR_AVAILABLE:
        raise RuntimeError("OCR dependencies not installed. Run: pip install pytesseract PyMuPDF")
    # Use Italian language for better recognition of Italian text
    text = pytesseract.image_to_string(image, lang="ita+eng")
    return text


def render_pdf_page_to_image(
    pdf_doc: "fitz.Document", page_num: int, dpi: int = 300
) -> "Image.Image":
    """
    Render a PDF page to a PIL Image using PyMuPDF.

    Args:
        pdf_doc: PyMuPDF document object
        page_num: 0-indexed page number
        dpi: Target DPI for rendering (default 300)

    Returns:
        PIL Image of the rendered page
    """
    # PyMuPDF renders at 72 DPI by default, so calculate zoom factor
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    page = pdf_doc[page_num]
    pix = page.get_pixmap(matrix=mat)

    # Convert to PIL Image
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img


def parse_ocr_text_to_rows(text: str) -> list[list[str]]:
    """
    Parse OCR text output into table rows.

    This is a heuristic parser that tries to extract tabular data from OCR output.
    For older PEM reports, columns may be separated by single spaces, so we use
    pattern matching to identify deal-like lines.
    """
    rows = []
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # First try: split on multiple spaces (2+) or tabs
        cells = re.split(r"\s{2,}|\t+", line)
        cells = [c.strip() for c in cells if c.strip()]

        if len(cells) >= 2:
            rows.append(cells)
        else:
            # Second try: parse deal-like lines with pattern matching
            # Look for lines with numeric patterns (amounts like "5,2" or stakes like "64%")
            deal_row = parse_deal_line_heuristic(line)
            if deal_row and len(deal_row) >= 2:
                rows.append(deal_row)

    return rows


def parse_deal_line_heuristic(line: str) -> list[str] | None:
    """
    Parse a line that might be a deal row using heuristics.

    Looks for patterns like: "Company Name Investor Name 5,2 64% ..."
    """
    # Pattern for amount (e.g., "5,2" or "100,0" or "n.a.")
    amount_pattern = r"\d+[,.]\d+"
    # Pattern for stake (e.g., "64%" or ">50%")
    stake_pattern = r"[<>]?\d+%"
    # Pattern for n.a.
    na_pattern = r"n\.a\."

    # Find first numeric value (amount or stake)
    amount_match = re.search(amount_pattern, line)
    stake_match = re.search(stake_pattern, line)
    na_match = re.search(na_pattern, line)

    if not amount_match and not stake_match and not na_match:
        return None

    # Find the earliest numeric indicator
    first_num_pos = len(line)
    if amount_match:
        first_num_pos = min(first_num_pos, amount_match.start())
    if stake_match:
        first_num_pos = min(first_num_pos, stake_match.start())
    if na_match:
        first_num_pos = min(first_num_pos, na_match.start())

    # Text before numeric values likely contains target + investor
    text_before = line[:first_num_pos].strip()

    if not text_before or len(text_before) < 5:
        return None

    # Try to split text_before into target and investor
    words = text_before.split()
    if len(words) < 2:
        return None

    # Heuristic: find transition point between target and investor
    # Known investor suffixes/keywords
    investor_indicators = ["sgr", "capital", "invest", "partners", "fund", "bank", "interbanca"]
    split_idx = None

    # Search from the end backwards to find investor indicators
    for i in range(len(words) - 1, 0, -1):
        word_lower = words[i].lower()
        for indicator in investor_indicators:
            if indicator in word_lower:
                # The investor name likely starts 1-2 words before this
                # Find the first capitalized word before/at this position
                for j in range(max(1, i - 2), i + 1):
                    if j < len(words) and words[j][0].isupper():
                        split_idx = j
                        break
                break
        if split_idx is not None:
            break

    # Fallback: split roughly in the middle if no clear indicator
    # Ensure at least 1 word for target
    if split_idx is None or split_idx < 1:
        split_idx = max(1, len(words) // 2)

    target = " ".join(words[:split_idx])
    investor = " ".join(words[split_idx:])

    if not target or not investor:
        return None

    # Build row: target, investor, then any numeric values
    row = [target, investor]

    # Extract amount if present
    if amount_match:
        row.append(amount_match.group())

    # Extract stake if present
    if stake_match:
        row.append(stake_match.group())

    # If only n.a. was found, add it
    if na_match and not amount_match and not stake_match:
        row.append(na_match.group())

    return row


def extract_deals_ocr_lane(
    pdf_path: Path,
    source_year: int,
    start_page: int,
    max_pages: int,
) -> list[DealRecord]:
    """
    Extract deals from a scanned/image PEM PDF using OCR.

    Uses PyMuPDF (fitz) to render pages to images, then pytesseract for OCR.

    Args:
        pdf_path: Path to the PDF file
        source_year: Year for the source
        start_page: 1-indexed page number where table starts
        max_pages: Number of pages to process

    Returns list of DealRecord dicts.
    """
    if not OCR_AVAILABLE:
        print(f"  WARNING: OCR not available, skipping {pdf_path.name}")
        return []

    deals: list[DealRecord] = []
    source_file = pdf_path.name
    deal_counter = 0

    # Convert to 0-indexed for PyMuPDF
    start_idx = start_page - 1
    end_idx = start_idx + max_pages

    end_page_display = start_page + max_pages - 1
    print(f"  Rendering pages {start_page}-{end_page_display} to images (PyMuPDF)...")

    try:
        pdf_doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  ERROR opening PDF: {e}")
        return []

    col_map: dict[str, int] = {}

    try:
        for page_idx in range(start_idx, min(end_idx, len(pdf_doc))):
            page_num = page_idx + 1  # 1-indexed for display
            print(f"  OCR page {page_num}...")

            try:
                image = render_pdf_page_to_image(pdf_doc, page_idx, dpi=300)
            except Exception as e:
                print(f"    ERROR rendering page {page_num}: {e}")
                continue

            text = ocr_page_to_text(image)
            rows = parse_ocr_text_to_rows(text)

            if not rows:
                continue

            # First row might be header
            first_row = rows[0]
            header_text = " ".join(str(h or "").lower() for h in first_row)

            # If it looks like a header, map columns
            if "target" in header_text or "investor" in header_text:
                col_map = map_columns_from_header(first_row)
                data_rows = rows[1:]
            else:
                # Use previous mapping or default
                if not col_map:
                    # Default mapping for typical PEM table structure
                    col_map = {"target": 0, "lead_investor": 1}
                data_rows = rows

            for row in data_rows:
                deal_counter += 1
                deal_id = f"pem-{source_year}-{deal_counter:04d}"
                deal = parse_row_to_deal(row, col_map, deal_id, source_file, source_year)
                if deal:
                    deals.append(deal)
    finally:
        pdf_doc.close()

    return deals


# =============================================================================
# Unified extraction dispatcher
# =============================================================================


def extract_deals_from_pdf(pdf_path: Path, config: PdfConfig) -> list[DealRecord]:
    """
    Extract deals from a PEM PDF using the appropriate lane.

    Dispatches to either text extraction (pdfplumber) or OCR based on config.
    """
    source_year = infer_year_from_filename(pdf_path.name)
    if not source_year:
        print(f"  WARNING: Could not infer year from {pdf_path.name}")
        source_year = 2000

    if config["is_scanned"]:
        print(f"  Using OCR lane for {pdf_path.name}")
        return extract_deals_ocr_lane(
            pdf_path,
            source_year,
            config["start_page"],
            config["max_pages"],
        )
    else:
        print(f"  Using text lane for {pdf_path.name}")
        return extract_deals_text_lane(
            pdf_path,
            source_year,
            config["start_page"],
            config["max_pages"],
        )


def extract_unique_investors(deals: list[DealRecord]) -> list[dict]:
    """Extract unique investors from deals list."""
    investors: dict[str, dict] = {}

    for deal in deals:
        slug = deal["lead_investor_slug"]
        if slug and slug != "unknown":
            if slug not in investors:
                investors[slug] = {
                    "slug": slug,
                    "name": deal["lead_investor"],
                    "deal_count": 0,
                    "first_seen_year": deal["source_year"],
                }
            investors[slug]["deal_count"] += 1
            if deal["source_year"] < investors[slug]["first_seen_year"]:
                investors[slug]["first_seen_year"] = deal["source_year"]

        # Also process co-investors
        if deal["co_investors"]:
            for co_inv in deal["co_investors"]:
                co_slug = canonicalize_investor_slug(co_inv)
                if co_slug and co_slug != "unknown":
                    if co_slug not in investors:
                        investors[co_slug] = {
                            "slug": co_slug,
                            "name": co_inv,
                            "deal_count": 0,
                            "first_seen_year": deal["source_year"],
                        }
                    investors[co_slug]["deal_count"] += 1

    return sorted(investors.values(), key=lambda x: (-x["deal_count"], x["name"]))


def generate_pem_manifest(pem_dir: Path, output_dir: Path) -> dict:
    """
    Scan PEM directory for PDFs and generate a manifest.

    Returns manifest dict with entries for each PDF file.
    """
    entries = []

    if not pem_dir.exists():
        raise FileNotFoundError(f"PEM directory not found: {pem_dir}")

    pdf_files = sorted(pem_dir.glob("*.pdf"))

    for pdf_path in pdf_files:
        config = PEM_TABLE_START_PAGE.get(pdf_path.name)
        entry = {
            "filename": pdf_path.name,
            "year_inferred": infer_year_from_filename(pdf_path.name),
            "sha256": compute_sha256(pdf_path),
            "path": str(pdf_path.relative_to(pem_dir.parent.parent)),
            "has_config": config is not None,
            "is_scanned": config["is_scanned"] if config else None,
            "start_page": config["start_page"] if config else None,
        }
        entries.append(entry)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write manifest
    manifest_path = output_dir / "pem_manifest.json"
    safe_json_write(manifest_path, manifest)

    print(f"Generated manifest with {len(entries)} PDF files")
    print(f"Manifest written to: {manifest_path}")

    return manifest


def parse_all_pdfs(pem_dir: Path, output_dir: Path, manifest: dict) -> tuple[list, list]:
    """
    Parse all PDFs with configuration entries.

    Uses two-lane processing: text for most PDFs, OCR for scanned ones.

    Returns (deals, investors) tuple.
    """
    all_deals: list[DealRecord] = []

    # Find PDFs with configuration
    configured_pdfs = [e for e in manifest["entries"] if e["has_config"]]

    if not configured_pdfs:
        print("No configured PDFs found to parse")
        return [], []

    print(f"\nParsing {len(configured_pdfs)} configured PDF(s)...")

    # Separate by lane for reporting
    text_count = sum(1 for e in configured_pdfs if not e["is_scanned"])
    ocr_count = sum(1 for e in configured_pdfs if e["is_scanned"])
    print(f"  Text lane: {text_count} PDFs")
    print(f"  OCR lane: {ocr_count} PDFs")

    for entry in configured_pdfs:
        pdf_path = pem_dir.parent.parent / entry["path"]
        config = PEM_TABLE_START_PAGE[entry["filename"]]

        print(f"\nProcessing {entry['filename']} (year: {entry['year_inferred']})...")

        try:
            deals = extract_deals_from_pdf(pdf_path, config)
            print(f"  Found {len(deals)} deals")
            all_deals.extend(deals)
        except Exception as e:
            print(f"  ERROR: {e}")

    # Extract unique investors
    investors = extract_unique_investors(all_deals)

    # Write outputs
    output_dir.mkdir(parents=True, exist_ok=True)

    deals_path = output_dir / "pem_deals.json"
    safe_json_write(deals_path, {"generated_at": datetime.now(timezone.utc).isoformat(), "deals": all_deals})
    print(f"\nDeals written to: {deals_path}")

    investors_path = output_dir / "pem_investors.json"
    safe_json_write(investors_path, {"generated_at": datetime.now(timezone.utc).isoformat(), "investors": investors})
    print(f"Investors written to: {investors_path}")

    return all_deals, investors


def main():
    """Entry point for the PEM ingest script."""
    pem_dir = PROJECT_ROOT / "data" / "pem"
    output_dir = PROJECT_ROOT / "data" / "derived"

    print("Fundradar PEM Ingest - Two-Lane Processing")
    print("=" * 50)

    if not OCR_AVAILABLE:
        print("WARNING: OCR dependencies not available. Scanned PDFs will be skipped.")
        print("To enable OCR, install: pip install pytesseract PyMuPDF Pillow")
        print("Also ensure Tesseract is installed on your system (brew install tesseract).")
        print()

    try:
        # Step 1: Generate manifest
        manifest = generate_pem_manifest(pem_dir, output_dir)
        print(f"\nPDF files found: {len(manifest['entries'])}")
        for entry in manifest["entries"]:
            year_str = str(entry["year_inferred"]) if entry["year_inferred"] else "unknown"
            config_str = "configured" if entry["has_config"] else "no config"
            if entry.get("is_scanned"):
                lane_str = "(OCR)"
            elif entry["has_config"]:
                lane_str = "(text)"
            else:
                lane_str = ""
            print(f"  - {entry['filename']} (year: {year_str}, {config_str} {lane_str})")

        # Step 2: Parse all configured PDFs
        deals, investors = parse_all_pdfs(pem_dir, output_dir, manifest)
        print("\n" + "=" * 50)
        print("Summary:")
        print(f"  Total deals extracted: {len(deals)}")
        print(f"  Unique investors found: {len(investors)}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
