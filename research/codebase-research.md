# Codebase Research: Intraday Cross-Impact Catalyst Briefings

**Date:** 2026-05-28  
**Branch:** main  
**Scope:** Full codebase as it exists today — no evaluations or suggestions.

---

## Summary of Findings

The project is a full-stack demo application that synthesizes intraday financial market catalysts for a set of watched stock tickers. A Python FastAPI backend hosts a six-node LangGraph pipeline that ingests news (live from Finnhub and Currents APIs, or from seeded scenario replays), extracts structured canonical events via an LLM, routes them to relevant tickers through a seeded exposure graph, deduplicates them against an in-memory vector ledger, and synthesizes per-ticker briefings. A React + Vite frontend at `http://localhost:5173` proxies all requests to the backend at `http://localhost:8000` and renders synthesis cards, an SVG exposure-graph viewer, and an observability panel that connects to an Arize Phoenix tracing server at `http://localhost:6006`. The system supports three distinct pipeline "iterations" (direct news, deduplication, cross-impact routing) selectable from the UI. A `persistence.py` file exists that provides JSON disk persistence for the watchlist and graph but is **not imported anywhere in the live application** as of this snapshot.

---

## 1. Repository Layout

```
problem-first-AI-capstone-team13/
├── backend/
│   ├── config.py          # env vars, LLM factory functions, Phoenix init
│   ├── main.py            # FastAPI app, routes, workflow invocation
│   ├── graph.py           # LangGraph workflow definition (6 nodes)
│   ├── ingestion.py       # Finnhub/Currents API clients + scenario replay
│   ├── routing.py         # Exposure graph state + path traversal
│   ├── memory.py          # In-memory catalyst ledger + embedding logic
│   ├── seed_data.py       # Static EXPOSURE_GRAPH and SCENARIOS dicts
│   ├── persistence.py     # JSON-file persistence (NOT wired up)
│   ├── run_tests.py       # unittest suite (3 workflow tests)
│   ├── scratch_inspect.py # Dev scratch script, not part of app
│   ├── search_design.py   # Dev scratch script, not part of app
│   ├── test_gemini_embeddings.py  # Standalone embedding probe script
│   ├── requirements.txt
│   ├── .env.example
│   └── .venv/
├── frontend/
│   ├── src/App.tsx        # Single-file React app (all UI logic)
│   ├── src/main.tsx       # React DOM mount
│   ├── src/index.css      # Dark-theme CSS variables + component styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── .vscode/
│   ├── launch.json        # VS Code debug configs
│   └── tasks.json
├── README.md
├── implementation_plan.md
└── final-capstone-system-design-FINAL-lean-per-ticker.md
```

---

## 2. Backend — Configuration (`backend/config.py`)

**Source:** [backend/config.py](../backend/config.py)

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `""` | Google Gemini LLM (extraction + synthesis; not embeddings) |
| `OPENAI_API_KEY` | `""` | OpenAI LLM (extraction + synthesis; not embeddings) |
| `LLM_PROVIDER` | `"gemini"` | Selects active provider; `"openai"` or `"gemini"` |
| `FINNHUB_API_KEY` | `""` | Live Finnhub company-news API |
| `CURRENTS_API_KEY` | `""` | Live Currents cross-impact news API |
| `PHOENIX_PORT` | `6006` | Arize Phoenix dashboard port |
| `PHOENIX_PROJECT_NAME` | `"cross-impact-catalysts"` | Phoenix project label |
| `FRESHNESS_LOOKBACK_MINUTES` | `10` | News freshness window in minutes |

Env is loaded from the repo root first, then `backend/.env` is loaded with `override=True` (`config.py:5-8`).

### LLM Factory Functions

Two factory functions are exported:

- **`get_llm()`** (`config.py:42-59`) — Returns the reasoning LLM used for synthesis (Node 5). OpenAI → `gpt-4o-mini`; Gemini → `gemini-2.5-flash`. Both at `temperature=0.0`.
- **`get_llm_fast()`** (`config.py:61-80`) — Returns the extraction LLM used for canonical event extraction (Node 2). OpenAI → `gpt-4.1-nano`; Gemini → `gemini-2.5-flash` (same model as `get_llm` for the Gemini path).

