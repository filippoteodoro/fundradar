# Site Configuration Schema

Per-site YAML configurations for customized scraping behavior.

## Overview

Site configs allow you to specify extraction rules for individual fund websites. When a config exists for a domain, it takes precedence over generic heuristic extraction.

Config files are stored in `data/site_configs/` with the naming convention `{domain}.yaml`.

## Schema

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domain` | string | Yes | Domain name (without protocol) |
| `name` | string | No | Human-readable name |
| `notes` | string | No | Notes about the site |
| `requires_headless` | boolean | No | Whether Playwright is required |
| `wait` | WaitConfig | No | Page load wait conditions |
| `scroll` | ScrollConfig | No | Scrolling behavior |
| `consent` | ConsentConfig | No | Cookie consent handling |
| `portfolio` | PortfolioConfig | No | Portfolio page extraction |
| `team` | TeamConfig | No | Team page extraction |
| `news` | NewsConfig | No | News page extraction |
| `metadata` | object | No | Additional custom data |

### WaitConfig

```yaml
wait:
  for_selector: ".portfolio-grid"  # Wait for this selector
  for_network_idle: true           # Wait for network to be idle
  timeout_ms: 10000                # Max wait time
  delay_ms: 500                    # Extra delay after load
```

### ScrollConfig

```yaml
scroll:
  enabled: true
  max_scrolls: 10
  pause_ms: 500
  scroll_to_selector: ".load-more"  # Scroll until this appears
```

### PaginationConfig

```yaml
# URL-based pagination
pagination:
  type: url_based
  url_pattern: "/portfolio?page={page}"
  start_page: 1
  max_pages: 10

# Click-to-load pagination
pagination:
  type: click_to_load
  load_more_selector: "button.load-more"
  max_clicks: 10

# Infinite scroll
pagination:
  type: infinite_scroll
  no_more_items_selector: ".end-of-list"
```

### SelectorConfig

```yaml
selectors:
  container: ".portfolio-grid"  # Parent element
  item: ".portfolio-card"       # Individual items
  name: "h3"                    # Name within item
  description: "p.description"
  sector: ".tag"
  website: "a[href^='http']"
  status: ".status"
  image: "img"
  title: ".job-title"           # Team-specific
  role: ".role"
  linkedin: "a[href*='linkedin']"
  email: "a[href^='mailto:']"
```

### PortfolioConfig

```yaml
portfolio:
  url_path: /portfolio
  selectors:
    # See SelectorConfig above
  strategies:
    - next_data
    - html_cards
    - logo_grid
  pagination:
    # See PaginationConfig above
  exclude_patterns:
    - "^Privacy"
    - "^Cookie"
  exited_section_selector: ".exited"
  exited_indicator: "exited"
```

### TeamConfig

```yaml
team:
  url_path: /team
  selectors:
    # See SelectorConfig above
  strategies:
    - team_cards
    - h3_with_title
  pagination:
    type: none
  section_selector: ".team-section"
  section_title_selector: "h2"
```

### ConsentConfig

```yaml
consent:
  accept_selector: "#accept-cookies"
  wait_for_modal: true
  modal_timeout_ms: 3000
  skip: false
```

## Extraction Strategies

Strategies are tried in order until one succeeds.

### Portfolio Strategies

| Strategy | Description |
|----------|-------------|
| `next_data` | Extract from `__NEXT_DATA__` script |
| `nuxt_data` | Extract from `__NUXT__` or Nuxt hydration |
| `json_ld` | Extract from JSON-LD structured data |
| `html_cards` | Extract from card-like HTML elements |
| `logo_grid` | Extract from logo/image grids |
| `link_list` | Extract from lists of links |
| `headings_in_context` | Extract from headings in portfolio context |
| `table_rows` | Extract from table rows |
| `attributes` | Extract from data attributes |
| `svg_titles` | Extract from SVG titles |
| `noscript` | Extract from noscript fallback |
| `anchor_wrappers` | Extract from anchor wrappers around images |

### Team Strategies

| Strategy | Description |
|----------|-------------|
| `team_cards` | Extract from team card elements |
| `h3_with_title` | Extract from h3 with following title |
| `json_ld_person` | Extract from JSON-LD Person data |

## Example Configurations

### Next.js SPA with Infinite Scroll

```yaml
domain: nextgen-partners.it
name: NextGen Partners
requires_headless: true

wait:
  for_selector: "[data-testid='portfolio-list']"
  timeout_ms: 15000

scroll:
  enabled: true
  max_scrolls: 5

portfolio:
  url_path: /portfolio
  selectors:
    container: ".portfolio-grid"
    item: ".portfolio-card"
    name: "h3"
    sector: ".tag"
    website: "a[target='_blank']"
  strategies:
    - next_data
    - html_cards
  pagination:
    type: infinite_scroll
```

### WordPress Site

```yaml
domain: capitalpartners-italia.it
name: Capital Partners Italia
requires_headless: false

portfolio:
  url_path: /portfolio
  selectors:
    container: ".portfolio-list"
    item: "article.portfolio-company"
    name: "h3"
    sector: ".sector"
    description: ".excerpt"
  strategies:
    - html_cards
    - headings_in_context

news:
  url_path: /news
  article_selector: "article.post"
  title_selector: ".entry-title a"
  date_selector: ".post-date"
  link_selector: ".entry-title a"
  pagination:
    type: url_based
    url_pattern: "/news/page/{page}"
    max_pages: 5
```

### Static HTML Site

```yaml
domain: investimenti-capital.it
name: Investimenti Capital Partners
requires_headless: false

portfolio:
  url_path: /portfolio
  selectors:
    container: ".portfolio-list"
    item: ".portfolio-company"
    name: "h3"
    sector: ".sector"
    website: "a.website"
    description: ".description"
  strategies:
    - html_cards
  exited_section_selector: ".exited"
  exited_indicator: "exited"
```

## Validation

Use the CLI to validate a config against the live site:

```bash
python -m fundradar_worker.cli validate-site example-fund.it
```

This will:
1. Load the config from `data/site_configs/example-fund.it.yaml`
2. Fetch the site (using Playwright if required)
3. Run extraction with configured selectors
4. Report success/failure per field
5. Output sample extracted data
