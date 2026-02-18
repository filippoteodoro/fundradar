"""Tests for PEM ingest module.

These tests verify parsing logic without requiring actual PDF files.
"""

from fundradar_worker.ingest_pem import (
    PEM_TABLE_START_PAGE,
    infer_year_from_filename,
    map_columns_from_header,
    parse_amount,
    parse_co_investors,
    parse_deal_line_heuristic,
    parse_ocr_text_to_rows,
    parse_row_to_deal,
    parse_stake,
    slugify,
)


class TestInferYearFromFilename:
    """Test year extraction from PEM filenames."""

    def test_standard_pem_format(self):
        """Standard PEM_YYYY.pdf format should extract year."""
        assert infer_year_from_filename("PEM_2024.pdf") == 2024
        assert infer_year_from_filename("PEM_2023.pdf") == 2023
        assert infer_year_from_filename("PEM_2000.pdf") == 2000

    def test_deals_pem_format(self):
        """Deals-PEM_YYYY.pdf format should extract year."""
        assert infer_year_from_filename("Deals-PEM_2024.pdf") == 2024

    def test_range_format(self):
        """Range formats like PEM-2000_2001.pdf should extract first year."""
        # Extracts first 4-digit number found
        assert infer_year_from_filename("PEM-2000_2001.pdf") == 2000

    def test_rapporto_format(self):
        """Rapporto-PEM_YYYY.pdf format should extract year."""
        assert infer_year_from_filename("Rapporto-PEM_2024-1.pdf") == 2024
        assert infer_year_from_filename("Rapporto-PEM_Ita2021.pdf") == 2021

    def test_no_year_returns_none(self):
        """Filenames without a valid year return None."""
        assert infer_year_from_filename("readme.pdf") is None
        assert infer_year_from_filename("notes.txt") is None

    def test_invalid_year_returns_none(self):
        """Years outside valid range (1990-2030) return None."""
        assert infer_year_from_filename("PEM_1980.pdf") is None
        assert infer_year_from_filename("PEM_2050.pdf") is None


class TestSlugify:
    """Test slug generation from fund names."""

    def test_basic_name(self):
        """Simple names become lowercase with hyphens."""
        assert slugify("Investindustrial") == "investindustrial"
        assert slugify("Xenon Private Equity") == "xenon-private-equity"

    def test_with_special_chars(self):
        """Special characters are removed."""
        assert slugify("Fondo Italiano d'Investimento SGR") == "fondo-italiano-d-investimento-sgr"
        assert slugify("DeA Capital") == "dea-capital"

    def test_with_accents(self):
        """Accented characters are normalized."""
        assert slugify("Società Gestione") == "societa-gestione"

    def test_removes_extra_hyphens(self):
        """Multiple separators become single hyphens."""
        assert slugify("Some - Fund - Name") == "some-fund-name"


class TestParseAmount:
    """Test parsing of invested amounts."""

    def test_european_format(self):
        """European decimal format (comma) is parsed correctly."""
        assert parse_amount("6,4") == 6.4
        assert parse_amount("800,0") == 800.0
        assert parse_amount("1,5") == 1.5

    def test_na_values(self):
        """N/A values return None."""
        assert parse_amount("n.a.") is None
        assert parse_amount("N.A.") is None
        assert parse_amount("-") is None
        assert parse_amount("") is None
        assert parse_amount(None) is None


class TestParseStake:
    """Test parsing of acquired stake percentages."""

    def test_with_percent_sign(self):
        """Percentage values are parsed correctly."""
        assert parse_stake("100%") == 100.0
        assert parse_stake("49%") == 49.0

    def test_with_greater_than(self):
        """Greater-than values remove the symbol."""
        assert parse_stake(">50%") == 50.0

    def test_na_values(self):
        """N/A values return None."""
        assert parse_stake("n.a.") is None
        assert parse_stake("-") is None
        assert parse_stake(None) is None


class TestParseCoInvestors:
    """Test parsing of co-investors field."""

    def test_single_investor(self):
        """Single co-investor is returned as list."""
        assert parse_co_investors("Energred") == ["Energred"]

    def test_comma_separated(self):
        """Comma-separated investors are split."""
        result = parse_co_investors("Fund A, Fund B")
        assert result == ["Fund A", "Fund B"]

    def test_dash_means_none(self):
        """Dash means no co-investors."""
        assert parse_co_investors("-") is None
        assert parse_co_investors("") is None
        assert parse_co_investors(None) is None