Both functions fall back to OpenAI if `GEMINI_API_KEY` is absent but `OPENAI_API_KEY` is present.

### Phoenix Tracing

`init_phoenix()` (`config.py:25-39`) is called in the FastAPI `startup` event. It registers the OpenTelemetry provider targeting `localhost:4317` and instruments LangChain/LangGraph via `LangChainInstrumentor`. Failure is caught and printed; the app continues without traces.

---

## 3. Backend — FastAPI Server (`backend/main.py`)

**Source:** [backend/main.py](../backend/main.py)

### Application Bootstrap

- `app = FastAPI(title="Intraday Cross-Impact Catalyst Briefings API")` (`main.py:14`)
- CORS is wide-open (`allow_origins=["*"]`) (`main.py:17-23`)
- `_watchlist = ["AAPL", "MSFT", "NVDA", "TSM", "DAL"]` — in-memory list, reset on every restart (`main.py:26`)
- `workflow_app = build_workflow_graph()` — compiled LangGraph app, instantiated at module load time (`main.py:29`)

### API Endpoints

| Method | Path | Handler | Purpose |
|---|---|---|---|
| `GET` | `/api/watchlist` | `get_watchlist` | Returns `{"tickers": [...]}` |
| `POST` | `/api/watchlist` | `update_watchlist` | Replaces watchlist (`WatchlistRequest` body) |
| `GET` | `/api/graph` | `get_exposure_graph` | Returns full graph dict from `routing.get_graph()` |
| `POST` | `/api/graph/node` | `add_node` | Adds/replaces a node in the in-memory graph |
| `POST` | `/api/graph/edge` | `add_edge` | Adds/replaces an edge in the in-memory graph |
| `GET` | `/api/ledger` | `get_active_ledger` | Returns live (non-expired) ledger entries |
| `POST` | `/api/ledger/clear` | `reset_ledger` | Clears all ledger entries |
| `POST` | `/api/run` | `trigger_pipeline` | Runs the LangGraph workflow, returns synthesis results |
| `GET` | `/api/phoenix-status` | `get_phoenix_status` | Returns static `{"running": True, ...}` |
| `GET` | `/api/memory-status` | `get_memory_status` | Returns embedding engine config and ledger stats |

### `/api/run` — Pipeline Invocation (`main.py:83-143`)

Request body (`RunRequest`):
- `iteration`: int, 1|2|3
- `scenario_id`: str — `"live"`, `"direct_news"`, `"duplicate_news"`, or `"cross_impact"`
- `simulated_now`: str ISO timestamp (default `"2026-05-28T17:25:00Z"`)

The handler builds an `initial_state` dict, snapshots `_memory_module._ledger_store` before the run (`main.py:105`), invokes `workflow_app.invoke(initial_state)`, and rolls back the ledger snapshot if `final_state["llm_failed"] == True` or if an exception occurs (`main.py:113-116`, `main.py:137-140`).

Response fields returned to the client:
`runId`, `iteration`, `watchlist`, `articlesCount`, `eventsCount`, `routedCount`, `duplicateCounts`, `tickerSyntheses`, `llmFailed`, `rawArticles`, `canonicalEvents`, `routedCandidates`, `tickerBuckets`.

**Note:** `runId` is generated using `datetime_now()` which is defined at `main.py:194-196`. This helper is defined after it is used in the handler (`main.py:120`) — valid in Python because the function definition is at module scope.

---

## 4. Backend — LangGraph Pipeline (`backend/graph.py`)

**Source:** [backend/graph.py](../backend/graph.py)

### State Schema (`WorkflowState` TypedDict, `graph.py:12-25`)

