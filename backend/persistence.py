"""
Lightweight JSON file persistence for watchlist and exposure graph state.
Files are stored in backend/state/ and survive backend restarts.
"""
import json
import os
from typing import Any, Dict, List

# State directory sits next to this file (backend/state/)
_STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
_WATCHLIST_FILE = os.path.join(_STATE_DIR, "watchlist.json")
_GRAPH_FILE = os.path.join(_STATE_DIR, "graph.json")


def _ensure_state_dir():
    os.makedirs(_STATE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Watchlist persistence
# ---------------------------------------------------------------------------

def load_watchlist(default: List[str]) -> List[str]:
    """Loads the persisted watchlist, or returns the default if none exists."""
    _ensure_state_dir()
    if not os.path.exists(_WATCHLIST_FILE):
        return list(default)
    try:
        with open(_WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        tickers = data.get("tickers", default)
        print(f"[persistence] Loaded watchlist from disk: {tickers}")
        return tickers
    except Exception as e:
        print(f"[persistence] Failed to load watchlist, using default: {e}")
        return list(default)


def save_watchlist(tickers: List[str]):
    """Persists the current watchlist to disk."""
    _ensure_state_dir()
    try:
        with open(_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"tickers": tickers}, f, indent=2)
    except Exception as e:
        print(f"[persistence] Failed to save watchlist: {e}")


# ---------------------------------------------------------------------------
# Exposure graph persistence
# ---------------------------------------------------------------------------

def load_graph(default: Dict[str, Any]) -> Dict[str, Any]:
    """Loads the persisted exposure graph, or returns the seed default if none exists."""
    _ensure_state_dir()
    if not os.path.exists(_GRAPH_FILE):
        return default
    try:
        with open(_GRAPH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        node_count = len(data.get("nodes", []))
        edge_count = len(data.get("edges", []))
        print(f"[persistence] Loaded graph from disk: {node_count} nodes, {edge_count} edges")
        return data
    except Exception as e:
        print(f"[persistence] Failed to load graph, using seed default: {e}")
        return default


def save_graph(graph: Dict[str, Any]):
    """Persists the current exposure graph state to disk."""
    _ensure_state_dir()
    try:
        with open(_GRAPH_FILE, "w", encoding="utf-8") as f:
            json.dump(graph, f, indent=2)
    except Exception as e:
        print(f"[persistence] Failed to save graph: {e}")