class TestConfigMap:
    """Test the PEM_TABLE_START_PAGE configuration map."""

    def test_config_map_has_entries(self):
        """Config map should have entries for all known PDFs."""
        assert len(PEM_TABLE_START_PAGE) >= 20
        assert "Deals-PEM_2024.pdf" in PEM_TABLE_START_PAGE
        assert "PEM-2000_2001.pdf" in PEM_TABLE_START_PAGE

    def test_config_entries_have_required_fields(self):
        """Each config entry should have start_page, is_scanned, and max_pages."""
        for filename, config in PEM_TABLE_START_PAGE.items():
            assert "start_page" in config, f"{filename} missing start_page"
            assert "is_scanned" in config, f"{filename} missing is_scanned"
            assert "max_pages" in config, f"{filename} missing max_pages"
            assert isinstance(config["start_page"], int)
            assert isinstance(config["is_scanned"], bool)
            assert isinstance(config["max_pages"], int)
            assert config["start_page"] >= 1
            assert config["max_pages"] >= 1

    def test_scanned_pdfs_identified(self):
        """Only PEM-2000_2001 and PEM_2010 should be marked as scanned."""
        scanned = [f for f, c in PEM_TABLE_START_PAGE.items() if c["is_scanned"]]
        assert set(scanned) == {"PEM-2000_2001.pdf", "PEM_2010.pdf"}

    def test_deals_pdfs_have_more_pages(self):
        """Deals-specific PDFs should have more pages configured."""
        assert PEM_TABLE_START_PAGE["Deals-PEM_2024.pdf"]["max_pages"] > 4
        assert PEM_TABLE_START_PAGE["PEM_2023-Deals.pdf"]["max_pages"] > 4


class TestMapColumnsFromHeader:
    """Test column header mapping."""

    def test_standard_header(self):
        """Standard PEM header should map correctly."""
        header = ["Target", "Lead Investor", "Co-Investor", "Amount", "Stake %", "Region"]
        col_map = map_columns_from_header(header)
        assert col_map["target"] == 0
        assert col_map["lead_investor"] == 1
        assert col_map["co_investors"] == 2
        assert col_map["amount"] == 3
        assert col_map["stake"] == 4
        assert col_map["region"] == 5

    def test_partial_header(self):
        """Partial headers should map available columns."""
        header = ["Target Company", "Investor"]
        col_map = map_columns_from_header(header)
        assert col_map["target"] == 0
        assert col_map["lead_investor"] == 1

    def test_alternative_column_names(self):
        """Alternative column names should be recognized."""
        header = ["Target", "Lead Investor", "Invested Amount", "Acquired Stake", "Area"]
        col_map = map_columns_from_header(header)
        assert "amount" in col_map
        assert "stake" in col_map
        assert "region" in col_map  # "Area" maps to region


class TestParseRowToDeal:
    """Test row parsing to DealRecord."""

    def test_basic_row(self):
        """Basic row with target and investor parses correctly."""
        col_map = {"target": 0, "lead_investor": 1}
        row = ["Acme Corp", "BigFund Capital"]
        deal = parse_row_to_deal(row, col_map, "pem-2024-0001", "test.pdf", 2024)

        assert deal is not None
        assert deal["id"] == "pem-2024-0001"
        assert deal["target_company"] == "Acme Corp"
        assert deal["lead_investor"] == "BigFund Capital"
        # Fictitious investor not in db.json → normalizer returns "unknown"
        assert deal["lead_investor_slug"] == "unknown"
        assert deal["source_file"] == "test.pdf"
        assert deal["source_year"] == 2024

    def test_full_row(self):
        """Full row with all fields parses correctly."""
        col_map = {
            "target": 0,
            "lead_investor": 1,
            "co_investors": 2,
            "amount": 3,
            "stake": 4,
            "region": 5,
            "sector": 6,
        }
        row = ["TechCo", "VentureFund", "Angel1, Angel2", "15,5", "30%", "Lombardia", "Tech"]
        deal = parse_row_to_deal(row, col_map, "pem-2024-0002", "test.pdf", 2024)

        assert deal is not None
        assert deal["co_investors"] == ["Angel1", "Angel2"]
        assert deal["invested_amount_eur_mln"] == 15.5
        assert deal["acquired_stake_pct"] == 30.0
        assert deal["region"] == "Lombardia"
        assert deal["sector"] == "Tech"

    def test_empty_row_returns_none(self):
        """Empty rows should return None."""
        col_map = {"target": 0, "lead_investor": 1}
        assert parse_row_to_deal([], col_map, "id", "file", 2024) is None
        assert parse_row_to_deal([""], col_map, "id", "file", 2024) is None

    def test_header_row_returns_none(self):
        """Rows that look like headers should return None."""
        col_map = {"target": 0, "lead_investor": 1}
        row = ["Target", "Lead Investor"]
        assert parse_row_to_deal(row, col_map, "id", "file", 2024) is None

    def test_unknown_investor_fallback(self):
        """Missing investor should fall back to Unknown."""
        col_map = {"target": 0, "lead_investor": 1}
        row = ["SomeCorp", "-"]
        deal = parse_row_to_deal(row, col_map, "id", "file", 2024)
        assert deal is not None
        assert deal["lead_investor"] == "Unknown"