| Field | Type | Description |
|---|---|---|
| `iteration` | int | 1, 2, or 3 — controls dedup and cross-impact features |
| `watchlist` | List[str] | Ticker symbols to monitor |
| `scenario_id` | str | `"live"` or one of the three replay keys |
| `simulated_now` | str | ISO timestamp used as reference for freshness |
| `articles` | List[Dict] | Raw normalized article objects from ingestion |
| `canonical_events` | List[Dict] | Structured events extracted by Node 2 |
| `routed_candidates` | List[Dict] | Event-to-ticker routing decisions from Nodes 3/4 |
| `ticker_buckets` | Dict[str, Dict] | Per-ticker context groupings (direct + cross-impact) |
| `ticker_syntheses` | Dict[str, Dict] | Final LLM-generated briefings per ticker |
| `duplicate_counts` | Dict[str, int] | Count of suppressed duplicates per ticker |
| `ingestion_metadata` | Dict[str, Any] | `total_ingested` and `passed_freshness` counts |
| `llm_failed` | bool | Sentinel: halts downstream LLM steps if True |

### Workflow Topology

```
fetch_and_filter  →  extract_events  →  route_events  →  check_ledger  →  synthesize_ticker_briefings  →  compliance_gate  →  END
```

Built at `graph.py:800-820` via `build_workflow_graph()`. All edges are unconditional (no conditional branching via `add_conditional_edges`).

---

### Node 1 — `fetch_and_filter` (`graph.py:38-64`)

- If `iteration == 3`, calls `get_cross_impact_keywords(watchlist)` to expand search terms using the exposure graph.
- Calls `get_news_payload(...)` from `ingestion.py`.
- Writes `articles` and `ingestion_metadata` to state.

### Node 2 — `canonical_event_extraction_node` (`graph.py:182-345`)

- Checks if `GEMINI_API_KEY or OPENAI_API_KEY` is set. If neither is set, uses `MOCK_EVENTS` dict (`graph.py:66-179`) keyed by `articleId`.
- **LLM path:** Sends all articles in a single batch call to `get_llm_fast()` with a system prompt that asks for a JSON array of event objects (`graph.py:234-261`, `graph.py:300-308`).
- LLM output fields: `articleId`, `eventType`, `eventSummary`, `hardFacts`, `entities`, `eventTags`, `regions`, `sectors`, `commodities`, `technologyThemes`, `possibleDirectionalPressure`, `uncertaintyNotes`, `evidence`.
- After LLM call, adds metadata fields: `eventId`, `sourceArticleIds`, `relatedTickers`, `sourceUrl`, `sourceHeadline`.
- On any exception, returns `{"canonical_events": [], "llm_failed": True}` (`graph.py:342-343`).

**`clean_json_string()`** (`graph.py:26-35`) — strips markdown code fences from LLM output before `json.loads`.

**`clean_summary()`** (`graph.py:266-275`) — strips Finnhub's trailing headline repetition from summary text.

`MOCK_EVENTS` (`graph.py:66-179`) contains 7 pre-baked event dicts keyed by article ID:
- `finnhub_direct_001` — AAPL M5 chip
- `finnhub_direct_002` — MSFT Copilot cloud earnings
- `finnhub_dup_001/002/003` — Zhengzhou fire (3 versions for dedup testing)
- `currents_cross_001` — Taiwan earthquake
- `currents_cross_002` — Anthropic Claude 3.7 launch
- `currents_cross_003` — Red Sea drone strikes

### Node 3 — `routing_node` (`graph.py:348-382`)

- **Direct routing (all iterations):** For each canonical event, checks `event["relatedTickers"]` against watchlist. Creates a `routed_candidates` entry with `relationshipType="direct"`, `pathConfidence=1.0`.
- **Cross-impact routing (iteration 3 only):** Calls `route_cross_impact(event, watchlist)` from `routing.py` and appends candidates with `relationshipType="indirect"`. Deduplicates against already-added direct routes.

### Node 4 — `ledger_memory_node` (`graph.py:385-420`)

- **Iteration 1:** Skips ledger entirely; all candidates tagged `ledgerDecision="new"`.
- **Iterations 2 and 3:** Calls `check_ledger_decision(ticker, event)` from `memory.py` for each candidate. Returns `"new"` | `"update"` | `"duplicate"`.
  - `"duplicate"` candidates are removed from `routed_candidates` and counted in `duplicate_counts`.
  - `"new"` and `"update"` candidates pass through with `newFacts` populated.

### Node 5 — `per_ticker_synthesis_node` (`graph.py:422-753`)

