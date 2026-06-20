"""Tests for SSE streaming endpoint."""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


def _make_request(disconnect_after: int = 0) -> MagicMock:
    """Return a mock Request whose is_disconnected() returns True after N calls."""
    request = MagicMock()
    request.client = None  # suppresses IP logging

    call_count = 0

    async def is_disconnected() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > disconnect_after

    request.is_disconnected = is_disconnected
    return request


@pytest.mark.asyncio
class TestGenerateEvents:
    """Tests for the _generate_events async generator."""

    async def test_first_event_is_retry_directive(self):
        """SSE stream must open with a retry directive."""
        cache = PriceCache()
        request = _make_request(disconnect_after=0)  # disconnect immediately

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        assert events[0] == "retry: 1000\n\n"

    async def test_disconnects_cleanly_with_no_data(self):
        """Generator stops immediately when client disconnects with empty cache."""
        cache = PriceCache()
        request = _make_request(disconnect_after=0)

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        # Only the retry directive — no data events (cache is empty)
        assert events == ["retry: 1000\n\n"]

    async def test_emits_data_event_when_cache_has_prices(self):
        """A data event with JSON payload is emitted when cache has prices."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = _make_request(disconnect_after=1)  # one iteration before disconnect

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        assert len(events) == 2
        assert events[0] == "retry: 1000\n\n"
        assert events[1].startswith("data: ")
        payload = json.loads(events[1][len("data: "):].strip())
        assert "AAPL" in payload
        assert payload["AAPL"]["price"] == 190.50
        assert payload["AAPL"]["ticker"] == "AAPL"

    async def test_data_event_includes_all_cache_fields(self):
        """Each ticker in the payload contains all expected fields."""
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        cache.update("AAPL", 191.00)  # second update so direction is "up"
        request = _make_request(disconnect_after=1)

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        payload = json.loads(events[1][len("data: "):].strip())
        aapl = payload["AAPL"]
        assert aapl["ticker"] == "AAPL"
        assert aapl["price"] == 191.00
        assert aapl["previous_price"] == 190.00
        assert aapl["direction"] == "up"
        assert "change" in aapl
        assert "change_percent" in aapl
        assert "timestamp" in aapl

    async def test_no_duplicate_events_when_version_unchanged(self):
        """Generator skips sending when the cache version has not changed."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        # Allow two disconnect-check iterations but cache won't change between them
        request = _make_request(disconnect_after=2)

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        # retry + exactly one data event (second iteration: version unchanged → no yield)
        assert len(events) == 2

    async def test_new_data_event_after_cache_update(self):
        """A second data event is emitted after a new price is written to cache."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)

        call_count = 0

        async def is_disconnected() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                # Update cache between iterations so version changes
                cache.update("AAPL", 191.00)
            return call_count > 2

        request = MagicMock()
        request.client = None
        request.is_disconnected = is_disconnected

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        # retry + two data events (two distinct versions)
        assert len(events) == 3

    async def test_no_data_event_when_cache_is_empty(self):
        """Generator does not yield a data event when get_all() returns empty dict."""
        cache = PriceCache()  # empty
        request = _make_request(disconnect_after=1)

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        # Initial version is 0 != last_version(-1), so it checks cache.
        # Cache is empty → if prices: is False → no data event.
        assert events == ["retry: 1000\n\n"]

    async def test_cancelled_error_is_handled_cleanly(self):
        """CancelledError stops the generator without propagating."""
        cache = PriceCache()

        async def is_disconnected() -> bool:
            raise asyncio.CancelledError()

        request = MagicMock()
        request.client = None
        request.is_disconnected = is_disconnected

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        # Should complete without raising; only the retry directive was yielded
        assert events == ["retry: 1000\n\n"]

    async def test_multiple_tickers_in_payload(self):
        """All tickers in the cache appear in the SSE payload."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        cache.update("GOOGL", 175.25)
        cache.update("MSFT", 420.00)
        request = _make_request(disconnect_after=1)

        events = []
        async for event in _generate_events(cache, request, interval=0):
            events.append(event)

        payload = json.loads(events[1][len("data: "):].strip())
        assert set(payload.keys()) == {"AAPL", "GOOGL", "MSFT"}


class TestCreateStreamRouter:
    """Tests for the create_stream_router factory."""

    def test_returns_api_router(self):
        """Factory returns a FastAPI APIRouter."""
        from fastapi import APIRouter

        cache = PriceCache()
        router = create_stream_router(cache)
        assert isinstance(router, APIRouter)

    def test_router_has_prices_route(self):
        """Returned router contains the /prices route."""
        cache = PriceCache()
        router = create_stream_router(cache)
        paths = [route.path for route in router.routes]
        assert "/api/stream/prices" in paths

    def test_each_call_returns_fresh_router(self):
        """Multiple calls produce independent routers (no shared state)."""
        cache = PriceCache()
        router_a = create_stream_router(cache)
        router_b = create_stream_router(cache)
        assert router_a is not router_b
        # Each router has exactly one route
        assert len(router_a.routes) == 1
        assert len(router_b.routes) == 1