class TestParseDealLineHeuristic:
    """Test heuristic parsing of deal lines from OCR output."""

    def test_line_with_amount_and_stake(self):
        """Lines with numeric patterns should be parsed."""
        line = "Agorà Telematica Albatros Tech Investments 5,2 64%"
        result = parse_deal_line_heuristic(line)
        assert result is not None
        assert len(result) >= 2
        # Should extract target, investor, amount, stake
        assert "5,2" in result
        assert "64%" in result

    def test_line_with_investor_indicator(self):
        """Lines with known investor indicators should split correctly."""
        line = "Campari UBS Capital 100,0 15%"
        result = parse_deal_line_heuristic(line)
        assert result is not None
        assert len(result) >= 2
        # UBS Capital should be identified as investor
        assert "100,0" in result
        assert "15%" in result

    def test_line_without_numerics_returns_none(self):
        """Lines without numeric patterns should return None."""
        line = "Just some text without numbers"
        result = parse_deal_line_heuristic(line)
        assert result is None

    def test_short_line_returns_none(self):
        """Very short lines should return None."""
        line = "Ab 5,2"
        result = parse_deal_line_heuristic(line)
        assert result is None

    def test_line_with_na_values(self):
        """Lines with n.a. values should be parsed."""
        line = "SomeCompany SomeInvestor n.a. n.a."
        result = parse_deal_line_heuristic(line)
        assert result is not None
        assert "n.a." in result


class TestParseOcrTextToRows:
    """Test OCR text parsing into table rows."""

    def test_space_separated_columns(self):
        """Columns separated by multiple spaces should be split."""
        text = "Acme Corp    BigFund Capital    15,5\nTechCo    VentureFund    20,0"
        rows = parse_ocr_text_to_rows(text)
        assert len(rows) == 2
        assert rows[0] == ["Acme Corp", "BigFund Capital", "15,5"]
        assert rows[1] == ["TechCo", "VentureFund", "20,0"]

    def test_tab_separated_columns(self):
        """Tab-separated columns should be split."""
        text = "Acme Corp\tBigFund\t15,5"
        rows = parse_ocr_text_to_rows(text)
        assert len(rows) == 1
        assert rows[0] == ["Acme Corp", "BigFund", "15,5"]

    def test_empty_lines_skipped(self):
        """Empty lines should be skipped."""
        text = "Line 1    Col 2\n\n\nLine 2    Col 2"
        rows = parse_ocr_text_to_rows(text)
        assert len(rows) == 2

    def test_single_word_lines_use_heuristic(self):
        """Lines that don't split well may use heuristic parsing."""
        # This line has single spaces but contains deal-like data
        text = "SomeCompany SomeInvestor 10,5 50%"
        rows = parse_ocr_text_to_rows(text)
        # Should be parsed by heuristic since it has numeric patterns
        assert len(rows) >= 1

    def test_whitespace_stripped(self):
        """Whitespace should be stripped from cells."""
        text = "  Acme Corp     BigFund Capital  "
        rows = parse_ocr_text_to_rows(text)
        assert rows[0] == ["Acme Corp", "BigFund Capital"]


class TestNoContextLeak:
    """Verify tests don't require PDF context."""

    def test_no_pdf_imports_in_tests(self):
        """Tests should not import PDF processing modules that require files."""
        # This test verifies we're testing parsing logic, not PDF reading
        # The functions we import only deal with strings and dicts
        from fundradar_worker.ingest_pem import (
            infer_year_from_filename,
            map_columns_from_header,
            parse_amount,
            parse_co_investors,
            parse_deal_line_heuristic,
            parse_ocr_text_to_rows,
            parse_row_to_deal,
            parse_stake,
            slugify,
        )

        # All these functions work with simple Python types, not PDF objects
        assert callable(infer_year_from_filename)
        assert callable(slugify)
        assert callable(parse_amount)
        assert callable(parse_stake)
        assert callable(parse_co_investors)
        assert callable(map_columns_from_header)
        assert callable(parse_row_to_deal)
        assert callable(parse_ocr_text_to_rows)
        assert callable(parse_deal_line_heuristic)
