"""
Shared signal type correction logic for the Fundradar pipeline.

Both filter_signals.py and enrich_signals_openai.py apply post-classification
corrections to fix signal types. This module is the SINGLE SOURCE OF TRUTH
for those corrections — both files call these functions.

When adding a new correction rule, add it HERE. Both filter and enricher
will pick it up automatically.

Architecture:
  apply_universal_demotions()  — runs first, catches garbage before type-specific logic
  apply_type_corrections()     — type-specific corrections (exit→deal, deal→exit, etc.)

File-specific logic stays in each file:
  filter_signals.py:  domain ownership check, portfolio delta detection, initial classification
  enrich_signals_openai.py:  VC round logic, keyword fallback, fund_launch back-promotion
"""

from __future__ import annotations

import re
from typing import Optional

from signal_patterns import (
    _RE_ACCELERATOR_LAUNCH,
    _RE_ACCELERATOR_RESULTS,
    _RE_ACQUISITION_VERBS,
    _RE_ADVISORY_BOARD,
    _RE_AGREEMENT,
    _RE_AGREEMENT_PARTNERSHIP_CONTEXT,
    _RE_APPOINTMENT_VERBS,
    _RE_BOARD_APPOINT,
    _RE_BOILERPLATE_TEMPLATE,
    _RE_BOND_EXCLUDE,
    _RE_BOND_ISSUANCE,
    _RE_BUYER_CUES,
    _RE_CHIUDE_FONDO,
    _RE_CHIUDE_RACCOLTA,
    _RE_CLOSE_VERBS,
    _RE_CLOSING_FUND,
    _RE_COMPANY_ROUND,
    _RE_CREDIT_FACILITY,
    _RE_DEBT_FINANCING_BROAD,
    _RE_DEBT_RESTRUCTURE_CONTEXT,
    _RE_DEBT_RESTRUCTURING,
    _RE_EDITORIAL_FORMAT,
    _RE_EDITORIAL_STRATEGY,
    _RE_EVENT_ATTENDANCE,
    _RE_EVENT_INSIGHTS,
    _RE_EVENT_RECAP_ITALIAN,
    _RE_EVENT_TITLE,
    _RE_EXIT_VERBS,
    _RE_EXITED_FROM_PORTFOLIO,
    _RE_EXPLICIT_SELLER,
    _RE_FASHION_CAMPAIGN,
    _RE_FINALIZZAT,
    _RE_FUND_COMPARTMENT_OPERATIONAL,
    _RE_FUND_LAUNCH_STRICT,
    _RE_FUND_LAUNCH_VERBS,
    _RE_FUND_LEVEL_FUNDRAISE,
    _RE_FUNDRAISE_ACQUISITION,
    _RE_FUNDRAISE_CLOSED_VERBS,
    _RE_FUNDRAISE_CLOSING,
    _RE_FUNDRAISE_MILESTONE,
    _RE_FUNDRAISE_VERBS_FULL,
    _RE_HAS_ANY_PE_VERB,
    _RE_INTERNSHIP,
    _RE_INTERVIEW,
    _RE_INTERVIEW_EDITORIAL,
    _RE_INVEST_VERBS,
    _RE_INVESTOR_MEETING,
    _RE_JOB_POSTING_RECLASSIFY,
    _RE_JOB_SELECTION,
    _RE_JOINS_EVENT,
    _RE_LAUNCH_FUND,
    _RE_LP_COMMITMENT,
    _RE_MERGER,
    _RE_OFFER_BID,
    _RE_OFFICE_OPENING,
    _RE_ORDINAL_INVESTMENT,
    _RE_OUTSOURCING,
    _RE_PARTNERSHIP,
    _RE_PARTNERSHIP_EXCLUDE,
    _RE_PEOPLE_LANGUAGE,
    _RE_PEOPLE_TITLE,
    _RE_PORTFOLIO_CO_AS_ACQUIRER,
    _RE_PORTFOLIO_COMPANY_BACKED,
    _RE_PORTFOLIO_UPDATE,
    _RE_PROJECT_FINANCING,
    _RE_RACCOGLIE_EXCLUDE,
    _RE_RACCOGLIE_ROUND,
    _RE_REGULATORY_COMMUNICATION,
    _RE_REPORT,
    _RE_RESEARCH,
    _RE_REVENUE_PERFORMANCE,
    _RE_ROUND_INVEST,
    _RE_STRONG_DEAL,
    _RE_STRONG_EXIT_VERBS,
    _RE_TEAM_STRENGTHENING,
    _RE_VALUE_CREATION,
)


# Pattern lists used by filter — kept as module-level for both files to share
DEAL_CLASSIFY_PATTERNS = None  # Injected by callers (filter has dict-based, enricher has regex-based)
EXIT_CLASSIFY_PATTERNS = None
FUNDRAISE_CLASSIFY_PATTERNS = None
FUND_LAUNCH_CLASSIFY_PATTERNS = None
PEOPLE_CLASSIFY_PATTERNS = None


def _matches_deal(text_lower: str) -> bool:
    """Check if text has deal/acquisition language."""
    return bool(
        _RE_ACQUISITION_VERBS.search(text_lower)
        or _RE_INVEST_VERBS.search(text_lower)
        or _RE_OFFER_BID.search(text_lower)
        or _RE_COMPANY_ROUND.search(text_lower)
        or _RE_STRONG_DEAL.search(text_lower)
    )


