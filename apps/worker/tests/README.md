# Worker Tests

Unit and regression tests for the worker (`test_*.py` in this directory).

## Running Tests

```bash
cd apps/worker
source .venv/bin/activate

pytest                                        # Run all tests
pytest tests/test_differ.py                   # Run one file
pytest tests/test_signal_classification.py -v # Classification contract, verbose
```

CI runs `ruff check .` and `pytest -v` from `apps/worker` (`.github/workflows/ci.yml`).

## Test Data

- `fixtures/` — sample HTML pages for extractor tests
- `baselines/` — expected extraction output for regression tests (`test_regression.py`). Regenerate with `python -m fundradar_worker.cli generate-baselines --overwrite`.
- `conftest.py` — shared fixtures

## Signal Classification Suite

`test_signal_patterns.py`, `test_signal_corrections.py` and `test_signal_classification.py` cover signal classification. `test_signal_classification.py` is the canonical contract. Every classification change must break a test or add one. Details: [`apps/worker/CLAUDE.md`](../CLAUDE.md#signal-classification-test-suite).

## Adding New Tests

1. Create `test_<module>.py`.
2. Add fixtures to `fixtures/` if needed.
3. Add baseline files to `baselines/` for regression tests.