- First checks `state["llm_failed"]`; if True, returns empty error syntheses for all tickers (`graph.py:428-446`).
- Builds `ticker_buckets` separating `directEvents` and `crossImpactEvents` per ticker (`graph.py:454-486`).
- **No-key path:** Generates rules-based syntheses using event summaries and directional pressure aggregation (`graph.py:495-607`).
- **LLM path:** Calls `get_llm()` once per ticker bucket that has events. Each call receives a JSON-serialized bucket as context. System prompt enforces recency weighting: `< 30 mins = HIGH`, `30-90 mins = MEDIUM`, `> 90 mins = BACKGROUND` (`graph.py:615-616`).
- Events are annotated with `minutesAgo` before the LLM call (`graph.py:655-666`).
- Tickers with no events get a `"No new catalysts detected"` synthesis with contextual freshness explanation (`graph.py:670-692`).

### Node 6 — `compliance_gate_node` (`graph.py:761-793`)

Runs regex substitutions over `summaryHeadline` and `situationSummary` for forbidden terms:
- `buy` → `monitor`
- `sell` → `assess`
- `should short` → `may face downward sentiment pressure`
- `invest in` → `watch exposure to`
- `we recommend` → `it may be useful to`

Enforces `notFinancialAdvice = True` on all syntheses.

---

## 5. Backend — Ingestion (`backend/ingestion.py`)

**Source:** [backend/ingestion.py](../backend/ingestion.py)

### Live API Clients

**`fetch_finnhub_direct_news(symbol, minutes_lookback=10)`** (`ingestion.py:18-64`)
- Calls `https://finnhub.io/api/v1/company-news?symbol={symbol}&from={today}&to={today}&token={key}` with a 10-second timeout.
- Normalizes Finnhub's unix-epoch `datetime` field to ISO string.
- Returns articles with `articleId = f"finnhub_{art['id']}"`, `relatedTickers = [symbol]`.

**`fetch_currents_cross_impact_news(keywords)`** (`ingestion.py:66-111`)
- Calls `https://api.currentsapi.services/v1/search?keywords={query}&language=en&apiKey={key}`.
- Keywords joined with `" OR "`.
- Returns articles with `articleId = f"currents_{art['id']}"`, `relatedTickers = []`.

### Orchestrator

**`get_news_payload(symbol_watchlist, cross_impact_keywords, scenario_id, simulated_now_str)`** (`ingestion.py:113-181`)
- `scenario_id != "live"`: Loads articles from `SCENARIOS[scenario_id]["articles"]` in `seed_data.py`. Uses `simulated_now_str` as the reference time.
- `scenario_id == "live"`: Calls Finnhub for each symbol, then Currents if `cross_impact_keywords` is non-empty.

**Freshness filter** (`ingestion.py:155-175`):
- URL deduplication via `seen_urls` set.
- Keeps article if `0 <= time_diff_seconds <= FRESHNESS_LOOKBACK_MINUTES * 60`.
- **Exception:** Scenario (non-live) articles bypass the upper bound and are always kept regardless of freshness (`ingestion.py:172`).

---

## 6. Backend — Exposure Graph and Routing (`backend/routing.py`, `backend/seed_data.py`)

### In-Memory Graph State (`routing.py:6`)

```python
_graph_store = copy.deepcopy(EXPOSURE_GRAPH)
```

Initialized from `seed_data.EXPOSURE_GRAPH` at module import. Mutations via `add_graph_node()` and `add_graph_edge()` (`routing.py:12-35`) modify this dict in-place. **Resets to seed on every restart** because `persistence.py` is not called.

### Seed Graph (`seed_data.py:3-231`)

**13 nodes** across 6 types:

| nodeType | Nodes |
|---|---|
| `ticker` | AAPL, MSFT, NVDA, TSM, DAL |
| `private_company` | Foxconn, Anthropic, OpenAI |
| `region` | Taiwan |
| `technology_theme` | Frontier AI, Semiconductors |
| `shipping_route` | Red Sea Shipping |
| `risk_factor` | Logistics Cost Risk |

**13 edges:**

