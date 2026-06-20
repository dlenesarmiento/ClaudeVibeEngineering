# Market Data Component — Code Review

**Date:** 2026-06-20
**Reviewer:** Claude Sonnet 4.6 (independent review)
**Scope:** `backend/app/market/` (8 source files) and `backend/tests/market/` (6 test modules, 73 tests)

---

## 1. Test Run Results

```
Platform: Linux, Python 3.13.7, pytest 9.0.2
73 tests collected → 73 passed, 0 failed, 0 errors
Runtime: 3.54s
Linter (ruff): All checks passed
```

### Coverage by Module

| Module | Stmts | Cover | Missing Lines |
|--------|-------|-------|---------------|
| `models.py` | 26 | **100%** | — |
| `cache.py` | 39 | **100%** | — |
| `factory.py` | 15 | **100%** | — |
| `interface.py` | 13 | **100%** | — |
| `seed_prices.py` | 8 | **100%** | — |
| `massive_client.py` | 67 | **94%** | 85-87, 125 |
| `simulator.py` | 139 | **98%** | 149, 268-269 |
| `stream.py` | 36 | **33%** | 26-48, 62-87 |
| **TOTAL** | **349** | **91%** | |

**Note on previous review:** An earlier review (2026-02-10) reported 5 test failures and 84% coverage. All previously reported issues have been resolved: `pyproject.toml` build config added, lazy imports moved to module top level, return type annotation fixed, unused imports removed, and Massive test mocks corrected. The current state is clean.

---

## 2. Architecture Assessment

