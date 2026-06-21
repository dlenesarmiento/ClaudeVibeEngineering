# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, plus properties `change`, `change_percent`, `direction` ("up"/"down"/"flat"), and `to_dict()` for JSON serialization.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None) -> PriceUpdate`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)`
  - `version` property — monotonic counter, increments on every update (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set, otherwise `SimulatorDataSource`.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Test Suite

**88 tests, 99% coverage** across 7 modules in `tests/market/`.

| Module | Tests | Notes |
|--------|-------|-------|
| test_models.py | 11 | 100% — all properties, immutability, serialisation |
| test_cache.py | 13 | 100% — version counter, direction logic, thread-safe ops |
| test_simulator.py | 17 | 100% — GBM math, Cholesky correlations, tick bounds |
| test_simulator_source.py | 13 | async integration, exception resilience, ticker normalisation |
| test_factory.py | 7 | 100% — all env var cases, cache injection |
| test_massive.py | 13 | 94% — REST polling, tick normalisation |
| test_stream.py | 12 | 97% — SSE format, retry directive, version dedup, teardown |

```bash
uv run pytest -v                          # All tests
uv run pytest --cov=app/market            # With coverage report
uv run ruff check app/ tests/             # Lint
```

## Demo

A Rich terminal dashboard showing live simulated prices, sparklines, and event log:

```bash
uv run market_data_demo.py
```

Runs for 60 seconds (or until Ctrl+C), then prints a session summary comparing final prices to seed prices.