| From | To | edgeType | confidence |
|---|---|---|---|
| TSM | AAPL | `supplier_of` | 0.95 |
| Foxconn | AAPL | `supplier_of` | 0.90 |
| Semiconductors | AAPL | `technology_exposure` | 0.90 |
| Taiwan | TSM | `regional_exposure` | 0.99 |
| TSM | NVDA | `supplier_of` | 0.95 |
| Semiconductors | NVDA | `technology_exposure` | 0.99 |
| Frontier AI | NVDA | `technology_exposure` | 0.90 |
| Frontier AI | MSFT | `technology_exposure` | 0.90 |
| Anthropic | Frontier AI | `technology_exposure` | 0.95 |
| OpenAI | Frontier AI | `technology_exposure` | 0.95 |
| Red Sea | Logistics Cost Risk | `shipping_exposure` | 0.85 |
| Logistics Cost Risk | DAL | `macro_sensitivity` | 0.80 |

### Query Expansion (`routing.py:37-91`)

`get_cross_impact_keywords(watchlist)`:
1. Finds graph nodes matching watchlist tickers.
2. Collects all neighbors within 2 hops (bidirectional BFS).
3. Returns `queryTerms` of all non-ticker neighbor nodes as search keywords for the Currents API.

### Path Traversal and Scoring (`routing.py:93-247`)

`find_paths_to_watchlist(start_node_id, watchlist_node_ids, max_hops=3)` (`routing.py:93-127`):
- DFS, traverses edges in both directions.
- Returns all paths of length ≤ 3 as lists of edge dicts.

`route_cross_impact(canonical_event, watchlist)` (`routing.py:129-247`):
1. Matches event `entities`, `eventTags`, `regions`, `technologyThemes` against node `name` and `aliases` (case-insensitive substring match).
2. Calls `find_paths_to_watchlist` from each matched node.
3. Scores each path: `path_score = event_severity × avg_edge_confidence × path_shortness_bonus`.
   - `event_severity`: `positive/negative=1.0`, `mixed=0.8`, `unclear=0.5`
   - `path_shortness_bonus`: 1 hop=1.0, 2 hops=0.9, 3 hops=0.75
4. Routes if `path_score >= 0.45`.
5. Deduplicates per `(ticker, eventId)`, keeping highest-scoring path.

---

## 7. Backend — Catalyst Memory Ledger (`backend/memory.py`)

**Source:** [backend/memory.py](../backend/memory.py)

### Storage

`_ledger_store: List[Dict[str, Any]] = []` (`memory.py:7`) — process-level list, cleared by `clear_ledger()` or on restart.

`_embedding_unavailable: bool = False` — module-level flag, set to `True` if the local embedding model cannot be loaded; thereafter the dedup engine uses the lexical fallback.

### Dedup Embedding Engine (local, no API)

Catalyst dedup runs entirely **locally** — there is no remote embedding API and no per-call cost.

`get_text_embedding(text) -> Optional[List[float]]`:
1. **Primary:** local `fastembed.TextEmbedding` model (`BAAI/bge-small-en-v1.5`, 384 dimensions, ONNX/CPU), loaded once as a lazy singleton via `_get_embedding_model()`. Model name overridable with the `EMBEDDING_MODEL` env var.
2. **Returns `None`** if the model is unavailable, signalling callers to use the lexical fallback.

Embedding calls are wrapped in an OpenTelemetry span (`catalyst.embedding`, provider `local_fastembed`). The lexical fallback path emits a `catalyst.similarity` span (`similarity.method = lexical_tf_cosine`, `similarity.score`).

`is_embedding_active()` — reports whether the neural engine loaded (used by `/api/memory-status`).

### Similarity Functions

`calculate_cosine_similarity(vec1, vec2)` — numpy dot product / norms over embedding vectors (primary path).

`calculate_text_similarity(text1, text2)` — deterministic lexical token-frequency cosine (stopword-filtered). Fallback matcher when no embedding model is available.

`get_jaccard_similarity(str1, str2)` — word-level set intersection/union.

`check_for_new_facts(event_facts, ledger_facts)` — a fact is "new" if its Jaccard similarity to every existing ledger fact is `< 0.6`.

### Ledger Decision Logic

`check_ledger_decision(ticker, canonical_event, similarity_threshold=0.75)`:

