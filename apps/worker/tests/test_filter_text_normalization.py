"""Regression tests for signal text normalization in filter_signals.py."""

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from filter_signals import _clean_signal_fields, _normalize_monetary_values  # noqa: E402


def test_monetary_token_gets_space_before_following_word():
    text = "NANDO raccoglie €3.3Mper rivoluzionare la gestione rifiuti"
    normalized = _normalize_monetary_values(text)
    assert "€3.3M per" in normalized


def test_currency_symbol_not_duplicated_for_milioni_form():
    text = "Aumento di capitale da €120 milioni per Yarpa"
    normalized = _normalize_monetary_values(text)
    assert "€€" not in normalized
    assert "€120M per" in normalized


def test_clean_signal_fields_repairs_unknown_company_concatenation_and_money_connectors():
    signal = {
        "title": "Wise Equity entra nel capitale diMarulloper accompagnarne la crescita",
        "what_changed": "€62 million of capital increase for Philogen",
        "diff_summary": "SIMEST e CDP Venture Capital: €200Magreementfor startup internazionali",
    }
    cleaned = _clean_signal_fields(signal)
    assert "Marullo per" in cleaned["title"]
    assert "€62M of capital" in cleaned["what_changed"]
    assert "€200M agreement for" in cleaned["diff_summary"]


def test_clean_signal_fields_repairs_company_tokens_using_entity_candidates():
    signal = {
        "title": "Alpha Fund signs strategic partnershipwith TechNovaper growth",
        "what_changed": "Nuovo accordo conTechNova per accelerare l'espansione",
        "extracted_entities": {"companies": ["TechNova"]},
    }
    cleaned = _clean_signal_fields(signal)
    assert "partnership with TechNova per growth" in cleaned["title"]
    assert "con TechNova per accelerare" in cleaned["what_changed"]


def test_clean_signal_fields_keeps_tgcom24_token_intact():
    signal = {
        "title": "TGCom24: BFF Bank: apre all'acquisto dei crediti delle PMI verso la PA",
        "what_changed": "New announcement: TGCom24: BFF Bank: apre all'acquisto dei crediti delle PMI verso la PA",
    }
    cleaned = _clean_signal_fields(signal)
    assert "TGCom24" in cleaned["title"]
    assert "TGC om 24" not in cleaned["title"]


def test_clean_signal_fields_does_not_reintroduce_split_name_after_capitalization():
    signal = {
        "title": "Berardi Bullonerie acquires Fastpoint Srl",
        "what_changed": "The deal strengthens operations since HIG’s investment in Berar di.",
        "title_original": "Berardi Bullonerie acquires Fastpoint srl",
        "what_changed_original": "The deal strengthens operations since HIG’s investment in Berar di.",
        "extracted_entities": {"companies": ["Berardi Bullonerie"]},
    }
    cleaned = _clean_signal_fields(signal)
    assert "Berar di" not in cleaned["what_changed"]
    assert "Berardi" in cleaned["what_changed"]


def test_clean_signal_fields_uses_target_companies_for_name_capitalization():
    signal = {
        "title": "Libraesva and cyber guru announce strategic combination",
        "target_companies": [
            {"name": "Libraesva"},
            {"name": "Cyber Guru"},
        ],
    }
    cleaned = _clean_signal_fields(signal)
    assert "Cyber Guru" in cleaned["title"]


def test_clean_signal_fields_normalizes_brand_and_bank_casing_without_entities():
    signal = {
        "title": "teamsystem capital@work and banco bpm launch a new initiative",
        "what_changed": "banco bpm partners with teamsystem for SMEs",
    }
    cleaned = _clean_signal_fields(signal)
    assert "TeamSystem" in cleaned["title"]
    assert "Banco BPM" in cleaned["title"]
    assert "TeamSystem" in cleaned["what_changed"]
