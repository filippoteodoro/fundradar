"""
LinkedIn data integration module for Fundradar.

This module provides scraping capabilities for LinkedIn company feeds and
employee data using Apify actors, along with classifiers for extracting
signals from posts and analyzing employee backgrounds.
"""

from .apify_client import ApifyClient, ApifyConfig
from .posts_scraper import LinkedInPostsScraper, LinkedInPost
from .people_scraper import LinkedInPeopleScraper, LinkedInEmployee, LinkedInProfile
from .post_classifier import PostClassifier, ClassifiedPost, SignalType
from .profile_classifier import ProfileClassifier, ClassifiedProfile, BackgroundType
from .people_stats import FundPeopleStats, PeopleStatsCalculator

__all__ = [
    "ApifyClient",
    "ApifyConfig",
    "LinkedInPostsScraper",
    "LinkedInPost",
    "LinkedInPeopleScraper",
    "LinkedInEmployee",
    "LinkedInProfile",
    "PostClassifier",
    "ClassifiedPost",
    "SignalType",
    "ProfileClassifier",
    "ClassifiedProfile",
    "BackgroundType",
    "FundPeopleStats",
    "PeopleStatsCalculator",
]
