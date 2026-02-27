"""Tests for portfolio entry validation and cleaning."""

from fundradar_worker.portfolio_validation import (
    clean_portfolio_name,
    is_valid_portfolio_entry,
    validate_and_clean_portfolio,
)


def test_rejects_sentence_like_editorial_titles():
    slug = "stonepeak"
    assert not is_valid_portfolio_entry("Driving connectivity across North America", slug)
    assert not is_valid_portfolio_entry("The backbone of the global supply chain", slug)
    assert not is_valid_portfolio_entry(
        "Mike Dorrell Featured on The Wall Street Skinny Podcast",
        slug,
    )


def test_rejects_concatenated_editorial_tokens():
    slug = "oaktree-capital-management"
    assert not is_valid_portfolio_entry("Oaktreeinsights", slug)
    assert not is_valid_portfolio_entry("Alternativeinvesting", slug)


def test_rejects_generic_single_word_labels():
    slug = "patrizia"
    assert not is_valid_portfolio_entry("Acquisitions", slug)
    assert not is_valid_portfolio_entry("Insights", slug)
    assert not is_valid_portfolio_entry("Podcast", slug)


def test_rejects_generic_italian_portfolio_heading():
    slug = "credem-euromobiliare-private-asset-sgr"
    assert not is_valid_portfolio_entry("Elenco investimenti", slug)


def test_keeps_real_company_names():
    slug = "stonepeak"
    assert is_valid_portfolio_entry("ReliaQuest", slug)
    assert is_valid_portfolio_entry("The New Home Company", slug)
    assert is_valid_portfolio_entry("SK E&S", slug)


def test_validate_and_clean_portfolio_filters_noise_and_cleans_logo_suffix():
    raw = [
        {"name": "CEME logo"},
        {"name": "Acquisitions"},
        {"name": "Driving connectivity across North America"},
    ]
    cleaned = validate_and_clean_portfolio(raw, "stonepeak")
    assert [c["name"] for c in cleaned] == ["CEME"]
    assert clean_portfolio_name("CEME logo") == "CEME"
