"""
Specialized extractors for fund website data.

Each extractor handles a specific type of data:
- PortfolioExtractor: Portfolio companies (current and exited)
- TeamExtractor: Team members with roles and contact info
- NewsExtractor: News/press items with article URLs and dates
"""

from .portfolio_extractor import PortfolioExtractor, ExtractedCompany
from .team_extractor import TeamExtractor, ExtractedTeamMember
from .news_extractor import NewsExtractor, ExtractedNewsItem

__all__ = [
    "PortfolioExtractor",
    "ExtractedCompany",
    "TeamExtractor",
    "ExtractedTeamMember",
    "NewsExtractor",
    "ExtractedNewsItem",
]
