import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.config import init_phoenix, PHOENIX_PORT
from backend.routing import get_graph, add_graph_node, add_graph_edge, set_graph, reset_graph
from backend.memory import get_ledger, clear_ledger
import backend.memory as _memory_module
from backend.config import GEMINI_API_KEY, OPENAI_API_KEY, LLM_PROVIDER
from backend.graph import build_workflow_graph
from backend.persistence import load_watchlist, save_watchlist, load_graph, save_graph
from backend.graph_expansion import (
    process_ticker_expansion,
    mark_pending,
    get_expansion_status,
)

app = FastAPI(title="Intraday Cross-Impact Catalyst Briefings API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For localhost demo, allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory Watchlist configuration
_watchlist = ["AAPL", "MSFT", "NVDA", "TSM", "DAL"]

# Compile LangGraph app
workflow_app = build_workflow_graph()

class RunRequest(BaseModel):
    iteration: int # 1, 2, or 3
    scenario_id: str # "live", "direct_news", "duplicate_news", "cross_impact"
    simulated_now: Optional[str] = "2026-05-28T17:25:00Z"

class WatchlistRequest(BaseModel):
    tickers: List[str]

class ExpandRequest(BaseModel):
    ticker: str
    force: bool = True  # manual triggers default to re-running even if the node exists

class RebuildRequest(BaseModel):
    reset: bool = True  # True = reset to curated seed first; False = additive refresh on top

@app.on_event("startup")
def startup_event():
    global _watchlist
    init_phoenix()
    _watchlist = load_watchlist(default=_watchlist)
    set_graph(load_graph(default=get_graph()))

@app.get("/api/watchlist")
def get_watchlist():
    return {"tickers": _watchlist}

@app.post("/api/watchlist")
def update_watchlist(req: WatchlistRequest, background_tasks: BackgroundTasks):
    global _watchlist
    previous_watchlist = list(_watchlist)

    # Newly added tickers trigger a ONE-TIME exposure-graph expansion. The add itself
    # is NOT blocked by the LLM: we commit the watchlist immediately and run expansion
    # as a background task. Removals are left in the graph so knowledge accumulates.
    new_tickers = [t for t in req.tickers if t not in previous_watchlist]

    _watchlist = req.tickers
    save_watchlist(_watchlist)

    # Queue expansion for each new ticker. mark_pending() flips the status before the
    # task runs so the UI shows "pending" the instant the add returns.
    for ticker in new_tickers:
        mark_pending(ticker)
        background_tasks.add_task(process_ticker_expansion, ticker, False)

    return {"tickers": _watchlist, "expansionStatus": get_expansion_status()}

@app.get("/api/graph/status")
def graph_expansion_status():
    """Per-ticker exposure-graph expansion status (pending/running/done/skipped/failed)."""
    return {"status": get_expansion_status()}

@app.post("/api/graph/expand")
def trigger_graph_expansion(req: ExpandRequest, background_tasks: BackgroundTasks):
    """Manually (re-)run the exposure-graph expansion for a ticker, in the background."""
    ticker = req.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    mark_pending(ticker)
    background_tasks.add_task(process_ticker_expansion, ticker, req.force)
    return {"status": "scheduled", "ticker": ticker, "expansionStatus": get_expansion_status()}

@app.post("/api/graph/rebuild")
def rebuild_graph_endpoint(req: RebuildRequest, background_tasks: BackgroundTasks):
    """
    Rebuild the exposure graph for the ENTIRE watchlist in the background.
      - reset=True  : restore the curated seed graph (drop accumulated LLM additions), then re-expand every ticker.
      - reset=False : keep the current graph and force a fresh expansion for every ticker on top of it.
    """
    if req.reset:
        reset_graph()
        save_graph(get_graph())
    for ticker in _watchlist:
        mark_pending(ticker)
        background_tasks.add_task(process_ticker_expansion, ticker, True)
    return {
        "status": "scheduled",
        "reset": req.reset,
        "tickers": _watchlist,
        "expansionStatus": get_expansion_status(),
    }

@app.get("/api/graph")
def get_exposure_graph():
    return get_graph()

@app.post("/api/graph/node")
def add_node(node: Dict[str, Any]):
    try:
        add_graph_node(node)
        save_graph(get_graph())
        return {"status": "success", "graph": get_graph()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/graph/edge")
def add_edge(edge: Dict[str, Any]):
    try:
        add_graph_edge(edge)
        save_graph(get_graph())
        return {"status": "success", "graph": get_graph()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ledger")
def get_active_ledger():
    return get_ledger()

@app.post("/api/ledger/clear")
def reset_ledger():
    clear_ledger()
    return {"status": "success", "message": "Catalyst Ledger has been cleared."}

@app.post("/api/run")
def trigger_pipeline(req: RunRequest):
    """Triggers the LangGraph pipeline run for the specified iteration and scenario."""
    if req.iteration not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Iteration must be 1, 2, or 3.")
        
    initial_state = {
        "iteration": req.iteration,
        "watchlist": _watchlist,
        "scenario_id": req.scenario_id,
        "simulated_now": req.simulated_now,
        "articles": [],
        "canonical_events": [],
        "routed_candidates": [],
        "ticker_buckets": {},
        "ticker_syntheses": {},
        "duplicate_counts": {},
        "ingestion_metadata": {},
        "llm_failed": False
    }

    # Snapshot ledger before run so we can roll back if the pipeline fails
    ledger_snapshot = list(_memory_module._ledger_store)
    
    try:
        print(f"Executing LangGraph workflow for Iteration {req.iteration} (Scenario: {req.scenario_id})...")
        final_state = workflow_app.invoke(initial_state)

        # If LLM failed, roll back any ledger writes made during this run so
        # re-running won't treat those articles as already-seen duplicates.
        if final_state.get("llm_failed", False):
            print("Pipeline had LLM failure — rolling back ledger to pre-run snapshot.")
            _memory_module._ledger_store.clear()
            _memory_module._ledger_store.extend(ledger_snapshot)

        # Clean final state for client consumption
        response_data = {
            "runId": f"run_{req.scenario_id}_{int(datetime_now().timestamp())}",
            "iteration": final_state["iteration"],
            "watchlist": final_state["watchlist"],
            "articlesCount": len(final_state.get("articles", [])),
            "eventsCount": len(final_state.get("canonical_events", [])),
            "routedCount": len(final_state.get("routed_candidates", [])),
            "duplicateCounts": final_state.get("duplicate_counts", {}),
            "tickerSyntheses": final_state.get("ticker_syntheses", {}),
            "llmFailed": final_state.get("llm_failed", False),
            # Debug structures
            "rawArticles": final_state.get("articles", []),
            "canonicalEvents": final_state.get("canonical_events", []),
            "routedCandidates": final_state.get("routed_candidates", []),
            "tickerBuckets": final_state.get("ticker_buckets", {})
        }
        return response_data
    except Exception as e:
        # Also roll back ledger on unexpected crash
        print(f"Error running pipeline: {e} — rolling back ledger.")
        _memory_module._ledger_store.clear()
        _memory_module._ledger_store.extend(ledger_snapshot)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@app.get("/api/phoenix-status")
def get_phoenix_status():
    return {
        "running": True,
        "dashboardUrl": f"http://127.0.0.1:{PHOENIX_PORT}",
        "projectName": "cross-impact-catalysts"
    }

@app.get("/api/memory-status")
def get_memory_status():
    """Returns the current status of the catalyst dedup engine and memory module."""
    # The dedup engine runs LOCALLY at $0/call — no remote embedding API.
    # Primary: local fastembed neural embeddings. Fallback: lexical token cosine.
    embedding_active = _memory_module.is_embedding_active()
    if embedding_active:
        dedup_provider = "Local embeddings"
        dedup_model = f"{_memory_module._EMBEDDING_MODEL_NAME} (384d)"
        dedup_method = "neural_cosine"
    else:
        dedup_provider = "Local (lexical fallback)"
        dedup_model = "tf-cosine + jaccard"
        dedup_method = "lexical_cosine"

    # LLM model reporting still depends on the configured provider.
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        llm_extraction_model = "gpt-4.1-nano"
        llm_synthesis_model = "gpt-4o-mini"
    elif GEMINI_API_KEY:
        llm_extraction_model = "gemini-2.5-flash"
        llm_synthesis_model = "gemini-2.5-flash"
    else:
        llm_extraction_model = "N/A"
        llm_synthesis_model = "N/A"

    live_entries = [e for e in _memory_module._ledger_store if e.get("status") == "live"]
    embedded_entries = [e for e in live_entries if e.get("embedding_vec")]

    return {
        "dedupProvider": dedup_provider,
        "dedupModel": dedup_model,
        "dedupMethod": dedup_method,
        # isFallbackActive=True means the lexical fallback is in use (embedding model unavailable).
        "isFallbackActive": not embedding_active,
        "similarityThreshold": 0.75,
        "jaccardFactThreshold": 0.6,
        "ledgerTotalEntries": len(_memory_module._ledger_store),
        "ledgerLiveEntries": len(live_entries),
        "ledgerEmbeddedEntries": len(embedded_entries),
        "llmExtractionModel": llm_extraction_model,
        "llmSynthesisModel": llm_synthesis_model,
    }

def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
