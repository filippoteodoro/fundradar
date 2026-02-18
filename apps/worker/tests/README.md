# Worker Tests

Unit and integration tests for the Fundradar worker module.

## Test Files

| File | Tests |
|------|-------|
| `test_differ.py` | Page diff detection logic |
| `test_enrichment.py` | AI enrichment functions (comprehensive) |
| `test_fetcher.py` | HTTP fetching and caching |
| `test_ingest_pem.py` | PEM PDF parsing |
| `test_linkedin.py` | LinkedIn profile scraping |
| `test_playwright_fetcher.py` | Browser-based fetching |
| `test_regression.py` | Regression tests against known baselines |

## Test Data

### `/fixtures/`
Sample HTML pages and expected outputs for testing extractors.

### `/baselines/`
Snapshot baselines for regression testing - ensures extraction quality doesn't degrade.

## Running Tests

```bash
cd apps/worker

# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_differ.py

# Run with coverage
poetry run pytest --cov=fundradar_worker

# Run only fast unit tests (skip integration)
poetry run pytest -m "not integration"

# Verbose output
poetry run pytest -v
```

## Configuration

`conftest.py` contains shared fixtures:
- Mock HTTP responses
- Sample HTML content
- Test fund/company data

## Adding New Tests

1. Create test file: `test_<module>.py`
2. Add fixtures to `/fixtures/` if needed
3. Use `@pytest.mark.integration` for slow/network tests
4. Add baseline files to `/baselines/` for regression tests
