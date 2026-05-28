# Intraday Cross-Impact Catalyst Briefings

A full-stack demo that monitors a stock watchlist for breaking news, deduplicates duplicate story threads, routes untickered geopolitical events through a causal exposure graph, and synthesizes per-ticker briefings via an LLM pipeline.

Built with **LangGraph** (pipeline orchestration), **FastAPI** (backend API), **React + Vite** (dashboard), and **Arize Phoenix** (LLM tracing).

---

## Table of Contents

1. [How It Works](#how-it-works)
2. [Prerequisites](#prerequisites)
3. [API Keys](#api-keys)
4. [Local Setup](#local-setup)
5. [Running the Application](#running-the-application)
6. [Running with VS Code](#running-with-vs-code)
7. [Running Tests](#running-tests)
8. [The Three Pipeline Iterations](#the-three-pipeline-iterations)
9. [Environment Variable Reference](#environment-variable-reference)
10. [Repository Structure](#repository-structure)
11. [Troubleshooting](#troubleshooting)

---

## How It Works

Each pipeline run executes a six-node LangGraph workflow:

```
Fetch & Filter News
        ↓
Canonical Event Extraction  (LLM: gpt-4.1-nano / gemini-2.5-flash)
        ↓
Route Events to Tickers     (direct tag + exposure graph traversal)
        ↓
Ledger Memory Check         (cosine similarity deduplication)
        ↓
Per-Ticker Synthesis        (LLM: gpt-4o-mini / gemini-2.5-flash)
        ↓
Compliance Gate             (regex scrub of buy/sell language)
```

**No API keys?** The app runs in no-key mode using pre-baked mock events and rules-based synthesis. All three replay scenarios work fully offline.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | Earlier versions are untested |
| Node.js | 18.x | 20.x or later also works |
| npm | 9.x | Comes with Node.js |

Check your versions:

```bash
python --version
node --version
npm --version
```

---

## API Keys

The application uses up to four external API keys. **All are optional** — see the table below for what each one unlocks.

### Which keys do you actually need?

| Scenario | Keys required |
|----------|--------------|
| Run the three built-in replay scenarios with real LLM synthesis | One of: `GEMINI_API_KEY` **or** `OPENAI_API_KEY` |
| Run the three replay scenarios without any LLM (rules-based mock output) | None |
| Pull live company news from Finnhub | `FINNHUB_API_KEY` |
| Pull live cross-impact / geopolitical news from Currents | `CURRENTS_API_KEY` |

---

### `GEMINI_API_KEY` — Google Gemini (default LLM)

Used for: canonical event extraction (`gemini-2.5-flash`) and per-ticker synthesis (`gemini-2.5-flash`), plus embeddings for the deduplication ledger (`models/embedding-001`, 768 dimensions).

**How to get it:**
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with a Google account.
3. Click **Create API key** and copy the value.

The free tier is sufficient for all replay scenarios.

---

### `OPENAI_API_KEY` — OpenAI (alternative LLM)

Used for: canonical event extraction (`gpt-4.1-nano`) and per-ticker synthesis (`gpt-4o-mini`), plus embeddings (`text-embedding-3-small`, 1536 dimensions).

Set `LLM_PROVIDER=openai` in your `.env` to activate this path. If both keys are set, `LLM_PROVIDER` controls which one is used. If `GEMINI_API_KEY` is absent but `OPENAI_API_KEY` is present, the app automatically falls back to OpenAI regardless of `LLM_PROVIDER`.

**How to get it:**
1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Sign in and click **Create new secret key**.
3. Copy the value — it is only shown once.

You need a funded account (pay-as-you-go). Running all three replay scenarios costs well under $0.10.

---

### `FINNHUB_API_KEY` — Finnhub (live direct company news)

Used for: fetching real-time company-specific news in **Live Feeds** mode. Not needed for replay scenarios.

**How to get it:**
1. Go to [finnhub.io](https://finnhub.io) and click **Get free API key**.
2. Create a free account.
3. Your key appears on the dashboard immediately.

The free tier allows 60 API calls/minute, which is more than enough for this demo.

---

### `CURRENTS_API_KEY` — Currents API (live cross-impact news)

Used for: fetching broad geopolitical, macro, and technology news in **Live Feeds** mode with Iteration 3. Not needed for replay scenarios.

**How to get it:**
1. Go to [currentsapi.services](https://currentsapi.services/en/register).
2. Register a free account.
3. Your API key appears on the dashboard after email verification.

---

## Local Setup

Run all commands from the **repository root** unless noted otherwise.

### Step 1 — Clone the repository

```bash
git clone <repo-url>
cd problem-first-AI-capstone-team13
```

### Step 2 — Set up the Python backend

**Create and activate a virtual environment:**

```bash
# Create
python -m venv backend/.venv

# Activate — Windows PowerShell
.\backend\.venv\Scripts\Activate.ps1

# Activate — Windows CMD
backend\.venv\Scripts\activate.bat

# Activate — macOS / Linux
source backend/.venv/bin/activate
```

**Install Python dependencies:**

```bash
pip install -r backend/requirements.txt
```

**Create your `.env` file:**

```bash
# Windows
copy backend\.env.example backend\.env

# macOS / Linux
cp backend/.env.example backend/.env
```

Open `backend/.env` and fill in the keys you want to use:

```env
# At minimum, add one LLM key if you want real synthesis.
# Leave blank to run in no-key / mock mode.
GEMINI_API_KEY=your_key_here

# Only needed for the Live Feeds scenario
FINNHUB_API_KEY=your_key_here
CURRENTS_API_KEY=your_key_here
```

### Step 3 — Set up the React frontend

```bash
cd frontend
npm install
cd ..
```

---

## Running the Application

You need **two terminals** open from the repository root.

**Terminal 1 — Backend:**

```bash
# Activate the venv first if not already active (see Step 2 above)
python -m backend.main
```

The backend starts at `http://localhost:8000`.  
Arize Phoenix tracing dashboard starts at `http://localhost:6006`.

**Terminal 2 — Frontend:**

```bash
cd frontend
npm run dev
```

Open your browser to `http://localhost:5173`.

> The Vite dev server proxies all `/api/*` requests to `http://localhost:8000`, so both processes must be running.

---

## Running with VS Code

The `.vscode/launch.json` includes pre-configured debug/run configurations:

| Configuration | What it does |
|---|---|
| `Backend: FastAPI Server` | Starts Uvicorn with the FastAPI app |
| `Frontend: Vite React Server` | Runs `npm run dev` in `frontend/` |
| `Tracing: Arize Phoenix Server` | Starts the Phoenix collector separately |
| `Backend: Run Unit Tests` | Runs `backend/run_tests.py` |
| **`Full Application (Backend + Frontend + Tracing)`** | Launches all three servers at once |

**To start everything:**
1. Open the **Run and Debug** panel (`Ctrl+Shift+D` / `Cmd+Shift+D`).
2. Select **`Full Application (Backend + Frontend + Tracing)`** from the dropdown.
3. Click the green play button.

**Install dependencies first (one-time):**
- Open the Command Palette (`Ctrl+Shift+P`) → `Tasks: Run Task`.
- Run `Install Backend Requirements` then `Install Frontend Dependencies`.

---

## Running Tests

The test suite verifies the LangGraph workflow end-to-end: direct routing, duplicate suppression, and cross-impact graph traversal.

```bash
# From the repository root, with the venv active
python -m unittest backend/run_tests.py
```

Or via the VS Code launch config `Backend: Run Unit Tests`.

**What the tests cover:**

| Test | Scenario | Validates |
|------|----------|-----------|
| `test_iteration_1_direct_news` | `direct_news`, Iteration 1 | AAPL and MSFT are directly routed; syntheses are generated |
| `test_iteration_2_ledger_duplicates` | `duplicate_news`, Iteration 2 | Exactly 1 duplicate is suppressed for AAPL across 3 articles |
| `test_iteration_3_cross_impact_routing` | `cross_impact`, Iteration 3 | Taiwan earthquake → AAPL/NVDA/TSM; Anthropic launch → MSFT/NVDA; Red Sea → DAL |

Tests run with mocked LLM responses and do not require any API keys.

---

## The Three Pipeline Iterations

Select the iteration and scenario from the header dropdowns, then click **Fetch Catalysts**.

### Iteration 1 — Direct News Synthesis
- Fetches news articles tagged with watchlist ticker symbols.
- Extracts structured canonical events via LLM (or mock).
- Synthesizes a briefing for each ticker that has direct news.
- No deduplication, no cross-impact routing.

**Recommended scenario:** `Replay Scenario 1: Direct Announcements`  
(AAPL M5 chip announcement + MSFT Copilot cloud earnings)

---

### Iteration 2 — Catalyst Memory Deduplication
- Everything from Iteration 1, plus:
- An in-memory vector ledger checks each incoming event against previously seen catalysts using cosine similarity (threshold ≥ 0.75) and Jaccard fact overlap (threshold ≥ 0.60).
- **Duplicate:** same story, no new facts → suppressed, counted.
- **Update:** same story, new facts added → emitted with only the new facts.
- **New:** unrelated story → emitted normally.

**Recommended scenario:** `Replay Scenario 2: Duplicate Articles`  
(Three reports of the same Zhengzhou factory fire; the second is a duplicate, the third is an update with new facts about production halts and 2M delayed iPhones.)

> Use **Reset Cache** between runs to clear the ledger and observe the deduplication behavior from a clean state.

---

### Iteration 3 — Graph Cross-Impact Routing
- Everything from Iteration 2, plus:
- The exposure graph is used to expand search keywords by traversing up to 2 hops from watched tickers.
- Untickered external events (no `relatedTickers`) are matched to graph nodes by entity/tag/region/theme and routed to watchlist tickers via graph path traversal (max 3 hops).
- Path score = `event_severity × avg_edge_confidence × path_shortness_bonus`. Routes with score ≥ 0.45 are included.
- Hover over an indirect catalyst card to highlight its path through the Exposure Graph SVG on the right.

**Recommended scenario:** `Replay Scenario 3: Untickered Geopolitical/Tech`  
(Taiwan earthquake → TSMC/AAPL/NVDA; Anthropic model launch → NVDA/MSFT via Frontier AI; Red Sea drone strikes → DAL via Logistics Cost Risk)

---

## Environment Variable Reference

All variables go in `backend/.env`. Copy `backend/.env.example` as a starting point.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `GEMINI_API_KEY` | _(empty)_ | No | Google Gemini API key. Used for LLM extraction, synthesis, and embeddings. Either this or `OPENAI_API_KEY` needed for real LLM output. |
| `OPENAI_API_KEY` | _(empty)_ | No | OpenAI API key. Alternative to Gemini. Set `LLM_PROVIDER=openai` to activate. |
| `LLM_PROVIDER` | `gemini` | No | `"gemini"` or `"openai"`. Selects which provider's models are used when both keys are set. |
| `FINNHUB_API_KEY` | _(empty)_ | No | Finnhub key for live company-specific news. Only used with `scenario_id=live`. |
| `CURRENTS_API_KEY` | _(empty)_ | No | Currents API key for live cross-impact news. Only used with `scenario_id=live` and Iteration 3. |
| `PHOENIX_PORT` | `6006` | No | Port for the Arize Phoenix tracing dashboard. |
| `PHOENIX_PROJECT_NAME` | `cross-impact-catalysts` | No | Project label shown in the Phoenix dashboard. |
| `FRESHNESS_LOOKBACK_MINUTES` | `10` | No | How many minutes back from "now" to accept articles in live mode. Replay scenarios bypass this filter. |

---

## Repository Structure

```
problem-first-AI-capstone-team13/
├── backend/
│   ├── main.py               # FastAPI app — routes and pipeline invocation
│   ├── config.py             # Env vars, LLM factory functions, Phoenix init
│   ├── graph.py              # LangGraph 6-node workflow definition
│   ├── ingestion.py          # Finnhub/Currents API clients + scenario replay
│   ├── routing.py            # Exposure graph state + path traversal + scoring
│   ├── memory.py             # In-memory catalyst ledger + embedding engine
│   ├── seed_data.py          # Seeded exposure graph and replay scenario articles
│   ├── persistence.py        # JSON file persistence helpers (not yet wired up)
│   ├── run_tests.py          # Unit test suite (3 end-to-end workflow tests)
│   ├── requirements.txt      # Python dependencies (unpinned)
│   ├── .env.example          # Environment variable template
│   └── .venv/                # Local Python virtual environment (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # All dashboard logic, state, and rendering
│   │   ├── main.tsx          # React DOM mount point
│   │   └── index.css         # Dark-theme CSS variables and component styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts        # Vite config — dev server port 5173, /api proxy to 8000
├── .vscode/
│   ├── launch.json           # Debug/run configurations
│   └── tasks.json            # Install dependency tasks
├── research/
│   └── codebase-research.md  # Full codebase research document
├── README.md
├── implementation_plan.md
└── final-capstone-system-design-FINAL-lean-per-ticker.md
```

---

## Troubleshooting

### The backend starts but synthesis output says "LLM unavailable"
The LLM API key is either missing or exhausted. Check that `backend/.env` exists and contains a valid `GEMINI_API_KEY` or `OPENAI_API_KEY`. The app will still run and use mock synthesis in this case — the `Embeddings Memory Engine` panel in the UI will show which provider is active.

### PowerShell blocks the venv activation script
Run this once to allow local scripts:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### `ModuleNotFoundError: No module named 'backend'`
Run the backend as a module from the **repository root**, not from inside the `backend/` directory:
```bash
# Correct — from the repo root
python -m backend.main

# Wrong
cd backend && python main.py
```

### Arize Phoenix dashboard shows no traces
Phoenix must be running as a separate collector process for the dashboard at `http://localhost:6006` to display data. Use the `Full Application (Backend + Frontend + Tracing)` VS Code compound config, or start it manually:
```bash
python -m phoenix.server.main serve
```
The backend instruments LangGraph via OpenTelemetry on startup and sends traces to `localhost:4317`.

### Frontend shows "Pipeline execution error"
Check the backend terminal for the Python traceback. Common causes:
- Backend is not running (`http://localhost:8000` unreachable).
- An LLM API key is set but invalid or rate-limited — the pipeline sets `llm_failed=True` and rolls back the ledger.

### Live mode returns 0 articles
- The freshness filter only accepts articles published within the last `FRESHNESS_LOOKBACK_MINUTES` (default 10) minutes. Live news APIs may return articles older than this window.
- Verify your `FINNHUB_API_KEY` and `CURRENTS_API_KEY` are set correctly. Check the backend terminal for API error messages.

### Watchlist resets after restarting the backend
This is expected — the watchlist is currently stored in memory only. A file-based persistence module exists at `backend/persistence.py` but is not yet connected to the running application.