The strategy pattern is well-executed:

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key)
└── MassiveDataSource    →  Polygon.io REST poller (MASSIVE_API_KEY set)
        │
        ▼
   PriceCache (thread-safe, in-memory)
        │
        ├──→ SSE stream  (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

**Strengths:**
- Clean separation across 8 focused modules with a well-defined public API in `__init__.py`
- `PriceCache` as single source of truth decouples producers from consumers — downstream code never calls the data source directly
- Immutable `PriceUpdate` (`frozen=True, slots=True`) crosses thread boundaries safely
- Both data sources seed the cache at `start()`, so SSE clients get data on the first tick with no visible empty state
- Background tasks are properly cancellable and `stop()` is idempotent in both implementations
- SSE version-based change detection avoids redundant payloads when the cache hasn't changed
- `asyncio.to_thread()` correctly wraps the synchronous Massive `RESTClient`

---

## 3. Issues Found

### 3.1 SSE Endpoint Has No Tests (Severity: Medium)

`stream.py` is at 33% coverage. Neither `stream_prices()` nor `_generate_events()` have any tests. The uncovered lines (26-48, 62-87) include:

- The `StreamingResponse` construction and response headers
- The `retry: 1000\n\n` reconnection directive
- The disconnect detection loop (`request.is_disconnected()`)
- Version comparison and change-gated publish
- JSON serialisation of the full price snapshot
- `CancelledError` handling on stream teardown

This is the primary consumer-facing code path — every frontend price update goes through it. The SSE layer should have at least basic integration tests. An `httpx.AsyncClient` with a `TestClient` wrapper (or `starlette.testclient.TestClient`) can exercise the async generator without a running server.

**Recommendation:** Add tests for: correct event format (`data: {...}\n\n`), `retry` header on connect, no duplicate events when version unchanged, clean shutdown on client disconnect.

### 3.2 Ticker Normalisation Inconsistency (Severity: Low)

`MassiveDataSource.add_ticker()` and `remove_ticker()` both call `.upper().strip()` on the ticker before processing. `SimulatorDataSource.add_ticker()` and `remove_ticker()` do not normalise — they pass the ticker directly to `GBMSimulator`.

If the upstream API layer sends `"aapl"` instead of `"AAPL"`, the two sources behave differently. Under the Simulator, the ticker would be tracked as `"aapl"` (not matching seed prices, getting a random initial price). Under Massive, it would be normalised to `"AAPL"`. This is a latent correctness bug if the API layer ever passes un-normalised tickers.

**Recommendation:** Add `.upper().strip()` normalisation to `SimulatorDataSource.add_ticker()` and `remove_ticker()`.

### 3.3 Module-Level Router in `stream.py` (Severity: Low)

`router = APIRouter(prefix="/api/stream", tags=["streaming"])` is defined at module scope (line 17). `create_stream_router()` registers `@router.get("/prices")` on this shared singleton. If `create_stream_router()` is called more than once (e.g., in a test suite that re-imports the module), routes accumulate on the same router object, causing duplicate route registration.

In production this is called exactly once, so it doesn't break today. But the factory function implies a fresh router per call.

**Recommendation:** Move `router = APIRouter(...)` inside `create_stream_router()`.

### 3.4 Exception Handler in `_run_loop` Not Covered (Severity: Low)

`simulator.py` lines 268-269 are the `except Exception` block inside `SimulatorDataSource._run_loop`. `test_exception_resilience` verifies the task is still running after some time, but it doesn't inject a fault that triggers the exception branch. The handler itself — `logger.exception("Simulator step failed")` — is never exercised.

**Recommendation:** Add a test that patches `GBMSimulator.step` to raise an exception and verifies the loop continues producing updates.

### 3.5 Dead Guard in `_add_ticker_internal` (Severity: Info)

`simulator.py` line 149 is `if ticker in self._prices: return` inside `_add_ticker_internal`. This is unreachable because every caller (`add_ticker`) already checks `if ticker in self._prices` before calling this method. The line is 0% covered for this reason.

**Recommendation:** Remove the redundant guard from `_add_ticker_internal`.

### 3.6 TSLA in `CORRELATION_GROUPS["tech"]` is Dead Data (Severity: Info)

`seed_prices.py` line 39 includes `"TSLA"` in `CORRELATION_GROUPS["tech"]`. However, `GBMSimulator._pairwise_correlation()` special-cases TSLA before checking group membership:

```python
if t1 == "TSLA" or t2 == "TSLA":
    return TSLA_CORR  # 0.3 — fires before tech-group check
```

TSLA's membership in the tech group never has any effect. This could mislead a maintainer who removes the special-case expecting TSLA to inherit tech-sector correlation (0.6).

**Recommendation:** Remove TSLA from `CORRELATION_GROUPS["tech"]`, or add a comment explaining why it is listed there but overridden.

### 3.7 `version` Property Reads Without Lock (Severity: Info)

`cache.py` line 66:
```python
@property
def version(self) -> int:
    return self._version
```

`_version` is read without acquiring `self._lock`. Under CPython with the GIL, reading a Python `int` is atomic, so there is no practical risk. However, it is inconsistent with the rest of the class. On a future no-GIL build (Python 3.13t+, PEP 703), this would be a data race.

**Recommendation:** Either acquire the lock (adds negligible overhead) or add a comment noting the intentional GIL reliance.

---

## 4. Test Quality Assessment

### What Is Well-Tested

| Module | Assessment |
|--------|-----------|
| `test_models.py` (11 tests) | Thorough — creation, all computed properties, edge case (zero previous price), immutability, serialisation |
| `test_cache.py` (13 tests) | Thorough — all public methods, direction logic, version counter, rounding, `__len__`, `__contains__` |
| `test_simulator.py` (17 tests) | Good — GBM math (positivity over 10k steps), add/remove, all correlation pairs, Cholesky rebuild, `DEFAULT_DT` bounds |
| `test_simulator_source.py` (10 tests) | Good async integration — start seeds cache, prices update over time, idempotent stop, dynamic add/remove |
| `test_factory.py` (7 tests) | Complete — all env var cases (missing, empty, whitespace, valid), cache injection verified |
| `test_massive.py` (13 tests) | Good mocking strategy — `patch.object(source, "_fetch_snapshots")` is the right level of isolation |

### Gaps

1. **SSE streaming** — no tests (see Finding 3.1)
2. **Concurrent PriceCache access** — no multi-threaded tests to empirically verify lock correctness
3. **Full 10-ticker Cholesky** — tests use 1-2 tickers; a test with all 10 default tickers would verify the full correlation matrix is positive-definite
4. **`_run_loop` exception path** — not triggered by any test (see Finding 3.4)

---

## 5. Remaining Coverage Gaps Explained

| Module | Uncovered | Reason |
|--------|-----------|--------|
| `massive_client.py:85-87` | `_poll_loop` while-body | `test_stop_cancels_task` starts then immediately stops; the 10s interval means the loop body never fires |
| `massive_client.py:125` | `_fetch_snapshots` return | All tests mock `_fetch_snapshots` directly — correct for unit tests; real REST call untested by design |
| `simulator.py:149` | Duplicate guard | Unreachable — callers already guard before calling `_add_ticker_internal` |
| `simulator.py:268-269` | Exception handler | Never triggered — `step()` has never been made to raise in tests |
| `stream.py:26-48,62-87` | Entire route handler + generator | No SSE tests exist |

---

## 6. Verdict

The market data component is **solid and production-ready for its core logic**. The GBM simulator is mathematically correct, the thread-safety model is sound, the strategy pattern is clean, and all previously identified issues from the February review have been resolved. 91% overall coverage with 73 green tests is a strong baseline.

**The one meaningful open gap is the untested SSE layer.** For a trading workstation where live price streaming is the central user experience, this should be addressed before integration with the frontend is considered done.

### Priority Action List

| Priority | Action |
|----------|--------|
| Should fix | Add SSE integration tests (Finding 3.1) |
| Should fix | Normalise tickers in `SimulatorDataSource` (Finding 3.2) |
| Nice to have | Move `router` inside `create_stream_router()` (Finding 3.3) |
| Nice to have | Add test that triggers the `_run_loop` exception branch (Finding 3.4) |
| Cleanup | Remove dead guard in `_add_ticker_internal` (Finding 3.5) |
| Cleanup | Clarify TSLA in `CORRELATION_GROUPS` (Finding 3.6) |