1. Filters `_ledger_store` to active entries matching `ticker` and `eventType`.
2. Computes the local embedding of the incoming `eventSummary` (may be `None`).
3. For each candidate entry: uses **embedding cosine** when both vectors exist, else falls back to **lexical cosine** over summaries.
4. **If best match `>= 0.75`:**
   - Checks `check_for_new_facts`. If new facts exist → `"update"`: appends facts, updates `canonicalSummary`, re-embeds entry. If no new facts → `"duplicate"`: logs article ID only.
5. **If no match `>= 0.75`:** Creates new ledger entry with 1-day TTL (storing `embedding_vec`), returns `"new"`.

**Ledger entry schema:**
```
catalystId, ticker, eventType, relationshipType, canonicalSummary,
embedding_vec, firstSeenAt, lastUpdatedAt, expiresAt (1-day TTL),
memberArticleIds, hardFactsSeen, status ("live" | "expired")
```

`get_ledger()` (`memory.py:9-17`) marks entries as `"expired"` at read time and returns only `"live"` entries.

---

## 8. Backend — Seed Data (`backend/seed_data.py`)

**Source:** [backend/seed_data.py](../backend/seed_data.py)

Defines two module-level dicts:

**`EXPOSURE_GRAPH`** (`seed_data.py:3-231`): The graph described in Section 6 above.

**`SCENARIOS`** (`seed_data.py:233-332`): Three replay scenarios:
- `"direct_news"` — 2 articles: AAPL M5 chip (`finnhub_direct_001`), MSFT Copilot earnings (`finnhub_direct_002`). `publishedAt: 2026-05-28T17:20/21:00Z`.
- `"duplicate_news"` — 3 articles: Three Zhengzhou fire reports with increasing detail (`finnhub_dup_001/002/003`). `publishedAt: 2026-05-28T17:20:00Z` to `17:24:00Z`.
- `"cross_impact"` — 3 untickered articles: Taiwan earthquake (`currents_cross_001`), Anthropic Claude 3.7 launch (`currents_cross_002`), Red Sea drone strikes (`currents_cross_003`). All `relatedTickers: []`. `publishedAt: 2026-05-28T17:20/21/22:00Z`.

---

## 9. Backend — Persistence Module (`backend/persistence.py`)

**Source:** [backend/persistence.py](../backend/persistence.py)

Provides file-based JSON persistence for watchlist and exposure graph. Targets `backend/state/watchlist.json` and `backend/state/graph.json`.

Functions:
- `load_watchlist(default)` / `save_watchlist(tickers)` (`persistence.py:23-46`)
- `load_graph(default)` / `save_graph(graph)` (`persistence.py:53-77`)

**This module is not imported by `main.py`, `routing.py`, or any other live module.** The watchlist (`_watchlist`) and graph (`_graph_store`) are reset to hard-coded defaults on every backend restart.

---

## 10. Frontend (`frontend/src/App.tsx`)

**Source:** [frontend/src/App.tsx](../frontend/src/App.tsx)

Single-file React app (908 lines). All state, data fetching, and rendering live here.

### TypeScript Interfaces

| Interface | Purpose |
|---|---|
| `Catalyst` | Individual catalyst item inside a synthesis |
| `TickerSummary` | Full per-ticker synthesis output (headline, summary, catalysts, URLs…) |
| `EventEntry` | A canonical event within a ticker bucket |
| `TickerBucket` | Per-ticker grouping: `directEvents`, `crossImpactEvents`, `suppressedDuplicateCount` |
| `RunResult` | Full pipeline output from `/api/run` |
| `GraphNode` / `GraphEdge` / `ExposureGraph` | Exposure graph shape for the SVG viewer |

### React State

| State | Type | Initial Value |
|---|---|---|
| `watchlist` | `string[]` | `[]` — populated from `GET /api/watchlist` |
| `newTicker` | `string` | `""` — controlled input for adding tickers |
| `iteration` | `number` | `3` |
| `scenarioId` | `string` | `"live"` |
| `activeTicker` | `string` | `"AAPL"` |
| `runResult` | `RunResult \| null` | `null` |
| `graphData` | `ExposureGraph` | `{ nodes: [], edges: [] }` |
| `ledgerEntries` | `any[]` | `[]` |
| `loading` | `boolean` | `false` |
| `phoenixStatus` | `any` | `{ running: false, dashboardUrl: '' }` |
| `selectedCatalystPath` | `string[] \| null` | `null` — for SVG path highlighting |
| `memoryStatus` | `any` | `null` |

