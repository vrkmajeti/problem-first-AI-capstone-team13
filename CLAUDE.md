# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Intraday Cross-Impact Catalyst Briefings** — a financial news synthesis tool that watches a set of stock tickers and generates intraday catalyst briefings by combining direct company news, deduplication memory, and an exposure graph that routes external events (e.g., Taiwan earthquake → AAPL via TSMC supply chain) to watched tickers.

Three design iterations:
1. **Iteration 1** — Direct ticker-tagged news synthesis via Finnhub
2. **Iteration 2** — Adds in-memory ledger to suppress duplicates and detect meaningful updates
3. **Iteration 3** — Adds Currents broad-news API + exposure graph cross-impact routing

## Commands

### Backend

```powershell
# Setup
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt --only-binary sqlean-py  # --only-binary required on Windows
copy backend/.env.example backend/.env   # then fill in API keys

# Run
python -m backend.main                   # FastAPI at http://localhost:8000

# Tests (run from repo root with venv active)
python -m unittest backend/run_tests.py

# Single test
python -m unittest backend.run_tests.TestWorkflow.test_iteration_1_direct_news
python -m unittest backend.run_tests.TestWorkflow.test_iteration_2_ledger_duplicates
python -m unittest backend.run_tests.TestWorkflow.test_iteration_3_cross_impact_routing
```

### Frontend

```powershell
cd frontend
npm install
npm run dev       # Vite dev server at http://localhost:5173
npm run build     # Production build
npm run lint      # TypeScript + ESLint
```

### Tracing (optional)

```powershell
python -m phoenix.server.main serve   # Arize Phoenix at http://localhost:6006
```

VS Code: Use the compound launch **"Full Application (Backend + Frontend + Tracing)"** (`.vscode/launch.json`).

## Architecture

### Pipeline (LangGraph, 6 nodes in `backend/graph.py`)

```
Node 1: fetch_and_filter_node     — Finnhub + Currents APIs, freshness filter
Node 2: canonical_event_extraction_node — LLM extracts structured events from articles
Node 3: routing_node              — direct routes + cross-impact via exposure graph
Node 4: ledger_memory_node        — embedding dedup, suppresses/flags updates
Node 5: per_ticker_synthesis_node — LLM generates one briefing per ticker
Node 6: compliance_gate_node      — regex scrubs financial-advice language
```

LLM handles extraction and explanation; all routing, graph traversal, dedup, and compliance are deterministic code.

### Key Backend Files

| File | Responsibility |
|---|---|
| `backend/main.py` | FastAPI server, 11 REST endpoints, in-memory watchlist/ledger state |
| `backend/graph.py` | LangGraph pipeline definition, state schema, mock/LLM branching |
| `backend/ingestion.py` | Finnhub and Currents API clients, freshness filter, `clean_summary()` |
| `backend/routing.py` | In-memory exposure graph, 2-hop BFS keyword expansion, DFS path scoring |
| `backend/memory.py` | Catalyst ledger, fastembed local embeddings, cosine/lexical dedup (threshold 0.75) |
| `backend/seed_data.py` | Static `EXPOSURE_GRAPH` (13 nodes/edges) and `SCENARIOS` (3 replay scenarios) |
| `backend/config.py` | Env vars, `get_llm()` / `get_llm_fast()` factory, Phoenix OpenTelemetry init |
| `backend/run_tests.py` | 3 unittest cases with mocked LLM (`@patch('backend.graph.get_llm')`) |
| `backend/persistence.py` | JSON file I/O — **built but not imported anywhere; watchlist/graph reset on every restart** |

### Frontend

`frontend/src/App.tsx` is a single 900+ line file containing all state, API calls, and UI rendering. The Vite dev server proxies `/api/*` to `http://localhost:8000` (`vite.config.ts`).

## LLM Fallback Chain

1. `GEMINI_API_KEY` set → Gemini 2.5-flash (extraction + synthesis)
2. `OPENAI_API_KEY` set → gpt-4.1-nano (extraction) + gpt-4o-mini (synthesis)
3. Neither → `MOCK_EVENTS` dict + rules-based synthesis (no API calls; used in tests)

If Node 2 extraction fails (rate-limit, timeout), `llm_failed=True` is set, downstream nodes produce no output, and `main.py` rolls back the ledger to its pre-run snapshot.

## Exposure Graph

- 13 nodes: 5 tickers (AAPL, MSFT, NVDA, TSM, DAL), intermediaries (Foxconn, Anthropic, OpenAI, Taiwan, Semiconductors, Frontier AI, Red Sea Shipping, Logistics Cost Risk)
- 13 edges with `confidence` (0.80–0.99) and `type` (supplier_of, technology_exposure, regional_exposure, shipping_exposure, macro_sensitivity)
- Cross-impact routing: DFS up to 3 hops; route fires if `event_severity × avg_edge_confidence × path_shortness_bonus ≥ 0.45`
- Modify via `seed_data.EXPOSURE_GRAPH` or runtime API (`POST /api/graph/node`, `POST /api/graph/edge`)

## Test Setup

Tests in `backend/run_tests.py` (`class TestWorkflow`):
- `setUp()` clears the ledger and rebuilds the LangGraph workflow before each test
- LLM is mocked via `@patch('backend.graph.get_llm')`; the mock inspects system/user message content to return correct fixture data
- Node 2 uses `MOCK_EVENTS` automatically when no API keys are present

## Known Limitations

- **Persistence not wired**: watchlist and exposure graph reset to hardcoded defaults on every backend restart (`persistence.py` exists but is unused)
- **No scheduled polling**: runs are manually triggered from the UI
- **Wide-open CORS**: `allow_origins=["*"]` — not for production
- **Freshness window**: default 10 min; capstone demo uses 120 min (`FRESHNESS_LOOKBACK_MINUTES` env var)
- **Embedding model download**: fastembed downloads `BAAI/bge-small-en-v1.5` (~50 MB) on first run
