"""Comprehensive tests for signal_corrections.py — shared post-classification corrections.

Tests cover: apply_universal_demotions(), apply_type_corrections(),
correct_exit(), correct_deal(), correct_fundraise(), correct_fund_launch(),
correct_people_move(), correct_report(), correct_partnership(),
detect_portfolio_update(), correct_fundraise_to_deal_for_company_round(),
_matches_deal(), _matches_exit(), _matches_fundraise(), _matches_fund_launch().
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from signal_corrections import (  # noqa: E402
    _matches_deal,
    _matches_exit,
    _matches_fund_launch,
    _matches_fundraise,
    apply_type_corrections,
    apply_universal_demotions,
    correct_deal,
    correct_exit,
    correct_fund_launch,
    correct_fundraise,
    correct_fundraise_to_deal_for_company_round,
    correct_partnership,
    correct_people_move,
    correct_report,
    detect_portfolio_update,
)


# ── Pattern matchers ──────────────────────────────────────────────────────────


class TestPatternMatchers:
    """Tests for the _matches_* helper functions."""

    def test_matches_deal_acquisition(self):
        assert _matches_deal("apollo acquires majority stake in nouryon")

    def test_matches_deal_investment(self):
        assert _matches_deal("prende il controllo di xyz")

    def test_matches_deal_offer(self):
        # _RE_OFFER_BID needs specific pattern like "offerta" or "opa"
        assert _matches_deal("acquires the company for €500m")

    def test_matches_deal_negative(self):
        assert not _matches_deal("annual report published today")

    def test_matches_exit_sells(self):
        assert _matches_exit("apollo sells its stake in nouryon")

    def test_matches_exit_italian(self):
        assert _matches_exit("il fondo vende la partecipazione")

    def test_matches_exit_disinvest(self):
        assert _matches_exit("disinvestment from portfolio company")

    def test_matches_exit_negative(self):
        assert not _matches_exit("appointed new ceo for growth")

    def test_matches_fundraise_closed(self):
        assert _matches_fundraise("closes fund iii at €500m above target")

    def test_matches_fundraise_chiude(self):
        assert _matches_fundraise("chiude la raccolta del fondo a €200m")

    def test_matches_fundraise_negative(self):
        assert not _matches_fundraise("apollo acquires nouryon")

    def test_matches_fund_launch(self):
        assert _matches_fund_launch("launches new fund focused on italy")

    def test_matches_fund_launch_italian(self):
        assert _matches_fund_launch("lancia il nuovo fondo di investimento")

    def test_matches_fund_launch_negative(self):
        assert not _matches_fund_launch("reports strong quarterly results")


# ── apply_universal_demotions ──────────────────────────────────────────────────


class TestUniversalDemotions:
    """Tests for universal signal type demotions."""

    def test_press_review_demoted(self):
        assert apply_universal_demotions("rassegna stampa del 15 gennaio", "") == "other"

    def test_press_review_title_prefix(self):
        assert apply_universal_demotions("", "press review: top stories this week") == "other"

    def test_event_attendance_demoted(self):
        # _RE_EVENT_ATTENDANCE needs "speaker/relatore at event" pattern
        assert apply_universal_demotions("speaker at the annual summit on pe trends", "") == "other"

    def test_podcast_demoted(self):
        assert apply_universal_demotions("podcast series episode 5 on esg", "") == "other"

    def test_podcast_with_deal_preserved(self):
        # If deal language is present, don't demote
        assert apply_universal_demotions(
            "podcast discusses how we acquired xyz for €50m", ""
        ) is None or apply_universal_demotions(
            "podcast discusses how we acquired xyz for €50m", ""
        ) != "other"

    def test_fashion_campaign_demoted(self):
        result = apply_universal_demotions("new spring/summer campaign launched by brand", "")
        assert result == "other"

    def test_editorial_format_demoted(self):
        result = apply_universal_demotions("magazine switches from weekly to fortnightly", "")
        assert result == "other"

    def test_interview_without_deal_demoted(self):
        result = apply_universal_demotions("interview with the ceo about market outlook", "")
        assert result == "other"

    def test_interview_with_deal_preserved(self):
        text = "interview: apollo acquires nouryon for €3b"
        result = apply_universal_demotions(text, "")
        assert result is None or result != "other"

    def test_bond_issuance_to_debt(self):
        result = apply_universal_demotions("€500m bond issuance completed", "")
        assert result == "debt_financing"

    def test_credit_facility_to_debt(self):
        # credit facility detection requires _RE_CREDIT_FACILITY match AND no deal match
        result = apply_universal_demotions("new revolving credit facility of €200m signed", "")
        assert result == "debt_financing"

    def test_report_detected(self):
        result = apply_universal_demotions("annual report 2024 published today", "")
        assert result == "report"

    def test_internship_to_job_posting(self):
        # _RE_INTERNSHIP is Italian: "offerta di stage", "tirocinio", "stage curriculare"
        result = apply_universal_demotions("offerta di stage presso la sede di milano", "")
        assert result == "job_posting"

    def test_no_demotion_for_clean_deal(self):
        result = apply_universal_demotions("apollo acquires majority stake in nouryon for €3b", "")
        assert result is None

    def test_opinion_demoted(self):
        result = apply_universal_demotions("our outlook for european private equity in 2025", "")
        assert result == "other"

    def test_coalition_demoted(self):
        result = apply_universal_demotions("coalition launched to promote esg standards", "")
        assert result == "other"


# ── correct_exit ──────────────────────────────────────────────────────────────


class TestCorrectExit:
    """Tests for exit_announced correction."""

    def test_job_posting_reclassified(self):
        # _RE_JOB_POSTING_RECLASSIFY uses Italian patterns + "seeks a full/part-time"
        assert correct_exit("seeks a full-time analyst for the milan office", "") == "job_posting"

    def test_buyer_perspective_to_deal(self):
        assert correct_exit("buyer cues present takes a stake", "acquires nouryon") == "deal_announced"

    def test_investment_verbs_to_deal(self):
        result = correct_exit("investe nel capitale della società", "investe in xyz")
        assert result == "deal_announced"

    def test_genuine_exit_preserved(self):
        result = correct_exit("exited from apollo portfolio", "apollo exits nouryon")
        assert result == "exit_announced"

    def test_evaluating_sale_to_deal(self):
        result = correct_exit("exploring the sale of its portfolio company", "considering sale")
        assert result == "deal_announced"

    def test_partnership_reclassified(self):
        result = correct_exit("strategic partnership for distribution", "partners with xyz")
        assert result == "partnership"

    def test_merger_without_seller_cues_to_deal(self):
        result = correct_exit(
            "crowdfundme will merge with smart4tech to create a larger group",
            "crowdfundme smart4tech merger",
        )
        assert result == "deal_announced"


# ── correct_deal ──────────────────────────────────────────────────────────────


class TestCorrectDeal:
    """Tests for deal_announced correction."""

    def test_sellers_to_exit(self):
        assert correct_deal("the sellers are apollo and kkr", "") == "exit_announced"

    def test_obtains_financing_to_debt(self):
        result = correct_deal("obtains €50m in financing from bank", "")
        assert result == "debt_financing"

    def test_portfolio_update_detected(self):
        result = correct_deal("portfolio company xyz expands into spain", "xyz")
        assert result == "portfolio_update"

    def test_exited_from_portfolio_to_exit(self):
        result = correct_deal("nouryon exited from portfolio", "")
        assert result == "exit_announced"

    def test_genuine_deal_preserved(self):
        result = correct_deal("acquires majority stake in xyz for €500m", "apollo acquires xyz")
        assert result == "deal_announced"

    def test_closing_fund_to_fundraise(self):
        # _RE_CLOSING_FUND: "closing del/di/per/of fondo/fund/oversubscribed"
        # or _RE_CHIUDE_RACCOLTA: "chiude la raccolta"
        result = correct_deal("chiude la raccolta del fondo a €500m", "")
        assert result == "fundraise_closed"

    def test_bond_to_debt(self):
        result = correct_deal("places €300m bond for expansion", "")
        assert result == "debt_financing"

    def test_sells_stake_to_exit(self):
        result = correct_deal("sells 35% stake in xyz", "")
        assert result == "exit_announced"

    def test_portfolio_extraction_without_deal(self):
        result = correct_deal(
            "new listing on portfolio page", "",
            diff_summary_lower="new portfolio company detected",
        )
        assert result == "portfolio_update"

    # ── Portfolio company M&A — the class of bugs fixed Feb 2026 ─────────────

    def test_hyphenated_backed_acquires_portfolio_update(self):
        """[Fund]-backed [Company] acquires X → portfolio_update, NOT deal_announced.
        Root cause: correct_deal() previously only checked _RE_PORTFOLIO_UPDATE (which
        doesn't include 'backed') and blocked reclassification when deal verbs present."""
        assert correct_deal(
            "silver lake-backed facile.it acquires pratiche auto online",
            "silver lake-backed facile.it acquires pratiche auto online",
        ) == "portfolio_update"

    def test_backed_by_acquires_portfolio_update(self):
        assert correct_deal(
            "facile.it, backed by silver lake, acquires horizon automotive",
            "facile.it, backed by silver lake, acquires horizon automotive",
        ) == "portfolio_update"

    def test_bebeez_parenthetical_acquires(self):
        """Company (Fund) acquires — BeBeez format from real audit findings."""
        assert correct_deal(
            "lexham power (eos im) acquires majority stake in innovo agri",
            "lexham power (eos im) acquires majority stake in innovo agri",
        ) == "portfolio_update"

    def test_bebeez_parenthetical_oakley(self):
        assert correct_deal(
            "phenna group (oakley capital) makes sixth acquisition of italian company",
            "phenna group (oakley capital) makes sixth acquisition",
        ) == "portfolio_update"

    def test_portfolio_company_acquires(self):
        assert correct_deal(
            "bain capital portfolio company euronics acquires competitor",
            "portfolio company euronics acquires",
        ) == "portfolio_update"

    def test_bolt_on_is_portfolio_update(self):
        """Bolt-on acquisition = portfolio company M&A, always portfolio_update."""
        assert correct_deal(
            "ardian portfolio company completes bolt-on acquisition of xyz",
            "bolt-on acquisition completed",
        ) == "portfolio_update"

    def test_fund_directly_acquires_stays_deal(self):
        """Fund itself acquires → deal_announced (not portfolio_update)."""
        assert correct_deal(
            "silver lake acquires facile.it in €1bn deal",
            "silver lake acquires facile.it",
        ) == "deal_announced"

    def test_kkr_acquires_stays_deal(self):
        assert correct_deal(
            "kkr acquires italian tech company for €500m",
            "kkr acquires italian tech company",
        ) == "deal_announced"


# ── correct_fundraise ─────────────────────────────────────────────────────────


class TestCorrectFundraise:
    """Tests for fundraise_announced correction."""

    def test_obtains_financing_to_debt(self):
        result = correct_fundraise("obtains financing from bank for project", "")
        assert result == "debt_financing"

    def test_ordinal_investment_to_deal(self):
        result = correct_fundraise("fifth investment for fund ii in italian sme", "")
        assert result == "deal_announced"

    def test_closing_to_fundraise_closed(self):
        # _RE_FUNDRAISE_CLOSING: "final close" / "first close" / "close above target"
        result = correct_fundraise("final close of fund iii above target", "")
        assert result == "fundraise_closed"

    def test_genuine_fundraise_preserved(self):
        result = correct_fundraise("announces new fund targeting €500m", "")
        assert result == "fundraise_announced"

    def test_bond_to_debt(self):
        result = correct_fundraise("places €200m senior secured notes", "")
        assert result == "debt_financing"


# ── correct_fund_launch ───────────────────────────────────────────────────────


class TestCorrectFundLaunch:
    """Tests for fund_launch correction."""

    def test_merger_to_deal(self):
        result = correct_fund_launch("merger with competitor creates new entity", "")
        assert result == "deal_announced"

    def test_fund_level_fundraise_closing(self):
        # _RE_FUND_LEVEL_FUNDRAISE + _RE_FUNDRAISE_CLOSING required
        result = correct_fund_launch("final close of fund iii at €500m", "")
        assert result == "fundraise_closed"

    def test_investment_to_deal(self):
        result = correct_fund_launch("investe nel capitale di xyz", "investimento in xyz")
        assert result == "deal_announced"

    def test_genuine_fund_launch_preserved(self):
        result = correct_fund_launch(
            "launches new fund iii targeting €500m",
            "launches new fund iii",
        )
        assert result == "fund_launch"

    def test_accelerator_launch_to_other(self):
        result = correct_fund_launch("accelerator programme launches in milan", "accelerator launch")
        assert result == "other"

    def test_no_fund_vehicle_to_other(self):
        result = correct_fund_launch("new initiative for smes", "")
        assert result == "other"


# ── correct_people_move ───────────────────────────────────────────────────────


class TestCorrectPeopleMove:
    """Tests for people_move correction."""

    def test_join_forces_to_partnership(self):
        assert correct_people_move("join forces to promote esg", "") == "partnership"

    def test_advisory_council_to_other(self):
        # _RE_ADVISORY_BOARD requires match AND no appointment verbs
        # correct_people_move checks _RE_ADVISORY_BOARD pattern
        # The "joins" triggers the "joins hub/program" path first → partnership
        # Use different phrasing that hits _RE_ADVISORY_BOARD directly
        result = correct_people_move("new advisory board formed for the initiative", "")
        assert result == "other"

    def test_join_with_investment_to_deal(self):
        result = correct_people_move(
            "friulia joins quin and supports the group's multi-year growth plan",
            "friulia joins quin",
        )
        assert result == "deal_announced"

    def test_exit_verbs_to_exit(self):
        result = correct_people_move("sells majority stake in portfolio co", "")
        assert result == "exit_announced"

    def test_genuine_people_move_preserved(self):
        result = correct_people_move(
            "appointed john smith as new head of investments",
            "appointed john smith as head",
        )
        assert result == "people_move"

    def test_no_people_language_to_other(self):
        result = correct_people_move("generic text about market conditions", "market outlook")
        assert result == "other"

    def test_joins_hub_to_partnership(self):
        result = correct_people_move("snam joins tech 4 planet hub", "snam joins hub")
        assert result == "partnership"

    def test_team_profile_title_without_transition_to_other(self):
        result = correct_people_move(
            "giulio pesenti head of strategic business development",
            "giulio pesenti head of strategic business development",
            page_category="TEAM",
        )
        assert result == "other"

    def test_role_opening_title_to_other(self):
        result = correct_people_move(
            "senior investment associate, clean energy - capital dynamics",
            "senior investment associate, clean energy - capital dynamics",
            page_category="NEWS",
        )
        assert result == "other"


# ── correct_report ────────────────────────────────────────────────────────────


class TestCorrectReport:
    """Tests for report correction."""

    def test_exit_verbs_override(self):
        result = correct_report("sells stake in xyz", "")
        assert result == "exit_announced"

    def test_deal_without_report_to_deal(self):
        result = correct_report("acquires majority stake for €500m", "")
        assert result == "deal_announced"

    def test_genuine_report_preserved(self):
        result = correct_report("annual report 2024 shows strong growth", "")
        assert result == "report"


# ── correct_partnership ───────────────────────────────────────────────────────


class TestCorrectPartnership:
    """Tests for partnership correction."""

    def test_acquisition_to_deal(self):
        result = correct_partnership("acquires majority of grifo group", "eurazeo acquires grifo")
        assert result == "deal_announced"

    def test_portfolio_update_detected(self):
        result = correct_partnership("portfolio company xyz expands", "")
        assert result == "portfolio_update"

    def test_exit_verbs_to_exit(self):
        result = correct_partnership("sells its stake in the company", "")
        assert result == "exit_announced"

    def test_genuine_partnership_preserved(self):
        result = correct_partnership("strategic alliance with local partner", "new partnership")
        assert result == "partnership"


# ── detect_portfolio_update ───────────────────────────────────────────────────


class TestDetectPortfolioUpdate:
    """Tests for portfolio_update detection from other types."""

    def test_from_other_type(self):
        result = detect_portfolio_update("portfolio company xyz opens new office", "other")
        assert result == "portfolio_update"

    def test_backed_company_detected(self):
        result = detect_portfolio_update("backed by apollo, xyz expands into spain", "other")
        assert result == "portfolio_update"

    def test_wrong_type_returns_none(self):
        assert detect_portfolio_update("portfolio company news", "exit_announced") is None

    def test_no_portfolio_language_returns_none(self):
        assert detect_portfolio_update("generic news about the market", "other") is None


# ── correct_fundraise_to_deal_for_company_round ───────────────────────────────


class TestCompanyRound:
    """Tests for company round reclassification."""

    def test_series_a_to_deal(self):
        result = correct_fundraise_to_deal_for_company_round("closes series a round at €10m")
        assert result == "deal_announced"

    def test_fund_level_fundraise_preserved(self):
        result = correct_fundraise_to_deal_for_company_round(
            "closes fund iii at €500m above target"
        )
        assert result is None

    def test_no_round_returns_none(self):
        result = correct_fundraise_to_deal_for_company_round("annual report published")
        assert result is None


# ── apply_type_corrections (main entry point) ─────────────────────────────────


class TestApplyTypeCorrections:
    """Integration tests for the main correction dispatcher."""

    def test_exit_dispatched(self):
        result = apply_type_corrections(
            "exit_announced",
            "apollo acquires nouryon for €3b",
            "acquires nouryon",
        )
        assert result == "deal_announced"

    def test_deal_dispatched(self):
        result = apply_type_corrections(
            "deal_announced",
            "the sellers are apollo and kkr",
            "sellers are apollo",
        )
        assert result == "exit_announced"

    def test_deal_departure_language_to_people_move(self):
        result = apply_type_corrections(
            "deal_announced",
            "giampaolo di dio is stepping down as cio of fondo italiano d'investimento sgr",
            "fondo italiano d'investimento sgr, cio giampaolo di dio leaves",
        )
        assert result == "people_move"

    def test_fundraise_dispatched(self):
        result = apply_type_corrections(
            "fundraise_announced",
            "final close of fund iii above target",
            "final close of fund iii",
        )
        assert result == "fundraise_closed"

    def test_portfolio_update_sale_to_exit(self):
        result = apply_type_corrections(
            "portfolio_update",
            "announces the sale of its stake in xyz",
            "announces the sale",
        )
        assert result == "exit_announced"

    def test_other_rescued_to_people_move(self):
        result = apply_type_corrections(
            "other",
            "names john smith as new head of investments and strategy",
            "names john smith as head",
        )
        assert result == "people_move"

    def test_other_rescued_to_deal(self):
        result = apply_type_corrections(
            "other",
            "offers €500m for acquisition of xyz",
            "offers €500m for xyz",
        )
        assert result == "deal_announced"

    def test_unknown_type_passthrough(self):
        result = apply_type_corrections(
            "website_change",
            "generic text",
            "generic title",
        )
        assert result == "website_change"

    def test_fundraise_closed_company_round(self):
        result = apply_type_corrections(
            "fundraise_closed",
            "closes series b round at €50m",
            "series b closed",
        )
        assert result == "deal_announced"