def _matches_exit(text_lower: str) -> bool:
    """Check if text has exit language."""
    return bool(
        _RE_EXIT_VERBS.search(text_lower)
        or _RE_STRONG_EXIT_VERBS.search(text_lower)
        or _RE_EXPLICIT_SELLER.search(text_lower)
        or _RE_EXITED_FROM_PORTFOLIO.search(text_lower)
    )


def _matches_fundraise(text_lower: str) -> bool:
    """Check if text has fundraise language."""
    return bool(
        _RE_FUND_LEVEL_FUNDRAISE.search(text_lower)
        or _RE_FUNDRAISE_CLOSING.search(text_lower)
        or _RE_FUNDRAISE_MILESTONE.search(text_lower)
        or _RE_CHIUDE_RACCOLTA.search(text_lower)
    )


def _matches_fund_launch(text_lower: str) -> bool:
    """Check if text has fund launch language."""
    return bool(
        _RE_FUND_LAUNCH_STRICT.search(text_lower)
        or _RE_LAUNCH_FUND.search(text_lower)
        or _RE_FUND_LAUNCH_VERBS.search(text_lower)
    )


# ── Universal demotions ──────────────────────────────────────────────────────


def apply_universal_demotions(text_lower: str, title_lower: str) -> Optional[str]:
    """Check for universal patterns that override any signal type.

    Returns the corrected type if a demotion applies, or None if no demotion.
    These run BEFORE type-specific corrections in both filter and enricher.
    """
    # Conference events with date in title: "3rd Annual LPGP Connect 3/25/2026 - organizer"
    # The date embedded in the title is the key differentiator for conference listings.
    if re.search(r"\b\d+(?:st|nd|rd|th)?\s+annual\b.{0,80}\b\d{1,2}/\d{1,2}/\d{4}\b", text_lower):
        return "other"

    # Press review / rassegna stampa → other (aggregated press clippings, not PE signals)
    # Also catch "Press Review:" prefix pattern from FIEE-SGR extractor
    if re.search(r"\b(?:rassegna\s+stampa|press\s+review)\b", text_lower):
        return "other"
    if re.search(r"^(?:press\s+review|rassegna\s+stampa)\s*:", title_lower):
        return "other"

    # Podcast/talk/webinar series (e.g., "#innoistalk", "webinar series") → other
    if re.search(r"(?:#\w+talk\b|\bpodcast\s+(?:series|episode|ep\.?)|\bwebinar\s+series)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Call for applications / accelerator open call → other
    if re.search(r"\bcall\s+for\s+(?:applications?|proposals?|startups?)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Exploratory survey / procurement RFP → other
    if re.search(r"\b(?:exploratory|indagine\s+di\s+mercato)\s+(?:survey|sondaggio)\b", text_lower):
        return "other"
    # Broader outsourcing/procurement RFP patterns
    if re.search(r"\boutsourcing\s+of\s+(?:internal\s+)?(?:audit|compliance|risk)\b", text_lower):
        return "other"

    # Investor meeting / LP event → other
    if re.search(r"\binvestor\s+(?:meeting|day|conference|summit)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Research summary / report aggregate → other (not a specific PE transaction)
    if re.search(r"\bsummary\s+of\s+research\s+conducted\b", text_lower):
        return "other"

    # Strong exit verbs override everything (unless acquisition verbs also present)
    if _RE_STRONG_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
        return "exit_announced"

    # Fashion/marketing campaign → other (portfolio co PR, not PE activity)
    if _RE_FASHION_CAMPAIGN.search(text_lower):
        return "other"

    # Editorial format changes (magazine weekly→fortnightly etc.) → other
    if _RE_EDITORIAL_FORMAT.search(text_lower):
        return "other"

    # Boilerplate template signals with zero information → other
    if _RE_BOILERPLATE_TEMPLATE.search(text_lower):
        return "other"

    # Outsourcing/procurement RFP → other (not PE activity)
    if _RE_OUTSOURCING.search(text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower):
            return "other"

    # Event/conference attendance → other
    if _RE_EVENT_ATTENDANCE.search(text_lower):
        return "other"

    # Event/talk/webinar series launch → other (not PE activity)
    if re.search(r"\b(?:series|ciclo|rassegna)\b.*\b(?:dedicated|dedicat[oa]|kicks?\s+off|al\s+via)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Pure event title (no deal content) → other
    if _RE_EVENT_TITLE.search(text_lower) and not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
        return "other"

    # "Joins forum/conference" → other
    if _RE_JOINS_EVENT.search(text_lower) and not _matches_deal(text_lower):
        return "other"

    # Investor/LP meetings → other
    if _RE_INVESTOR_MEETING.search(text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Interview/editorial without PE verbs → other
    if _RE_INTERVIEW.search(text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Opinion/analysis articles without concrete PE transactions → other
    if re.search(r"\b(?:opinion|analysis|commentary|point\s+of\s+view|outlook|forecast|perspectives?|riflessioni)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Blog post / thought-leadership titles with no PE event → other
    # e.g., "Beyond Capital: What it really takes to scale tech in Europe"
    if re.search(r"\b(?:what\s+it\s+(?:really\s+)?takes|how\s+to\s+|why\s+we\s+(?:don.?t|believe|think)|lessons?\s+(?:from|learned))\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Private matching / media partnership events → other
    if re.search(r"\bprivate\s+matching\b", text_lower):
        if not _matches_deal(text_lower):
            return "other"

    # CEO interview / "That's why we..." opinion pattern → other
    if re.search(r"\bthat.?s\s+why\s+we\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Industry coalition/trade group formation → other (not PE activity)
    if re.search(r"\bcoalition\s+(?:launched|formed|created|established)\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Generic article headlines with no PE content (e.g., "The deep sea: a crossroads of...")
    if re.search(r"\bcrossroads?\s+of\b|\bfrontier\s+of\b", text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # Event insights/recaps → other
    if _RE_EVENT_INSIGHTS.search(text_lower) or _RE_EVENT_RECAP_ITALIAN.search(text_lower):
        return "other"

    # Marketing/thought-leadership → other
    if _RE_VALUE_CREATION.search(text_lower):
        return "other"

    # Internship/stage offers → job_posting
    if _RE_INTERNSHIP.search(text_lower):
        return "job_posting"

    # Editorial "investment strategy" content → other
    # Allow demotion even when deal patterns match, if there's no monetary amount
    _has_monetary = bool(re.search(r"€\s*\d|\$\s*\d|\b\d+\s*(?:milion|million|mln|miliard|billion)\b", text_lower, re.IGNORECASE))
    if _RE_EDITORIAL_STRATEGY.search(text_lower):
        if (not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _RE_STRONG_DEAL.search(text_lower)) or not _has_monetary:
            return "other"

    # Financial results / annual reports → report (before revenue_performance check)
    if _RE_REPORT.search(text_lower):
        if not _RE_FUND_LAUNCH_VERBS.search(text_lower) and not _matches_deal(text_lower):
            return "report"

    # Portfolio company revenue articles → other
    if _RE_REVENUE_PERFORMANCE.search(text_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower):
            return "other"

    # Bond issuance / refinancing → debt_financing
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"

    # Credit facility → debt_financing
    if _RE_CREDIT_FACILITY.search(text_lower) and not _matches_deal(text_lower):
        return "debt_financing"

    # Broader debt financing → debt_financing
    if _RE_DEBT_FINANCING_BROAD.search(text_lower):
        if not _matches_deal(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
            return "debt_financing"

    # Regulatory/internal dealing → other
    if _RE_REGULATORY_COMMUNICATION.search(text_lower):
        return "other"

    # Research/publication → other
    if _RE_RESEARCH.search(text_lower):
        if not _matches_deal(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    # "NOTICE:" / "AVVISO:" title prefix → other (regulatory filings, not PE activity)
    if re.search(r"^(?:notice|avviso)\s*:", title_lower):
        if not _matches_deal(text_lower) and not _matches_exit(text_lower) and not _matches_fundraise(text_lower):
            return "other"

    return None


# ── Type-specific corrections ─────────────────────────────────────────────────


def correct_exit(text_lower: str, title_lower: str, page_category: str = "") -> str:
    """Correct exit_announced signals. Returns corrected type."""
    # Job posting misclassified as exit
    if _RE_JOB_POSTING_RECLASSIFY.search(text_lower):
        return "job_posting"

    # Outsourcing/procurement RFP misclassified as exit
    if _RE_OUTSOURCING.search(text_lower):
        return "other"

    # Fashion/campaign misclassified as exit
    if _RE_FASHION_CAMPAIGN.search(text_lower):
        return "other"

    # Editorial format change misclassified as exit
    if _RE_EDITORIAL_FORMAT.search(text_lower):
        return "other"

    # Bond/debt issuance misclassified as exit (bond issues, green bonds, credit facilities,
    # refinancing — these are debt events, not fund exits from portfolio companies)
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        if not _RE_STRONG_EXIT_VERBS.search(text_lower):
            return "debt_financing"
    if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "debt_financing"
    if _RE_CREDIT_FACILITY.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "debt_financing"

    # "Evaluating sale" / "considering sale" / "exploring sale" — process initiation, not completed exit
    # Keep as deal_announced (potential transaction) rather than exit_announced (completed)
    if re.search(r"\b(?:evaluat|consider|explor|weigh|assess)\w*\s+(?:the\s+)?(?:sale|disposal|divestiture|exit)\b", text_lower):
        if not _RE_EXITED_FROM_PORTFOLIO.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
            return "deal_announced"

    # Confirmed exit patterns — keep
    if _RE_EXITED_FROM_PORTFOLIO.search(text_lower):
        return "exit_announced"

    # Service contract / mandate selection → partnership (not an exit)
    if re.search(r"\b(?:select(?:s|ed)?|chosen|appoint(?:s|ed)?|retain(?:s|ed)?|win(?:s)?|award(?:s|ed)?)\b", text_lower):
        if re.search(r"\b(?:manag(?:e|es|ement)|administer|oversee|mandate|advisory)\b", text_lower):
            if not _RE_EXIT_VERBS.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
                return "partnership"

    # Partnership/agreement without exit/deal verbs → partnership
    if _RE_AGREEMENT.search(text_lower) and not _RE_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
        if _RE_AGREEMENT_PARTNERSHIP_CONTEXT.search(text_lower):
            return "partnership"

    has_explicit_seller = bool(
        _RE_EXPLICIT_SELLER.search(text_lower) or _RE_EXITED_FROM_PORTFOLIO.search(text_lower)
    )

    # Buyer perspective in title → deal
    if re.search(r"\bacquires?\s+\w+", title_lower) and not has_explicit_seller:
        return "deal_announced"

    # Buyer cues in title → deal
    if _RE_BUYER_CUES.search(title_lower) and not has_explicit_seller:
        return "deal_announced"

    # Buyer cues in body (without strong exit verbs) → deal
    if _RE_BUYER_CUES.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "deal_announced"

    # Offer/bid without exit verbs → deal
    if _RE_OFFER_BID.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "deal_announced"

    # Acquisition verbs without exit verbs → deal
    if _RE_ACQUISITION_VERBS.search(text_lower) and not _RE_EXIT_VERBS.search(text_lower):
        return "deal_announced"

    # Investment verbs without exit verbs → deal
    if _RE_INVEST_VERBS.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "deal_announced"

    # "launch/lancia fund" on exit signal → fund_launch
    if _RE_LAUNCH_FUND.search(text_lower):
        return "fund_launch"

    # Partnership without exit verbs → partnership
    if _RE_PARTNERSHIP.search(text_lower) and not _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "partnership"

    # Safety net: exit with ZERO PE verbs → other (likely misclassified)
    if page_category != "PORTFOLIO" and not _RE_HAS_ANY_PE_VERB.search(text_lower):
        return "other"

    return "exit_announced"


def correct_deal(text_lower: str, title_lower: str, diff_summary_lower: str = "") -> str:
    """Correct deal_announced signals. Returns corrected type."""
    # Portfolio extraction without deal evidence → portfolio_update
    # "New portfolio company detected via extraction" with no deal verbs = just a listing
    if "new portfolio company detected" in diff_summary_lower:
        if not _matches_deal(text_lower) and not _matches_exit(text_lower):
            return "portfolio_update"

    # "announces the sale of" / "completes the sale of" / "agreement to sell" → exit
    # These are seller-side language even though they contain deal verbs
    if re.search(r"\b(?:announc\w+\s+the\s+sale|completes?\s+(?:the\s+)?sale|agreement\s+to\s+sell|puts?\s+up\s+for\s+sale)\b", text_lower):
        return "exit_announced"

    # "the sellers are [fund]" / "seller is [fund]" → exit (the fund is selling)
    if re.search(r"\b(?:sellers?\s+(?:are|is|include)\b)", text_lower):
        return "exit_announced"

    # "obtains €X in financing/credit/loan" → debt_financing (not a deal)
    if re.search(r"\bobtains?\s+[€$£]?\s*\d+.*?\b(?:financ\w+|credit|loan|facility)\b", text_lower):
        return "debt_financing"

    # Fund sells/sold/divests stake → exit (explicit divestment)
    if re.search(r"\b(?:sells?|sold|divests?|divested|cede|ceduto)\s+(?:(?:\w+|[\d.]+%?)\s+)?(?:stake|position|shares?|interest|partecipazione|quota)\b", text_lower):
        return "exit_announced"

    # Portfolio company (not the fund) is the acquirer → portfolio_update.
    # "[Fund]-backed [Company] acquires X", "backed by [Fund]..acquires", bolt-on/add-on, etc.
    # This fires BEFORE the _RE_PORTFOLIO_UPDATE check so acquisition verbs don't block it:
    # when a portfolio company acquires, deal verbs are expected and correct — the key is
    # that the PORTFOLIO COMPANY is the subject, not the fund deploying new capital.
    if _RE_PORTFOLIO_CO_AS_ACQUIRER.search(text_lower):
        return "portfolio_update"

    # Portfolio company news → portfolio_update (no acquisition verbs = pure company update)
    if _RE_PORTFOLIO_UPDATE.search(text_lower):
        _has_deal_in_title = bool(_RE_ACQUISITION_VERBS.search(title_lower) or _RE_INVEST_VERBS.search(title_lower))
        _has_deal_in_body = bool(_RE_ACQUISITION_VERBS.search(text_lower) or _RE_STRONG_DEAL.search(text_lower))
        if not _has_deal_in_title and not _has_deal_in_body:
            return "portfolio_update"

    # "exited from portfolio" → exit
    if _RE_EXITED_FROM_PORTFOLIO.search(text_lower):
        return "exit_announced"

    # Explicit seller → exit
    if _RE_EXPLICIT_SELLER.search(text_lower):
        return "exit_announced"

    # Strong exit verbs without acquisition verbs → exit
    if _RE_STRONG_EXIT_VERBS.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower):
        # Don't reclassify if buyer perspective in title
        if not (_RE_BUYER_CUES.search(title_lower) and not _RE_EXPLICIT_SELLER.search(text_lower)):
            return "exit_announced"

    # Outsourcing → other
    if _RE_OUTSOURCING.search(text_lower):
        return "other"

    # Internship → job_posting
    if _RE_INTERNSHIP.search(text_lower):
        return "job_posting"

    # Job posting language → job_posting
    if _RE_JOB_SELECTION.search(text_lower):
        return "job_posting"

    # Team strengthening → people_move (if no deal language)
    if _RE_TEAM_STRENGTHENING.search(text_lower) and not _matches_deal(text_lower):
        return "people_move"

    # Partnership language → partnership
    if _RE_PARTNERSHIP.search(text_lower) and not _RE_INVEST_VERBS.search(text_lower) and not _RE_EXIT_VERBS.search(text_lower):
        if not _RE_PARTNERSHIP_EXCLUDE.search(text_lower):
            return "partnership"

    # Fund being acquired by another entity → other (corporate M&A of the PE firm)
    if re.search(r"\b(?:acquisition|acquisizione)\s+(?:by|da\s+parte\s+di)\b", text_lower):
        return "other"

    # Insolvency / composition with creditors / liquidation → other (not a PE deal)
    if re.search(
        r"\b(?:composition\s+with\s+creditors?|compulsory\s+(?:administrative\s+)?liquidation|insolvency\s+proceedings?|concordato\s+preventivo)\b",
        text_lower,
    ):
        return "other"

    # Debt restructuring → other or debt_financing
    if _RE_DEBT_RESTRUCTURING.search(text_lower):
        if _RE_DEBT_RESTRUCTURE_CONTEXT.search(text_lower):
            return "debt_financing"
        return "other"

    # Bond/debt financing
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"
    if _RE_CREDIT_FACILITY.search(text_lower):
        return "debt_financing"
    if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_ACQUISITION_VERBS.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"
    if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"

    # "provides/announces financing" → debt_financing (fund acting as lender)
    if re.search(r"\b(?:provid\w+|announc\w+|secur\w+)\s+(?:up\s+to\s+)?[€$£]?\s*\d+.*?\b(?:financ\w+|loan|credit)\b", text_lower):
        if not _RE_INVEST_VERBS.search(text_lower):
            return "debt_financing"

    # Fundraise closing misclassified as deal
    if _RE_CLOSING_FUND.search(text_lower):
        return "fundraise_closed"
    if _RE_CHIUDE_RACCOLTA.search(text_lower):
        return "fundraise_closed"

    return "deal_announced"


def correct_fund_launch(text_lower: str, title_lower: str) -> str:
    """Correct fund_launch signals. Returns corrected type."""
    has_fund_vehicle = bool(_RE_FUND_LAUNCH_STRICT.search(title_lower))

    # Merger/fusion → deal
    if _RE_MERGER.search(text_lower):
        return "deal_announced"

    # Fund-level fundraise → fundraise
    if _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        if _RE_FUNDRAISE_CLOSING.search(text_lower) or _RE_CHIUDE_FONDO.search(text_lower):
            return "fundraise_closed"
        return "fundraise_announced"

    # Bond issuance → debt_financing
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"
    if _RE_CREDIT_FACILITY.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"
    if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"
    if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"

    # Accelerator launch → other (unless also a fund launch)
    if _RE_ACCELERATOR_LAUNCH.search(text_lower) and not has_fund_vehicle:
        return "other"

    # Accelerator results → other
    if _RE_ACCELERATOR_RESULTS.search(text_lower) and not has_fund_vehicle:
        return "other"

    # LP commitment → fundraise
    if _RE_LP_COMMITMENT.search(text_lower) and not has_fund_vehicle:
        return "fundraise_announced"

    # Outsourcing → other
    if _RE_OUTSOURCING.search(text_lower):
        return "other"

    # Job posting → job_posting
    if _RE_JOB_SELECTION.search(text_lower):
        return "job_posting"

    # Ordinal investment → deal
    if _RE_ORDINAL_INVESTMENT.search(text_lower):
        return "deal_announced"

    # Board/appointment → people_move (unless also fund launch)
    if _RE_BOARD_APPOINT.search(text_lower) and not has_fund_vehicle:
        return "people_move"

    # Office opening → people_move
    if _RE_OFFICE_OPENING.search(text_lower) and not _RE_INVEST_VERBS.search(text_lower):
        return "people_move"

    # Offer/bid → deal
    if _RE_OFFER_BID.search(text_lower):
        return "deal_announced"

    # Investment verbs → deal
    if _RE_INVEST_VERBS.search(text_lower):
        return "deal_announced"

    # Company round → deal
    if _RE_COMPANY_ROUND.search(text_lower):
        return "deal_announced"

    # Round invest in title
    if _RE_ROUND_INVEST.search(title_lower):
        if _RE_CLOSE_VERBS.search(title_lower):
            return "fundraise_closed"
        return "fundraise_announced"

    # "chiude il fondo" → fundraise_closed
    if _RE_CHIUDE_FONDO.search(text_lower):
        return "fundraise_closed"

    # Fundraise milestone → fundraise_closed
    if _RE_FUNDRAISE_MILESTONE.search(text_lower):
        return "fundraise_closed"

    # Finalized deal → deal
    if _RE_FINALIZZAT.search(text_lower):
        return "deal_announced"

    # Partnership (without fund vehicle) → partnership or deal
    if _RE_PARTNERSHIP.search(text_lower) and not has_fund_vehicle:
        if not _RE_PARTNERSHIP_EXCLUDE.search(text_lower):
            return "partnership"
        return "deal_announced"

    # Debt restructuring → other
    if _RE_DEBT_RESTRUCTURING.search(text_lower) and not _RE_INVEST_VERBS.search(text_lower):
        return "other"

    # Revenue/financial results (no fund vehicle) → other
    if _RE_REVENUE_PERFORMANCE.search(text_lower) and not has_fund_vehicle:
        return "other"

    # Editorial content (no fund vehicle) → other
    if _RE_EDITORIAL_STRATEGY.search(text_lower) and not has_fund_vehicle:
        return "other"

    # "launches partnership" → partnership
    if re.search(r"\b(?:launch(?:es|ed)?|lancia|lancio)\b.{0,30}\b(?:partnership|collaborazione|accordo|alleanza)", title_lower):
        return "partnership"

    # Historical launch reference → other
    if re.search(r"\blaunched?\s+in\s+20(?:1\d|2[0-4])\b", text_lower):
        return "other"

    # Catch-all: fund_launch without fund vehicle → other
    if not has_fund_vehicle:
        return "other"

    return "fund_launch"


def correct_fundraise(text_lower: str, title_lower: str) -> str:
    """Correct fundraise_announced signals. Returns corrected type."""
    # "obtains financing/loan from [bank]" → debt_financing (project financing, not fund raise)
    if re.search(r"\bobtains?\b.*\b(?:financ\w+|credit|loan|facility)\b.*\bfrom\b", text_lower):
        return "debt_financing"

    # Ordinal investment → deal (e.g., "Fifth investment for Fund II")
    if _RE_ORDINAL_INVESTMENT.search(text_lower):
        return "deal_announced"

    # Acquisition verbs → deal
    if _RE_FUNDRAISE_ACQUISITION.search(text_lower):
        return "deal_announced"

    # Closing verbs → fundraise_closed
    if _RE_FUNDRAISE_CLOSING.search(text_lower):
        return "fundraise_closed"
    if _RE_FUNDRAISE_MILESTONE.search(text_lower):
        return "fundraise_closed"
    if _RE_FUNDRAISE_CLOSED_VERBS.search(text_lower):
        return "fundraise_closed"

    # Closing of oversubscribed fund → fundraise_closed
    if _RE_CLOSING_FUND.search(text_lower):
        return "fundraise_closed"

    # Debt financing → debt_financing
    if _RE_BOND_ISSUANCE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"
    if _RE_DEBT_FINANCING_BROAD.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "debt_financing"
    if _RE_PROJECT_FINANCING.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower) and not _RE_BOND_EXCLUDE.search(text_lower):
        return "debt_financing"

    # Thought leadership / editorial → other
    if _RE_EDITORIAL_STRATEGY.search(text_lower) and not _RE_INVEST_VERBS.search(text_lower):
        return "other"

    # Financial results → report
    if _RE_REPORT.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "report"

    return "fundraise_announced"


def correct_people_move(text_lower: str, title_lower: str) -> str:
    """Correct people_move signals. Returns corrected type."""
    # "join forces" / "join forces to promote" → partnership (not a person move)
    if re.search(r"\bjoin\s+forces\b", text_lower):
        return "partnership"

    # "joins the [council/committee/board] of [government body]" → other
    # Advisory/government body participation is not a PE fund signal
    if re.search(r"\bjoins?\s+(?:the\s+)?(?:technical|scientific|advisory)[\s\-]+(?:council|committee|board)\b", text_lower):
        if not re.search(r"\b(?:appoint\w*|nomin\w*|hired?)\b", text_lower):
            return "other"

    # Fund "joins" a company with investment/growth language → deal_announced
    # e.g., "Friulia joins Quin and supports the Group's multi-year growth plan"
    if re.search(r"\b(?:joins?|aderisce|entra\s+in)\b", text_lower):
        if re.search(r"\b(?:support\w*\s+(?:the\s+)?(?:group|company|growth)|growth\s+plan|multi-year|piano\s+di\s+crescita|investe|invest\w+\s+in)\b", text_lower):
            _has_hire = bool(re.search(r"\b(?:appoint\w*|nomin\w*|hired?|as\s+(?:managing|director|partner|head|chief|ceo|cfo|coo|cto))\b", text_lower))
            if not _has_hire:
                return "deal_announced"

    # Company/org "joins" a program/hub/fund → partnership (not people hire)
    # e.g. "SNAM joins Tech 4 Planet hub", "Newlat Food joins Corporate Partners"
    # Guard: only if no explicit hire/appointment language (appointed/named/hired/as + role)
    if re.search(r"\b(?:joins?|aderisce|entra\s+in)\b", text_lower):
        if re.search(r"\b(?:hub|program|partner|fund|fondo|initiative|corporate|accelerat|platform)\b", text_lower):
            _has_hire = bool(re.search(r"\b(?:appoint\w*|nomin\w*|hired?|as\s+(?:managing|director|partner|head|chief|ceo|cfo|coo|cto))\b", text_lower))
            if not _has_hire and not _RE_BOARD_APPOINT.search(text_lower):
                return "partnership"

    # Advisory board formation (without appointment verbs) → other
    if _RE_ADVISORY_BOARD.search(text_lower) and not _RE_APPOINTMENT_VERBS.search(text_lower):
        return "other"

    # Strong exit verbs → exit
    if _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "exit_announced"

    # Team strengthening with no deal → keep people_move
    if _RE_TEAM_STRENGTHENING.search(text_lower) and not _matches_deal(text_lower):
        return "people_move"

    # Report patterns → report
    if _RE_REPORT.search(text_lower) and not _matches_deal(text_lower):
        return "report"

    # Investment/deal verbs → deal
    if _RE_INVEST_VERBS.search(text_lower) or _RE_STRONG_DEAL.search(text_lower):
        return "deal_announced"

    # Fundraise language → fundraise
    if _RE_CHIUDE_FONDO.search(text_lower) or _matches_fundraise(text_lower):
        if _RE_FUNDRAISE_CLOSED_VERBS.search(text_lower):
            return "fundraise_closed"
        return "fundraise_announced"

    # CEO/CFO interviews → other (not personnel changes)
    if _RE_INTERVIEW_EDITORIAL.search(text_lower):
        if not _RE_PEOPLE_LANGUAGE.search(text_lower) and not re.search(
            r"\b(?:dimission\w+|resign\w+|leaves?)\b", text_lower, re.IGNORECASE
        ):
            return "other"

    # Safety net: people_move with NO people-related language → other
    if not _RE_PEOPLE_TITLE.search(text_lower) and not _RE_BOARD_APPOINT.search(text_lower):
        if not _RE_PEOPLE_LANGUAGE.search(text_lower):
            return "other"

    return "people_move"


def correct_report(text_lower: str, title_lower: str) -> str:
    """Correct report signals. Returns corrected type."""
    # Strong exit verbs → exit
    if _RE_STRONG_EXIT_VERBS.search(text_lower) or _RE_EXPLICIT_SELLER.search(text_lower):
        return "exit_announced"

    # Accelerator launch → other
    if _RE_ACCELERATOR_LAUNCH.search(text_lower):
        return "other"

    # Fund compartment operational → fund_launch
    if _RE_FUND_COMPARTMENT_OPERATIONAL.search(text_lower):
        return "fund_launch"

    # Fund launch patterns → fund_launch
    if _RE_FUND_LAUNCH_VERBS.search(text_lower) and _matches_fund_launch(text_lower):
        return "fund_launch"

    # Deal patterns without report language → deal
    if _matches_deal(text_lower) and not _RE_REPORT.search(text_lower):
        return "deal_announced"

    return "report"


def correct_partnership(text_lower: str, title_lower: str) -> str:
    """Correct partnership signals. Returns corrected type."""
    # Acquisition/majority stake → deal (not partnership)
    # e.g., "Eurazeo acquires majority of Grifo Group"
    if _RE_ACQUISITION_VERBS.search(text_lower):
        return "deal_announced"

    # Portfolio company news → portfolio_update
    if _RE_PORTFOLIO_UPDATE.search(text_lower):
        return "portfolio_update"

    # Accelerator launch → other
    if _RE_ACCELERATOR_LAUNCH.search(text_lower) and not _RE_FUND_LAUNCH_STRICT.search(text_lower):
        return "other"

    # Partnership with investment language → deal
    if re.search(
        r"\b(?:aumento\s+di\s+capitale|round\s+da|incassa|raccog\w+|investi\w+\s+(?:di|da|per|in)\s+"
        r"|invests?\s+in\b|co[\-\s]?invest\w+|€\d+\s*[MB]\w*\s+invest\w+|\d+\s*M€?\s+invest\w+)\b",
        text_lower, re.IGNORECASE
    ):
        return "deal_announced"

    # Strong exit verbs → exit
    if _RE_STRONG_EXIT_VERBS.search(text_lower):
        return "exit_announced"

    # Interview/editorial → other
    if _RE_INTERVIEW_EDITORIAL.search(text_lower):
        if not re.search(r"\b(?:nomin\w+|appoint\w+|hired?|joins?|joined|firmato|signed|accordo|agreement)\b", text_lower, re.IGNORECASE):
            return "other"

    return "partnership"


# ── Portfolio update detection ────────────────────────────────────────────────


def detect_portfolio_update(text_lower: str, current_type: str) -> Optional[str]:
    """Detect portfolio_update signals from other/deal/partnership types.

    Returns "portfolio_update" if detected, None otherwise.
    """
    if current_type not in ("other", "deal_announced", "partnership"):
        return None

    if _RE_PORTFOLIO_UPDATE.search(text_lower):
        return "portfolio_update"

    # "partecipata/sostenuta/backed ... acquires/expands"
    if _RE_PORTFOLIO_COMPANY_BACKED.search(text_lower):
        return "portfolio_update"

    # "[Fund]-backed [Company] acquires", bolt-on/add-on, "backed by [Fund] acquires", etc.
    if _RE_PORTFOLIO_CO_AS_ACQUIRER.search(text_lower):
        return "portfolio_update"

    return None


# ── Company round reclassification ────────────────────────────────────────────


def correct_fundraise_to_deal_for_company_round(text_lower: str) -> Optional[str]:
    """When a fund's portfolio company raises a round, it's the fund's investment (deal).

    Returns "deal_announced" if applicable, None otherwise.
    """
    if _RE_COMPANY_ROUND.search(text_lower) and not _RE_FUND_LEVEL_FUNDRAISE.search(text_lower):
        return "deal_announced"
    return None


# ── Main entry points ─────────────────────────────────────────────────────────


def apply_type_corrections(
    current_type: str,
    text_lower: str,
    title_lower: str,
    page_category: str = "",
    diff_summary_lower: str = "",
) -> str:
    """Apply type-specific corrections to a classified signal.

    This is the SINGLE SOURCE OF TRUTH for signal type corrections.
    Both filter_signals.py and enrich_signals_openai.py call this function.

    Args:
        current_type: The current signal type (e.g. "exit_announced", "deal_announced")
        text_lower: Lowercased combined text (title + what_changed or similar)
        title_lower: Lowercased title only
        page_category: Page category (e.g. "PORTFOLIO", "NEWS", "CAREERS")
        diff_summary_lower: Lowercased diff_summary (for portfolio extraction detection)

    Returns:
        Corrected signal type.
    """
    if current_type == "exit_announced":
        return correct_exit(text_lower, title_lower, page_category)

    if current_type == "deal_announced":
        return correct_deal(text_lower, title_lower, diff_summary_lower)

    if current_type == "fund_launch":
        return correct_fund_launch(text_lower, title_lower)

    if current_type == "fundraise_announced":
        return correct_fundraise(text_lower, title_lower)

    if current_type == "people_move":
        return correct_people_move(text_lower, title_lower)

    if current_type == "report":
        return correct_report(text_lower, title_lower)

    if current_type == "partnership":
        return correct_partnership(text_lower, title_lower)

    # Portfolio update correction
    if current_type == "portfolio_update":
        # Guard: if portfolio company is the acquirer, KEEP as portfolio_update even when
        # acquisition verbs are present in the title. Without this guard the enricher would
        # re-demote "[Fund]-backed [Co] acquires X" back to deal_announced after the filter
        # correctly classified it as portfolio_update.
        if _RE_PORTFOLIO_CO_AS_ACQUIRER.search(text_lower):
            # Still allow exit reclassification if the portfolio company is being sold
            if _RE_STRONG_EXIT_VERBS.search(text_lower):
                return "exit_announced"
            return "portfolio_update"
        # Generic portfolio_update with deal verbs in title → reclassify as deal
        # (fund making a new investment that was initially tagged as portfolio update)
        if _RE_ACQUISITION_VERBS.search(title_lower) or _RE_INVEST_VERBS.search(title_lower):
            return "deal_announced"
        if _RE_STRONG_EXIT_VERBS.search(text_lower):
            return "exit_announced"
        # "announces the sale" / "agreement to sell" → exit
        if re.search(r"\b(?:announc\w+\s+the\s+sale|agreement\s+to\s+sell|completes?\s+(?:the\s+)?sale)\b", text_lower):
            return "exit_announced"
        return current_type

    # For fundraise_closed, check company round and chiude_raccolta
    if current_type == "fundraise_closed":
        result = correct_fundraise_to_deal_for_company_round(text_lower)
        if result:
            return result
        return current_type

    # Rescue "other" signals that have clear type indicators
    # These were demoted but may have been over-demoted
    if current_type == "other":
        # "names X as [role]" / "appoints X as [role]" → people_move
        if re.search(r"\b(?:names?|appoints?|appointed|hired?)\b.*\b(?:head|director|partner|managing|chief|ceo|cfo|coo|cto|president|chairman)\b", text_lower):
            return "people_move"
        # Standalone professional title signal: title IS the person + role, no PE verbs.
        # Catches "Michele Romualdi managing director, Head of Investor Relations" and similar
        # signals where a website lists personnel with no transactional verb.
        if re.search(
            r"\b(?:managing\s+director|head\s+of|chief\s+\w+\s+officer|partner|president"
            r"|vice\s+president|director\s+of|responsabile\s+(?:di|del|della))\b",
            title_lower,
        ) and not re.search(
            r"\b(?:fund|fondo|capital|sgr|invest|acqui|rais|portfolio|raises?|launch|exit)\b",
            title_lower,
        ):
            return "people_move"
        # "offers €XXM for" / "bids for" → deal_announced
        if _RE_OFFER_BID.search(text_lower) and re.search(r"[€$£]\s*\d+", text_lower):
            return "deal_announced"
        # Strong deal verbs with monetary amounts → deal_announced
        if _RE_ACQUISITION_VERBS.search(text_lower) and re.search(r"[€$£]\s*\d+", text_lower):
            return "deal_announced"

    return current_type


def detect_all_signal_types(signal: dict) -> list[str]:
    """Detect all signal types present in a signal's text.

    Returns a list where the first element is the primary signal_type and
    subsequent elements are additional types detected in the text. Only
    secondary types that differ from the primary are included.

    Example: a signal about D-Orbit raising €110M where Indaco exits would
    return ["fundraise_closed", "exit_announced"].
    """
    primary = signal.get("signal_type") or "other"
    text = (
        (signal.get("title") or "") + " " + (signal.get("what_changed") or "")
    ).lower()

    result: list[str] = [primary]

    def _add_if_new(stype: str) -> None:
        if stype != primary and stype not in result:
            result.append(stype)

    # exit_announced
    if _RE_EXIT_VERBS.search(text):
        _add_if_new("exit_announced")

    # fundraise_closed
    if _RE_FUNDRAISE_CLOSING.search(text):
        _add_if_new("fundraise_closed")

    # fundraise_announced — only if no closing verbs (avoid duplicate with fundraise_closed)
    if _RE_FUNDRAISE_VERBS_FULL.search(text) and not _RE_FUNDRAISE_CLOSING.search(text):
        _add_if_new("fundraise_announced")

    # people_move
    if _RE_PEOPLE_TITLE.search(text) or _RE_PEOPLE_LANGUAGE.search(text):
        _add_if_new("people_move")

    # debt_financing
    if _RE_BOND_ISSUANCE.search(text):
        _add_if_new("debt_financing")

    # deal_announced
    if _RE_ACQUISITION_VERBS.search(text) or _RE_INVEST_VERBS.search(text):
        _add_if_new("deal_announced")

    return result
