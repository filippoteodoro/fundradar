"""
Extraction strategies for different website structures.

Each strategy handles a specific way websites present data:
- NEXT_DATA: Next.js __NEXT_DATA__ JSON
- NUXT_DATA: Nuxt.js payload
- JSON_LD: Schema.org structured data
- HTML_CARDS: Card-based layouts
- LOGO_GRID: Image/logo grids
- LINK_LIST: Simple link lists
- TABLE_ROWS: Table-based layouts
- TEAM_CARDS: Team member cards
"""

from .next_data_strategy import (
    extract_from_next_data,
    extract_portfolio_from_next_data,
    extract_team_from_next_data,
)
from .html_cards_strategy import (
    extract_from_html_cards,
    extract_portfolio_from_cards,
    extract_team_from_cards,
)
from .logo_grid_strategy import (
    extract_from_logo_grid,
    extract_companies_from_logos,
)
from .json_ld_strategy import (
    extract_from_json_ld,
    extract_organizations_from_json_ld,
    extract_people_from_json_ld,
)

__all__ = [
    "extract_from_next_data",
    "extract_portfolio_from_next_data",
    "extract_team_from_next_data",
    "extract_from_html_cards",
    "extract_portfolio_from_cards",
    "extract_team_from_cards",
    "extract_from_logo_grid",
    "extract_companies_from_logos",
    "extract_from_json_ld",
    "extract_organizations_from_json_ld",
    "extract_people_from_json_ld",
]