### Data Fetching

`useEffect` on mount (`App.tsx:101-107`) calls `fetchWatchlist`, `fetchGraph`, `fetchLedger`, `fetchPhoenixStatus`, `fetchMemoryStatus` in parallel.

`runPipeline()` (`App.tsx:214-241`) — POSTs to `/api/run` with hardcoded `simulated_now: '2026-05-28T17:25:00Z'` regardless of actual current time. Refreshes ledger, graph, and memory status on completion.

### SVG Exposure Graph Viewer (`App.tsx:253-279`)

Lays out nodes in three visual columns:
- Column 1 (`x=45`): regions, shipping routes, risk factors — all non-ticker, non-theme, non-company nodes.
- Column 2 (`x=190`): `technology_theme`, `private_company`, `sector` nodes.
- Column 3 (`x=330`): `ticker` nodes.

Nodes are spaced vertically within their column (`y = 30 + (index+1) * (220 / (total+1))`). Y-positions for column 3 use a fixed 45px stride (`App.tsx:259`).

**Path highlighting:** When the user hovers over a cross-impact catalyst card, `selectedCatalystPath` is set to the `impactPath` array. The SVG fades non-highlighted edges/nodes to 25-35% opacity (`App.tsx:557-569`, `App.tsx:665`, `App.tsx:683`).

### UI Layout

Three-column layout: `sidebar` (watchlist) | `main-content` (synthesis cards) | `right-panel` (graph + observability panels).

Right panel sections (top to bottom):
1. Causal Exposure Graph (SVG)
2. Observability Traces (Phoenix status + run metrics)
3. Active Story Ledger (live `_ledger_store` entries)
4. Embeddings Memory Engine (provider, model, thresholds, counts)

Company names for tickers other than `AAPL`, `MSFT`, `NVDA`, `TSM`, `DAL` display as `"Public Company"` (`App.tsx:412`).

---

## 11. Frontend Configuration (`frontend/vite.config.ts`)

**Source:** [frontend/vite.config.ts](../frontend/vite.config.ts)

Dev server runs on port `5173`. All `/api/*` requests are proxied to `http://localhost:8000` with `changeOrigin: true` (`vite.config.ts:8-13`).

---

## 12. Testing (`backend/run_tests.py`)

**Source:** [backend/run_tests.py](../backend/run_tests.py)

Three `unittest.TestCase` methods in `TestWorkflow`:

| Test | Method | Scenario | Key Assertions |
|---|---|---|---|
| `test_iteration_1_direct_news` | `@patch('backend.graph.get_llm')` | `direct_news`, iter 1 | 2 articles, 2 events, direct routes for AAPL+MSFT, syntheses present |
| `test_iteration_2_ledger_duplicates` | `@patch('backend.graph.get_llm')` | `duplicate_news`, iter 2 | 3 articles, 3 events, `duplicate_counts["AAPL"] == 1` |
| `test_iteration_3_cross_impact_routing` | `@patch('backend.graph.get_llm')` | `cross_impact`, iter 3 | Earthquake routes to AAPL/NVDA/TSM; Anthropic routes to MSFT/NVDA; Red Sea routes to DAL |

`setUp()` calls `clear_ledger()` and `build_workflow_graph()` before each test.

`mock_llm_invoke()` (`run_tests.py:21-202`) routes by checking `system_msg` content for extraction vs. synthesis patterns, then `user_msg` content for article URL fragments or IDs.

**Note on mock behavior:** The patch target is `backend.graph.get_llm` (the synthesis LLM). The extraction LLM (`get_llm_fast`) is not patched. However, Node 2 checks for API key presence before calling the LLM; if neither `GEMINI_API_KEY` nor `OPENAI_API_KEY` is set (the typical test environment), the mock events from `MOCK_EVENTS` are used directly, bypassing both `get_llm_fast()` and the patch. Similarly, Node 5's `use_mock` path is taken when no keys are present, bypassing `get_llm()` and the patch. The `@patch` decorator only has effect when API keys are present in the test environment.

