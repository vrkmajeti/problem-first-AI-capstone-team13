import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from backend.config import init_phoenix, PHOENIX_PORT
from backend.routing import get_graph, add_graph_node, add_graph_edge
from backend.memory import get_ledger, clear_ledger
import backend.memory as _memory_module
from backend.graph import build_workflow_graph

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

@app.on_event("startup")
def startup_event():
    # Initialize Arize Phoenix on startup
    init_phoenix()

@app.get("/api/watchlist")
def get_watchlist():
    return {"tickers": _watchlist}

@app.post("/api/watchlist")
def update_watchlist(req: WatchlistRequest):
    global _watchlist
    _watchlist = req.tickers
    return {"tickers": _watchlist}

@app.get("/api/graph")
def get_exposure_graph():
    return get_graph()

@app.post("/api/graph/node")
def add_node(node: Dict[str, Any]):
    try:
        add_graph_node(node)
        return {"status": "success", "graph": get_graph()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/graph/edge")
def add_edge(edge: Dict[str, Any]):
    try:
        add_graph_edge(edge)
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

def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
