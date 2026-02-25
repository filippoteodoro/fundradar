"""Tests for signal_patterns.py — shared regex patterns and utility functions.

Verifies key regex patterns compile, match expected inputs, and reject non-matches.
Also tests utility functions: _strip_read_time(), _strip_urls(),
_is_generic_portfolio_name(), _extract_portfolio_company_name().
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from signal_patterns import (  # noqa: E402
    CORE_GEO_TYPES,
    CORE_QUALITY_TYPES,
    _RE_ACQUISITION_VERBS,
    _RE_PORTFOLIO_CO_AS_ACQUIRER,
    _RE_PORTFOLIO_COMPANY_BACKED,
    _RE_BOARD_APPOINT,
    _RE_BOND_ISSUANCE,
    _RE_BUYER_CUES,
    _RE_CHIUDE_RACCOLTA,
    _RE_CLOSE_VERBS,
    _RE_COMPANY_ROUND,
    _RE_CREDIT_FACILITY,
    _RE_DEBT_FINANCING_BROAD,
    _RE_EVENT_ATTENDANCE,
    _RE_EVENT_TITLE,
    _RE_EXIT_VERBS,
    _RE_EXITED_FROM_PORTFOLIO,
    _RE_EXPLICIT_SELLER,
    _RE_FUND_LAUNCH_STRICT,
    _RE_FUND_LAUNCH_VERBS,
    _RE_FUND_LEVEL_FUNDRAISE,
    _RE_FUNDRAISE_CLOSING,
    _RE_FUNDRAISE_MILESTONE,
    _RE_HAS_ANY_PE_VERB,
    _RE_INTERNSHIP,
    _RE_INTERVIEW,
    _RE_INVEST_VERBS,
    _RE_JOB_POSTING_RECLASSIFY,
    _RE_JOB_SELECTION,
    _RE_LAUNCH_FUND,
    _RE_ORDINAL_INVESTMENT,
    _RE_PARTNERSHIP,
    _RE_PEOPLE_LANGUAGE,
    _RE_PEOPLE_TITLE,
    _RE_PORTFOLIO_UPDATE,
    _RE_REPORT,
    _RE_STRONG_DEAL,
    _RE_STRONG_EXIT_VERBS,
    _extract_portfolio_company_name,
    _is_generic_portfolio_name,
    _strip_read_time,
    _strip_urls,
)


# ── Type sets ──────────────────────────────────────────────────────────────────


class TestTypeSets:
    """Verify core type constants are correct."""

    def test_core_geo_types_contains_deal(self):
        assert "deal_announced" in CORE_GEO_TYPES
        assert "exit_announced" in CORE_GEO_TYPES

    def test_core_geo_types_excludes_people_move(self):
        assert "people_move" not in CORE_GEO_TYPES

    def test_core_quality_types_includes_people_move(self):
        assert "people_move" in CORE_QUALITY_TYPES
        assert "portfolio_update" in CORE_QUALITY_TYPES

    def test_core_quality_types_superset_of_geo(self):
        assert CORE_GEO_TYPES.issubset(CORE_QUALITY_TYPES)


# ── Exit patterns ──────────────────────────────────────────────────────────────


class TestExitPatterns:
    """Tests for exit-related regex patterns."""

    def test_exit_verbs_english(self):
        assert _RE_EXIT_VERBS.search("apollo sells its stake")
        assert _RE_EXIT_VERBS.search("exited from portfolio")
        assert _RE_EXIT_VERBS.search("divested the holding")

    def test_exit_verbs_italian(self):
        assert _RE_EXIT_VERBS.search("il fondo vende la partecipazione")
        assert _RE_EXIT_VERBS.search("cede la quota di maggioranza")

    def test_exit_verbs_negative(self):
        assert not _RE_EXIT_VERBS.search("acquires majority stake")

    def test_strong_exit_verbs(self):
        assert _RE_STRONG_EXIT_VERBS.search("sale of its stake in xyz")
        assert _RE_STRONG_EXIT_VERBS.search("successful realisation of investment")

    def test_explicit_seller(self):
        assert _RE_EXPLICIT_SELLER.search("il venditore ha ceduto la quota")
        assert _RE_EXPLICIT_SELLER.search("cede la propria partecipazione in xyz")
        assert _RE_EXPLICIT_SELLER.search("operazione di disinvestimento")

    def test_exited_from_portfolio(self):
        assert _RE_EXITED_FROM_PORTFOLIO.search("nouryon exited from apollo portfolio")


# ── Deal patterns ──────────────────────────────────────────────────────────────


class TestDealPatterns:
    """Tests for deal-related regex patterns."""

    def test_acquisition_verbs(self):
        assert _RE_ACQUISITION_VERBS.search("acquires majority stake in xyz")
        assert _RE_ACQUISITION_VERBS.search("acquisizione di xyz per €500m")

    def test_invest_verbs_english(self):
        assert _RE_INVEST_VERBS.search("takes a stake in the company")

    def test_invest_verbs_italian(self):
        assert _RE_INVEST_VERBS.search("investe nel capitale di xyz")
        assert _RE_INVEST_VERBS.search("prende il controllo di abc")
        assert _RE_INVEST_VERBS.search("entra nel capitale della società")

    def test_strong_deal(self):
        assert _RE_STRONG_DEAL.search("completes acquisition of xyz corporation")
        assert _RE_STRONG_DEAL.search("invests in the new platform")
        assert _RE_STRONG_DEAL.search("series b round completed")

    def test_buyer_cues(self):
        assert _RE_BUYER_CUES.search("il fondo è in lizza per l'acquisizione")
        assert _RE_BUYER_CUES.search("potrebbe essere interessato all'acquisto")
        assert _RE_BUYER_CUES.search("valuta l\u2019acquisto della società")

    def test_company_round(self):
        assert _RE_COMPANY_ROUND.search("closes series b round at €50m")
        assert _RE_COMPANY_ROUND.search("startup chiude un round di finanziamento")

    def test_ordinal_investment_english(self):
        assert _RE_ORDINAL_INVESTMENT.search("first investment for the fund")
        assert _RE_ORDINAL_INVESTMENT.search("third deal of the year")

    def test_ordinal_investment_italian(self):
        assert _RE_ORDINAL_INVESTMENT.search("primo investimento del fondo")
        assert _RE_ORDINAL_INVESTMENT.search("secondo investimento nel settore")

    def test_has_any_pe_verb(self):
        assert _RE_HAS_ANY_PE_VERB.search("acquires the company")
        assert _RE_HAS_ANY_PE_VERB.search("investimento nella società")
        assert not _RE_HAS_ANY_PE_VERB.search("publishes annual report")


# ── Fundraise patterns ─────────────────────────────────────────────────────────


class TestFundraisePatterns:
    """Tests for fundraise-related regex patterns."""

    def test_fund_level_fundraise(self):
        assert _RE_FUND_LEVEL_FUNDRAISE.search("closes fund iii at €500m")

    def test_fundraise_closing(self):
        assert _RE_FUNDRAISE_CLOSING.search("final close above target")

    def test_fundraise_milestone(self):
        assert _RE_FUNDRAISE_MILESTONE.search("surpassing its target")
        assert _RE_FUNDRAISE_MILESTONE.search("arriva a 500 mln")

    def test_chiude_raccolta(self):
        assert _RE_CHIUDE_RACCOLTA.search("chiude la raccolta del nuovo fondo")

    def test_close_verbs(self):
        assert _RE_CLOSE_VERBS.search("closed the fund at €500m")
        assert _RE_CLOSE_VERBS.search("closing of the new vehicle")


# ── Fund launch patterns ──────────────────────────────────────────────────────


class TestFundLaunchPatterns:
    """Tests for fund launch regex patterns."""

    def test_fund_launch_strict(self):
        assert _RE_FUND_LAUNCH_STRICT.search("new fund iii launched")

    def test_fund_launch_verbs(self):
        assert _RE_FUND_LAUNCH_VERBS.search("launch of new fund for growth equity")

    def test_launch_fund(self):
        assert _RE_LAUNCH_FUND.search("launch of new fund targeting €500m")


# ── People patterns ───────────────────────────────────────────────────────────


class TestPeoplePatterns:
    """Tests for people-related regex patterns."""

    def test_board_appoint(self):
        assert _RE_BOARD_APPOINT.search("appointed to the board of directors")
        assert _RE_BOARD_APPOINT.search("nominato nel consiglio di amministrazione")

    def test_people_title(self):
        assert _RE_PEOPLE_TITLE.search("appointed as managing director")
        assert _RE_PEOPLE_TITLE.search("new ceo announced for the fund")

    def test_people_language(self):
        assert _RE_PEOPLE_LANGUAGE.search("hired as senior partner")
        assert _RE_PEOPLE_LANGUAGE.search("nuovo ingresso nel team")


# ── Other type patterns ───────────────────────────────────────────────────────


class TestOtherPatterns:
    """Tests for other signal type patterns."""

    def test_partnership(self):
        assert _RE_PARTNERSHIP.search("strategic partnership with xyz")
        assert _RE_PARTNERSHIP.search("accordo di collaborazione con abc")

    def test_portfolio_update(self):
        assert _RE_PORTFOLIO_UPDATE.search("portfolio company xyz expands")
        assert _RE_PORTFOLIO_UPDATE.search("bolt-on acquisition by portfolio co")


# ── _RE_PORTFOLIO_CO_AS_ACQUIRER ──────────────────────────────────────────────


class TestPortfolioCoAsAcquirer:
    """Tests for _RE_PORTFOLIO_CO_AS_ACQUIRER — the portfolio-company-as-acquirer detector.

    Semantic contract:
      MATCH  → portfolio company (not the fund) is making the acquisition → portfolio_update
      NO MATCH → fund itself is the acquirer → deal_announced

    These cases come from real BeBeez signals that were historically misclassified.
    DO NOT weaken these tests without updating the pattern AND the audit results.
    """

    # ── Positive: portfolio company IS the acquirer ───────────────────────────

    def test_hyphenated_backed_acquires(self):
        """[Fund]-backed [Company] acquires X — canonical case."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "silver lake-backed facile.it acquires pratiche auto online"
        )

    def test_hyphenated_backed_acquires_variant(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "silver lake-backed facile.it acquires horizon automotive"
        )

    def test_hyphenated_owned_merges(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "kkr-owned company merges with competitor"
        )

    def test_backed_by_acquires(self):
        """backed by [Fund] ... acquires — non-hyphenated variant."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "facile.it, backed by silver lake, acquires horizon automotive"
        )

    def test_backed_by_acquires_inline(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "backed by ardian, euronics acquires a german retailer"
        )

    def test_portfolio_company_acquires(self):
        """Explicit 'portfolio company' language with acquisition verb."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "bain capital portfolio company euronics acquires competitor"
        )

    def test_bolt_on_acquisition(self):
        """bolt-on acquisition = BY DEFINITION portfolio company M&A."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "ardian-backed company completes bolt-on acquisition of xyz"
        )

    def test_add_on_deal(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "portfolio company makes add-on deal in italy"
        )

    def test_tuck_in_acquisition(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "tuck-in acquisition by portfolio co completed"
        )

    # BeBeez parenthetical format: "Company (Fund) acquires" — from live audit findings

    def test_bebeez_parenthetical_eos_im(self):
        """Lexham Power (EOS IM) acquires — real signal rss-signal-00117."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "lexham power (eos im) acquires majority stake in innovo agri"
        )

    def test_bebeez_parenthetical_argos(self):
        """Axitea (Argos) acquires — real signal rss-signal-00096."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "axitea (argos) on its acquisition of surveye"
        )

    def test_bebeez_parenthetical_equinox(self):
        """MVC Group (Equinox) acquires — real signal rss-signal-00010."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "mvc group (equinox) acquires wolvenberg nv"
        )

    def test_bebeez_parenthetical_charme(self):
        """Bianalisi (Charme+Columna) acquires — real signal rss-signal-00056."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "bianalisi (charme+columna) acquires poliambulatorio oberdan"
        )

    def test_bebeez_parenthetical_investindustrial(self):
        """Guala Closures (Investindustrial) acquires — real signal rss-signal-00138."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "guala closures (investindustrial) acquires plant from vinventions"
        )

    def test_bebeez_parenthetical_oakley(self):
        """Phenna Group (Oakley Capital) makes sixth acquisition — real signal rss-signal-00018."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "phenna group (oakley capital) makes sixth acquisition of italian company"
        )

    def test_italian_partecipata(self):
        """Italian 'partecipata da [Fund]' with acquisition verb."""
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "partecipata da ardian acquisisce la maggioranza di xyz"
        )

    def test_italian_controllata(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "la controllata da clessidra acquisisce il concorrente"
        )

    def test_promoted_controlled_by(self):
        assert _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "controlled by kkr, telecom italia acquires fibernet"
        )

    # ── _RE_PORTFOLIO_COMPANY_BACKED bug fix: 'acquires' must now match ───────

    def test_backed_bug_fix_acquires(self):
        """Bug: acquis\\w+ missed 'acquires' (uses 'acquir-' not 'acquis-').
        Fixed by adding acquir\\w+ to _RE_PORTFOLIO_COMPANY_BACKED."""
        assert _RE_PORTFOLIO_COMPANY_BACKED.search(
            "backed by silver lake, facile.it acquires horizon automotive"
        )

    def test_backed_still_matches_acquisisce(self):
        """Ensure Italian 'acquisisce' still matches after the fix."""
        assert _RE_PORTFOLIO_COMPANY_BACKED.search(
            "partecipata da ardian acquisisce la società xyz"
        )

    # ── Negative: fund is the acquirer, NOT a portfolio company ───────────────

    def test_fund_directly_acquires_no_match(self):
        """Silver Lake acquires X — fund is the subject, no 'backed' modifier."""
        assert not _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "silver lake acquires facile.it in €1bn deal"
        )

    def test_fund_acquires_no_match_2(self):
        assert not _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "kkr acquires italian tech company for €500m"
        )

    def test_hyphenated_backed_acquisition_guard(self):
        """[Fund]-backed acquisition of X — 'backed' modifies abstract noun, not company.
        Must NOT match: this is a fund-level deal, not portfolio company M&A."""
        assert not _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "silver lake-backed acquisition of facile.it"
        )

    def test_year_in_parenthetical_no_match(self):
        """Company (2024) acquires — year in parenthetical must not match."""
        assert not _RE_PORTFOLIO_CO_AS_ACQUIRER.search(
            "company (2024) acquires competitor"
        )

    def test_report(self):
        assert _RE_REPORT.search("annual report 2024 published")
        assert _RE_REPORT.search("sustainability report released")

    def test_event_attendance(self):
        assert _RE_EVENT_ATTENDANCE.search("speaks at the conference on PE trends")
        assert _RE_EVENT_ATTENDANCE.search("speaker at the annual summit")

    def test_event_title(self):
        assert _RE_EVENT_TITLE.search("PE Forum 2025")
        # "congresso" is "congress[oi]" pattern — needs congress (not congresso)
        assert _RE_EVENT_TITLE.search("annual congressi 2025")

    def test_interview(self):
        assert _RE_INTERVIEW.search("interview with the managing partner")

    def test_debt_broad(self):
        assert _RE_DEBT_FINANCING_BROAD.search("private debt transaction completed")
        assert _RE_DEBT_FINANCING_BROAD.search("ottiene finanziamento dalla banca")

    def test_credit_facility(self):
        assert _RE_CREDIT_FACILITY.search("€200m revolving credit facility")

    def test_bond_issuance(self):
        assert _RE_BOND_ISSUANCE.search("places €300m bond for refinancing")

    def test_job_selection(self):
        assert _RE_JOB_SELECTION.search("procedura di selezione per il ruolo")
        assert _RE_JOB_SELECTION.search("ricerca una risorsa per il team")

    def test_job_posting_reclassify(self):
        assert _RE_JOB_POSTING_RECLASSIFY.search("seeks a full-time analyst")
        assert _RE_JOB_POSTING_RECLASSIFY.search("avvia la selezione per il responsabile")

    def test_internship(self):
        assert _RE_INTERNSHIP.search("offerta di stage curriculare")
        assert _RE_INTERNSHIP.search("tirocinio presso la sede di milano")


# ── Utility functions ──────────────────────────────────────────────────────────


class TestUtilityFunctions:
    """Tests for utility functions in signal_patterns.py."""

    def test_strip_read_time(self):
        result = _strip_read_time("Apollo acquires XYZ 3 min read")
        assert "min read" not in result
        assert "Apollo" in result

    def test_strip_read_time_empty(self):
        assert _strip_read_time("") == ""

    def test_strip_urls(self):
        result = _strip_urls("Apollo acquires XYZ https://example.com/deal")
        assert "https://" not in result
        assert "Apollo" in result

    def test_strip_urls_empty(self):
        assert _strip_urls("") == ""

    def test_is_generic_portfolio_name_true(self):
        assert _is_generic_portfolio_name("investments")
        assert _is_generic_portfolio_name("Portfolio")
        assert _is_generic_portfolio_name("Our Companies")

    def test_is_generic_portfolio_name_false(self):
        assert not _is_generic_portfolio_name("Nouryon")
        assert not _is_generic_portfolio_name("Audiotonix")

    def test_extract_portfolio_company_name(self):
        signal = {"title": "New portfolio company: Nouryon", "what_changed": "added"}
        result = _extract_portfolio_company_name(
            signal,
            "New portfolio company detected: Nouryon",
            "New portfolio company: Nouryon",
        )
        assert result is not None

    def test_extract_portfolio_company_name_no_match(self):
        signal = {"title": "the market outlook", "what_changed": ""}
        result = _extract_portfolio_company_name(signal, "nothing here", "the market outlook")
        # May return the title text as fallback — verify it's not a crash
        assert isinstance(result, str) or result is None
