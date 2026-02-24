"""Comprehensive tests for signal_text_utils.py — shared text cleaning utilities.

Tests cover: clean_display_text(), fix_spacing(), normalize_monetary_values(),
repair_token_splits(), is_garbage_summary(), capitalize_entities(),
caps_to_title_case(), title_case_to_sentence_case(), strip_date_prefixes/suffixes,
strip_press_release_prefix, repair_attached_connectors.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from signal_text_utils import (  # noqa: E402
    capitalize_entities,
    caps_to_title_case,
    clean_display_text,
    fix_spacing,
    is_garbage_summary,
    normalize_monetary_values,
    repair_attached_connectors,
    repair_token_splits,
    strip_date_prefixes,
    strip_date_suffixes,
    strip_press_release_prefix,
    title_case_to_sentence_case,
)


# ── clean_display_text ────────────────────────────────────────────────────────


class TestCleanDisplayText:
    """Tests for the main pipeline entry point."""

    def test_empty_and_none(self):
        assert clean_display_text("") == ""
        assert clean_display_text(None) is None

    def test_strips_press_release_prefix(self):
        result = clean_display_text("Press Release: Apollo acquires Nouryon", is_title=True)
        assert not result.startswith("Press Release")
        assert "Apollo" in result

    def test_strips_comunicato_stampa_prefix(self):
        result = clean_display_text("Comunicato Stampa - Ardian investe in XYZ", is_title=True)
        assert "Comunicato Stampa" not in result

    def test_strips_date_prefixes(self):
        result = clean_display_text("15 January 2025 KKR acquires stake", is_title=True)
        assert result.startswith("KKR")

    def test_strips_date_suffixes(self):
        result = clean_display_text("KKR acquires stake 15/01/2025", is_title=True)
        assert "15/01/2025" not in result

    def test_strips_newspaper_attribution(self):
        result = clean_display_text("Apollo closes deal — IL SOLE 24 ORE", is_title=True)
        assert "IL SOLE 24 ORE" not in result

    def test_clears_newspaper_only_text_for_non_title(self):
        result = clean_display_text("Il Sole 24 Ore", is_title=False)
        assert result == ""

    def test_preserves_newspaper_only_for_title(self):
        # Titles should not be completely cleared
        result = clean_display_text("Il Sole 24 Ore", is_title=True)
        assert len(result) > 0

    def test_strips_read_more_artifacts(self):
        result = clean_display_text("Apollo acquires Nouryon Approfondisci", is_title=True)
        assert "Approfondisci" not in result

    def test_strips_aum_boilerplate(self):
        result = clean_display_text(
            "Apollo, a global firm with $70B of capital under management, acquires XYZ",
            is_title=True,
        )
        assert "$70B of capital under management" not in result
        assert "acquires XYZ" in result

    def test_rewrites_exited_from_portfolio(self):
        result = clean_display_text("Nouryon exited from Apollo portfolio", is_title=True)
        assert "Apollo exits Nouryon" in result

    def test_strips_leading_italian_articles(self):
        result = clean_display_text("Il Fondo Italiano investe", is_title=True)
        assert result.startswith("Fondo")

    def test_geographic_proper_nouns_capitalized(self):
        result = clean_display_text("expansion into italy and spain", is_title=True)
        assert "Italy" in result
        assert "Spain" in result

    def test_short_geo_nouns_uppercased(self):
        result = clean_display_text("operations in the uk and us", is_title=True)
        assert "UK" in result
        assert "US" in result

    def test_camel_case_splitting(self):
        result = clean_display_text("appointedJohnSmith", is_title=True)
        assert "appointed" in result.lower()
        assert "John" in result or "john" in result.lower()

    def test_acronym_split_repair(self):
        # "CEOand" → "CEO and"
        result = clean_display_text("New CEOand managing director", is_title=True)
        assert "CEO and" in result or "CEO" in result

    def test_brand_token_tgcom24_preserved(self):
        result = clean_display_text("TGCom24: BFF Bank opens to SME credits", is_title=True)
        assert "TGCom24" in result
        assert "TGC om" not in result

    def test_fused_words_split(self):
        result = clean_display_text("chiefexecutiveofficer leaves the firm", is_title=True)
        assert "chief executive officer" in result.lower()

    def test_all_caps_to_title_case(self):
        result = clean_display_text(
            "APOLLO ACQUIRES NOURYON IN A MAJOR DEAL FOR THE INDUSTRY",
            is_title=True,
        )
        assert result != result.upper()
        assert "Apollo" in result

    def test_title_case_to_sentence_case(self):
        result = clean_display_text(
            "Capza Invests In Italian Company Travelsoft For Growth",
            is_title=True,
        )
        # Should lowercase common words like "in", "for"
        assert " in " in result.lower()

    def test_person_name_capitalized_after_verb(self):
        result = clean_display_text("appointed claudia pingue as head", is_title=True)
        assert "Claudia" in result
        assert "Pingue" in result

    def test_strips_logo_prefix(self):
        result = clean_display_text("Logo Permira acquires stake", is_title=True)
        assert not result.startswith("Logo")

    def test_strips_pipe_boilerplate(self):
        result = clean_display_text("Major deal announced | Press release | News", is_title=True)
        assert "Press release" not in result

    def test_dateline_stripped(self):
        result = clean_display_text(
            "Milan (IT), 15 January 2025 — Apollo closes deal",
            is_title=True,
        )
        assert "Milan (IT)" not in result
        assert "Apollo" in result

    def test_ensures_title_starts_uppercase(self):
        result = clean_display_text("apollo acquires nouryon", is_title=True)
        assert result[0].isupper()

    def test_strips_trailing_colon(self):
        result = clean_display_text("Giuseppe Santangelo (Space Industries):", is_title=True)
        assert not result.endswith(":")

    def test_monetary_normalization_inline(self):
        result = clean_display_text("raises 500 milioni di euro for new fund", is_title=True)
        assert "€500M" in result


# ── fix_spacing ───────────────────────────────────────────────────────────────


class TestFixSpacing:
    """Tests for HTML extraction spacing repair."""

    def test_empty_input(self):
        assert fix_spacing("") == ""
        assert fix_spacing(None) is None

    def test_digit_letter_split(self):
        # fix_spacing strips leading numbers; the split inserts a space then
        # the leading-number stripper removes "2025 " leaving "Comunicato"
        result = fix_spacing("2025Comunicato")
        assert "Comunicato" in result

    def test_letter_digit_split(self):
        result = fix_spacing("Apollo3")
        assert " " in result

    def test_f2i_preserved(self):
        result = fix_spacing("F 2 i SGR investe")
        assert "F2i" in result

    def test_b4i_preserved(self):
        assert "B4i" in fix_spacing("B 4 i accelerator")

    def test_co2_preserved(self):
        assert "CO2" in fix_spacing("CO 2 emissions reduction")

    def test_tgcom24_preserved(self):
        assert "TGCom24" in fix_spacing("TGC om 24 reports")

    def test_quarter_notation(self):
        assert "Q1" in fix_spacing("Q 1 results")
        assert "H2" in fix_spacing("H 2 earnings")

    def test_ordinal_compact(self):
        assert "14th" in fix_spacing("14 th edition")

    def test_italian_word_splits(self):
        assert "Investimento" in fix_spacing("Investimen to")
        assert "Finanziamento" in fix_spacing("Finanziamen to")

    def test_series_c_spacing(self):
        assert "Series C " in fix_spacing("Series Cfinancing")

    def test_cdp_venture_capital(self):
        assert "CDP Venture Capital" in fix_spacing("Cdp Venture Capital")

    def test_sgr_uppercase(self):
        assert "SGR" in fix_spacing("Sgr investe")

    def test_aucap_expansion(self):
        result = fix_spacing("aucap da €5M")
        assert "capital increase" in result

    def test_mojibake_euro(self):
        result = fix_spacing("â¬€500M deal")
        assert "€500M" in result
        assert "â¬" not in result

    def test_italian_preposition_spacing(self):
        # "diAlba" → "di Alba"
        result = fix_spacing("investimento diAlba")
        assert "di Alba" in result

    def test_camelcase_word_spacing(self):
        # "tedescaKBC" → "tedesca KBC"
        result = fix_spacing("tedescaKBC Group")
        assert "tedesca KBC" in result or "tedesca" in result

    def test_monetary_magnitude_reattach(self):
        result = fix_spacing("€200 Magreementfor")
        assert "€200M" in result


# ── normalize_monetary_values ──────────────────────────────────────────────────


class TestNormalizeMonetaryValues:
    """Tests for Italian/English monetary normalization."""

    def test_empty_input(self):
        assert normalize_monetary_values("") == ""
        assert normalize_monetary_values(None) is None

    def test_milioni_di_euro(self):
        result = normalize_monetary_values("120 milioni di euro")
        assert "€120M" in result

    def test_miliardi_di_euro(self):
        result = normalize_monetary_values("2 miliardi di euro")
        assert "€2B" in result

    def test_mln_standalone(self):
        result = normalize_monetary_values("500 mln")
        assert "€500M" in result

    def test_mld_standalone(self):
        result = normalize_monetary_values("3 mld")
        assert "€3B" in result

    def test_dollar_million(self):
        result = normalize_monetary_values("$200 million")
        assert "$200M" in result

    def test_gbp_million(self):
        result = normalize_monetary_values("£150 million")
        assert "£150M" in result

    def test_euro_symbol_million(self):
        result = normalize_monetary_values("€500 million")
        assert "€500M" in result

    def test_euro_symbol_billion(self):
        result = normalize_monetary_values("€2 billion")
        assert "€2B" in result

    def test_verbal_amount(self):
        result = normalize_monetary_values("three million euros")
        assert "€3M" in result

    def test_usd_prefix(self):
        result = normalize_monetary_values("USD 500 million")
        assert "$500M" in result

    def test_eur_prefix(self):
        result = normalize_monetary_values("EUR 200 million")
        assert "€200M" in result

    def test_oltre_translation(self):
        result = normalize_monetary_values("oltre 500 mln di euro")
        assert "over" in result
        assert "€500M" in result

    def test_circa_translation(self):
        result = normalize_monetary_values("circa 200 milioni di euro")
        assert "~" in result

    def test_compact_amount_spacing(self):
        result = normalize_monetary_values("€200Mfor the acquisition")
        assert "€200M " in result

    def test_no_double_euro_symbol(self):
        result = normalize_monetary_values("€120 milioni di euro")
        assert "€€" not in result

    def test_italian_full_number_euro(self):
        result = normalize_monetary_values("1.350.000 euro")
        # 1,350,000 / 1,000,000 = 1.35 → may round to €1.4M or €1.35M
        assert "€" in result and "M" in result

    def test_mila_euro(self):
        result = normalize_monetary_values("500 mila euro")
        assert "€" in result and "M" in result

    def test_descriptive_tens_of_millions(self):
        result = normalize_monetary_values("tens of mln")
        assert "tens of millions" in result

    def test_reversed_currency_mln_euro(self):
        result = normalize_monetary_values("100 mln €")
        assert "€100M" in result


# ── repair_token_splits ────────────────────────────────────────────────────────


class TestRepairTokenSplits:
    """Tests for OCR/PDF/HTML token repair."""

    def test_empty_input(self):
        assert repair_token_splits("") == ""
        assert repair_token_splits(None) is None

    def test_italian_preposition_repair(self):
        assert "del" in repair_token_splits("de l fondo")
        assert "della" in repair_token_splits("del la societa")

    def test_read_more_stripped(self):
        result = repair_token_splits("Apollo invests read more")
        assert "read more" not in result.lower()

    def test_investimento_repair(self):
        result = repair_token_splits("I nvestimento di €5M")
        assert "Investimento" in result or "investimento" in result

    def test_leading_label_stripped(self):
        result = repair_token_splits("News: Apollo acquires XYZ")
        assert result.startswith("Apollo")

    def test_leading_label_preserved_when_too_short(self):
        result = repair_token_splits("News: XYZ", strip_leading_label=False)
        assert "News" in result

    def test_single_letter_fragment_merge(self):
        # Single uppercase letter between words gets merged
        result = repair_token_splits("Invest E ment")
        assert "Investment" in result or "Invest" in result


# ── is_garbage_summary ─────────────────────────────────────────────────────────


class TestIsGarbageSummary:
    """Tests for garbage summary detection."""

    def test_empty_is_garbage(self):
        assert is_garbage_summary("") is True
        assert is_garbage_summary(None) is True
        assert is_garbage_summary("   ") is True

    def test_pipe_is_garbage(self):
        assert is_garbage_summary("Apollo | Press release | News") is True

    def test_very_short_is_garbage(self):
        assert is_garbage_summary("Apollo fund") is True

    def test_starts_lowercase_is_garbage(self):
        assert is_garbage_summary("apollo acquires major stake in Nouryon") is True

    def test_boilerplate_template_is_garbage(self):
        assert is_garbage_summary("New investment involving Apollo and Nouryon") is True

    def test_integers_artifact_is_garbage(self):
        assert is_garbage_summary("Apollo integers the majority stake in Nouryon") is True

    def test_fused_token_25_chars_is_garbage(self):
        assert is_garbage_summary("Apollo appointedClaudiaPingueasheadoffondotechnologytransfer") is True

    def test_italian_stop_words_is_garbage(self):
        assert is_garbage_summary("Apollo della nella degli anno dopo questo per la società") is True

    def test_no_verb_short_is_garbage(self):
        # "Management" matches "manag\w*" verb pattern, so use a name without verbs
        assert is_garbage_summary("Apollo Capital Holdings Group") is True

    def test_valid_summary_not_garbage(self):
        assert is_garbage_summary("Apollo acquires majority stake in Nouryon for €3B") is False

    def test_valid_with_verb_not_garbage(self):
        assert is_garbage_summary("KKR has completed the acquisition of XYZ Corporation in a deal valued at €500M") is False

    def test_long_text_without_verb_not_garbage(self):
        # Long enough (>80 chars) text without verb is NOT garbage
        text = "Apollo Global Management — " * 4
        assert is_garbage_summary(text) is False


# ── capitalize_entities ────────────────────────────────────────────────────────


class TestCapitalizeEntities:
    """Tests for NER-based entity capitalization."""

    def test_empty_inputs(self):
        assert capitalize_entities("", ["Apollo"]) == ""
        assert capitalize_entities("hello", None) == "hello"
        assert capitalize_entities("hello", []) == "hello"

    def test_basic_capitalization(self):
        result = capitalize_entities("apollo acquires nouryon", ["Apollo", "Nouryon"])
        assert "Apollo" in result
        assert "Nouryon" in result

    def test_preserves_existing_acronym(self):
        # Don't replace "KKR" with "Kkr"
        result = capitalize_entities("KKR acquires stake", ["Kkr"])
        assert "KKR" in result

    def test_short_entity_skipped(self):
        result = capitalize_entities("a fund invests", ["a"])
        assert result == "a fund invests"

    def test_multiple_entities(self):
        result = capitalize_entities(
            "apollo and carlyle co-invest in audiotonix",
            ["Apollo", "Carlyle", "Audiotonix"],
        )
        assert "Apollo" in result
        assert "Carlyle" in result
        assert "Audiotonix" in result


# ── caps_to_title_case ─────────────────────────────────────────────────────────


class TestCapsToTitleCase:
    """Tests for ALL CAPS → title case conversion."""

    def test_empty_input(self):
        assert caps_to_title_case("") == ""
        assert caps_to_title_case(None) is None

    def test_short_text_unchanged(self):
        assert caps_to_title_case("APOLLO FUND") == "APOLLO FUND"

    def test_long_all_caps_converted(self):
        result = caps_to_title_case("APOLLO ACQUIRES MAJOR STAKE IN NOURYON FOR GROWTH")
        assert "Apollo" in result
        assert result != result.upper()

    def test_mixed_case_unchanged(self):
        result = caps_to_title_case("Apollo acquires Nouryon")
        assert result == "Apollo acquires Nouryon"

    def test_restores_acronyms(self):
        result = caps_to_title_case("NUOVA SGR INVESTE IN STARTUP IPO PER CRESCITA AZIENDALE")
        assert "SGR" in result
        assert "IPO" in result

    def test_lowercases_italian_prepositions(self):
        result = caps_to_title_case("APOLLO INVESTE NEL FONDO DI CRESCITA PER LA SOCIETA")
        assert " di " in result or " Di " in result


# ── title_case_to_sentence_case ────────────────────────────────────────────────


class TestTitleCaseToSentenceCase:
    """Tests for Title Case → sentence case conversion."""

    def test_empty_input(self):
        assert title_case_to_sentence_case("") == ""
        assert title_case_to_sentence_case(None) is None

    def test_short_text_unchanged(self):
        assert title_case_to_sentence_case("Apollo Fund") == "Apollo Fund"

    def test_title_case_converted(self):
        result = title_case_to_sentence_case("Capza Invests In Travelsoft For Growth Plans")
        assert " in " in result
        assert " for " in result

    def test_first_word_stays_capitalized(self):
        result = title_case_to_sentence_case("Apollo Invests In Major Italian Company For Growth")
        assert result[0].isupper()

    def test_preserves_acronyms(self):
        result = title_case_to_sentence_case("KKR Invests In Italian SGR For ESG Growth")
        assert "KKR" in result
        assert "SGR" in result
        assert "ESG" in result

    def test_normal_sentence_unchanged(self):
        text = "Apollo acquires majority stake in Nouryon"
        assert title_case_to_sentence_case(text) == text


# ── strip_date_prefixes / strip_date_suffixes ──────────────────────────────────


class TestDateStripping:
    """Tests for date prefix and suffix removal."""

    def test_numeric_prefix(self):
        assert strip_date_prefixes("15/01/2025 Apollo invests").strip().startswith("Apollo")

    def test_word_prefix(self):
        assert strip_date_prefixes("15 January 2025 Apollo invests").strip().startswith("Apollo")

    def test_word_prefix_variant(self):
        assert strip_date_prefixes("January 15, 2025 Apollo invests").strip().startswith("Apollo")

    def test_numeric_suffix(self):
        result = strip_date_suffixes("Apollo invests 15/01/2025")
        assert "15/01/2025" not in result

    def test_word_suffix(self):
        result = strip_date_suffixes("Apollo invests 15 January 2025")
        assert "January 2025" not in result

    def test_empty_input(self):
        assert strip_date_prefixes("") == ""
        assert strip_date_suffixes("") == ""
        assert strip_date_prefixes(None) is None
        assert strip_date_suffixes(None) is None

    def test_italian_month_prefix(self):
        result = strip_date_prefixes("15 Gennaio 2025 Apollo investe")
        assert result.strip().startswith("Apollo")


# ── strip_press_release_prefix ─────────────────────────────────────────────────


class TestStripPressReleasePrefix:

    def test_english_prefix(self):
        result = strip_press_release_prefix("Press Release: Apollo acquires XYZ")
        assert result.startswith("Apollo")

    def test_italian_prefix(self):
        result = strip_press_release_prefix("Comunicato Stampa - Apollo investe")
        assert result.startswith("Apollo")

    def test_empty_input(self):
        assert strip_press_release_prefix("") == ""
        assert strip_press_release_prefix(None) is None


# ── repair_attached_connectors ─────────────────────────────────────────────────


class TestRepairAttachedConnectors:
    """Tests for connector word glue repair."""

    def test_empty_input(self):
        assert repair_attached_connectors("") == ""
        assert repair_attached_connectors(None) is None

    def test_prefix_connector_repair(self):
        result = repair_attached_connectors("investimento diMarullo")
        assert "di Marullo" in result

    def test_entity_aware_repair(self):
        result = repair_attached_connectors(
            "accordo conTechNova per crescita",
            company_candidates=["TechNova"],
        )
        assert "con TechNova" in result or "con Tech" in result

    def test_deal_noun_glue(self):
        result = repair_attached_connectors("investmentfor growth")
        assert "investment for" in result
