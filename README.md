# FinAlly — AI Trading Workstation

A Bloomberg-inspired trading terminal with live market data, a simulated portfolio, and an AI assistant that can analyze positions and execute trades through natural language.

Built as a capstone project for an agentic AI coding course — the entire codebase is produced by orchestrated AI agents.

## What It Does

- **Live price streaming** — prices flash green/red on each tick via SSE
- **Simulated portfolio** — $10,000 virtual cash, buy/sell at market price, instant fill
- **Portfolio visualizations** — treemap heatmap, P&L chart, positions table with unrealized P&L
- **AI chat assistant** — ask questions, get analysis, have the AI execute trades and manage your watchlist automatically
- **10 default tickers** — AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (TypeScript, static export) |
| Backend | FastAPI (Python, `uv`) |
| Database | SQLite (lazy-initialized, volume-mounted) |
| Real-time | Server-Sent Events (SSE) |
| AI | LiteLLM → OpenRouter (Cerebras inference) |
| Market data | GBM simulator (default) or Polygon.io REST (optional) |
| Runtime | Single Docker container, port 8000 |

## Quick Start

```bash
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env
```

**macOS/Linux:**
```bash
./scripts/start_mac.sh
```

**Windows:**
```powershell
.\scripts\start_windows.ps1
```

Open `http://localhost:8000`. No login required.

To stop:
```bash
./scripts/stop_mac.sh        # macOS/Linux
.\scripts\stop_windows.ps1   # Windows
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter key for AI chat |
| `MASSIVE_API_KEY` | No | Polygon.io key for real market data (simulator used if absent) |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (testing) |

## Project Structure

```
finally/
├── frontend/        # Next.js TypeScript app (static export)
├── backend/         # FastAPI Python app (uv project)
│   └── app/market/  # Market data subsystem (complete)
├── scripts/         # Start/stop Docker scripts
├── test/            # Playwright E2E tests
├── db/              # SQLite volume mount target
├── planning/        # Agent documentation and project plan
└── Dockerfile       # Multi-stage build (Node → Python)
```

## Development Status

| Component | Status |
|---|---|
| Market data backend (simulator + Massive API, SSE, cache) | Complete — 73 tests passing |
| REST API (portfolio, watchlist, chat, health) | Pending |
| LLM integration (chat + trade execution) | Pending |
| Frontend (trading terminal UI) | Pending |
| Docker build + start scripts | Pending |
| E2E tests | Pending |

## Running Backend Tests

```bash
cd backend
uv run pytest
```

To see the market data simulator in action:

```bash
uv run market_data_demo.py
```