**`llm_failed` field** is absent from `initial_state` dicts in all three tests (`run_tests.py:211-222`, `248-256`, `288-295`), even though `WorkflowState` declares it as a required key. LangGraph does not raise on missing TypedDict keys at runtime — Node 5 calls `state.get("llm_failed", False)` defensively.

---

## 13. Cross-Component Data Flow

### Live Mode (Iteration 3)

```
main.py /api/run
  → graph.py: fetch_and_filter_node
      → routing.py: get_cross_impact_keywords()
          → seed_data.EXPOSURE_GRAPH (via _graph_store)
      → ingestion.py: get_news_payload()
          → fetch_finnhub_direct_news() [Finnhub API]
          → fetch_currents_cross_impact_news() [Currents API]
          → freshness filter
  → graph.py: canonical_event_extraction_node
      → config.py: get_llm_fast() → Gemini/OpenAI
      → MOCK_EVENTS (if no keys)
  → graph.py: routing_node
      → routing.py: route_cross_impact()
          → find_paths_to_watchlist() [DFS on _graph_store]
  → graph.py: ledger_memory_node
      → memory.py: check_ledger_decision()
          → get_text_embedding() → local fastembed (or lexical-cosine fallback)
          → calculate_cosine_similarity()
          → check_for_new_facts()
          → _ledger_store mutation
  → graph.py: per_ticker_synthesis_node
      → config.py: get_llm() → Gemini/OpenAI
  → graph.py: compliance_gate_node
      → regex substitutions
  → main.py: ledger rollback (if llm_failed or exception)
  → response to frontend
```

### Frontend → Backend Round-Trips per Run

1. `POST /api/run` — main pipeline invocation
2. `GET /api/ledger` — refresh after run
3. `GET /api/graph` — refresh after run
4. `GET /api/memory-status` — refresh after run

---

## 14. Utility and Dev Scripts

| File | Purpose |
|---|---|
| [backend/scratch_inspect.py](../backend/scratch_inspect.py) | Dev script: invokes the graph with `cross_impact` scenario, prints canonical events and routed candidates for `currents_cross_002`. Not part of the app. |
| [backend/search_design.py](../backend/search_design.py) | Dev script: reads `final-capstone-system-design-FINAL-lean-per-ticker.md` and prints sections matching "extraction". Not part of the app. |
| [backend/test_gemini_embeddings.py](../backend/test_gemini_embeddings.py) | Standalone probe: tries four Gemini embedding model name variants and reports which works. Not part of the app. |

---

## 15. VS Code Launch Configurations (`.vscode/launch.json`)

Four individual configs and one compound:

| Config | Type | Command |
|---|---|---|
| `Backend: FastAPI Server` | Python | `python -m backend.main` |
| `Backend: Run Unit Tests` | Python | runs `backend/run_tests.py` directly |
| `Frontend: Vite React Server` | Node | `npm run dev` in `frontend/` |
| `Tracing: Arize Phoenix Server` | Python | `python -m phoenix.server.main serve` |
| **`Full Application (Backend + Frontend + Tracing)`** | compound | all three servers simultaneously |

All Python configs use `backend/.venv/Scripts/python.exe` and set `PYTHONIOENCODING=utf-8`. The Phoenix server config also sets `PHOENIX_HOST=127.0.0.1`.

---

## 16. Python Dependencies (`backend/requirements.txt`)

```
fastapi
uvicorn
langgraph
langchain-core
langchain-google-genai
langchain-openai
arize-phoenix
openinference-instrumentation-langchain
requests
python-dotenv
pydantic
numpy
```

All unpinned. Python runtime is 3.11 (inferred from `__pycache__` filenames).

---

## 17. Frontend Dependencies (`frontend/package.json`)

Runtime: `react@^18.2.0`, `react-dom@^18.2.0`, `lucide-react@^0.344.0`.  
Dev: `vite@^5.1.8`, `typescript@^5.2.2`, `@vitejs/plugin-react@^4.2.1`.
