"""
Exposure-graph expansion.

When a ticker is added to the watchlist, the add itself is NOT blocked: the LLM-driven
expansion runs afterwards as a background task. It discovers the causal exposure
surrounding the ticker (suppliers, customers, competitors, partners, regions, technology
themes, macro/commodity risk factors, shipping routes) and merges the resulting nodes
and edges into the live exposure graph. Per-ticker progress is tracked in an in-memory
status store so the UI can show a pending/ready/failed state and offer a manual re-run.
It is NOT re-run on pipeline refreshes.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Literal, Optional

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import GEMINI_API_KEY, OPENAI_API_KEY, get_llm
from backend.graph import invoke_with_retry
from backend.routing import get_graph, add_graph_node, add_graph_edge
from backend.persistence import save_graph


# Node/edge vocabulary mirrors backend/seed_data.py so generated graph elements are
# interchangeable with the manually seeded ones.
VALID_NODE_TYPES = {
    "ticker",
    "private_company",
    "region",
    "technology_theme",
    "shipping_route",
    "risk_factor",
    "sector",
    "commodity",
}

VALID_EDGE_TYPES = {
    "supplier_of",
    "customer_of",
    "competitor_of",
    "partner_of",
    "technology_exposure",
    "regional_exposure",
    "shipping_exposure",
    "macro_sensitivity",
    "sector_exposure",
    "commodity_exposure",
}


class GraphExpansionError(Exception):
    """Raised when a configured LLM fails to produce a usable expansion."""


# Structured-output schemas (constrained decoding). Binding these via
# `.with_structured_output(...)` guarantees the model emits schema-valid JSON, so a
# missing delimiter can never sink an expansion. The referential-integrity checks
# below (edges must point at known nodeIds) still run — structured outputs enforces
# SHAPE, not whether a generated nodeId actually exists in the graph.
NodeTypeLiteral = Literal[
    "ticker", "private_company", "region", "technology_theme",
    "shipping_route", "risk_factor", "sector", "commodity",
]
EdgeTypeLiteral = Literal[
    "supplier_of", "customer_of", "competitor_of", "partner_of",
    "technology_exposure", "regional_exposure", "shipping_exposure",
    "macro_sensitivity", "sector_exposure", "commodity_exposure",
]


class ExpansionNode(BaseModel):
    nodeId: str
    nodeType: NodeTypeLiteral
    name: str
    aliases: List[str]
    queryTerms: List[str]


class ExpansionEdge(BaseModel):
    fromNodeId: str
    toNodeId: str
    edgeType: EdgeTypeLiteral
    strength: Literal["high", "medium", "low"]
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str


class GraphExpansionResult(BaseModel):
    nodes: List[ExpansionNode]
    edges: List[ExpansionEdge]


# ---------------------------------------------------------------------------
# Per-ticker expansion status store (in-memory; drives the UI pending indicator)
# ---------------------------------------------------------------------------
# status: "pending" (queued) | "running" | "done" | "skipped" | "failed"
_expansion_status: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_status(ticker: str, status: str, **extra: Any) -> None:
    entry = {"ticker": ticker, "status": status, "updatedAt": _now_iso()}
    entry.update(extra)
    _expansion_status[ticker] = entry


def get_expansion_status() -> Dict[str, Dict[str, Any]]:
    """Returns the full per-ticker expansion status map."""
    return _expansion_status


def mark_pending(ticker: str) -> None:
    """Marks a ticker as queued for expansion (called before scheduling the task)."""
    _set_status(ticker.strip().upper(), "pending")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


SYSTEM_PROMPT = """You are a financial exposure-graph architect. A new stock ticker has just been added to an intraday trading watchlist.
Your job is to map the causal exposure surrounding this ticker COMPREHENSIVELY, so a news system can route INDIRECT news \
(supply-chain disruptions, geopolitics, technology themes, macro shocks, commodities, competitors, key partners) to this ticker.

You will be given:
- The new ticker symbol.
- The nodes ALREADY in the exposure graph (each with nodeId, name, nodeType).

Return a single JSON object with two keys: "nodes" and "edges".

"nodes": a list of NEW nodes to add. Do NOT duplicate nodes that already exist — reference those by their existing nodeId inside "edges" instead.
You MUST include exactly one node for the ticker itself:
{
  "nodeId": "ticker_<SYMBOL>",
  "nodeType": "ticker",
  "name": "<SYMBOL>",
  "aliases": ["common company names, e.g. Alphabet, Google"],
  "queryTerms": ["search keywords: company name, ticker, flagship products/brands"]
}
For each relevant exposure entity that is NOT already in the graph, add a node:
{
  "nodeId": "<type>_<ShortName>",   e.g. supplier_Foxconn, region_Taiwan, theme_semiconductors, risk_oil_price, commodity_lithium, route_Red_Sea, sector_cloud
  "nodeType": "private_company" | "region" | "technology_theme" | "shipping_route" | "risk_factor" | "sector" | "commodity",
  "name": "Human readable name",
  "aliases": ["alternative names"],
  "queryTerms": ["news search keywords for this entity"]
}

"edges": a list of directed exposure edges. Point each edge FROM the cause/source node TO the affected node (usually the ticker).
{
  "fromNodeId": "<source nodeId — a new node OR an existing nodeId from the provided list>",
  "toNodeId": "ticker_<SYMBOL>  (or another node when modelling an intermediate hop)",
  "edgeType": "supplier_of" | "customer_of" | "competitor_of" | "partner_of" | "technology_exposure" | "regional_exposure" | "shipping_exposure" | "macro_sensitivity" | "sector_exposure" | "commodity_exposure",
  "strength": "high" | "medium" | "low",
  "confidence": 0.0-1.0,
  "notes": "one sentence explaining the causal relationship"
}

Rules:
1. REUSE existing nodes: if an exposure entity already exists in the provided node list (e.g. theme_semiconductors, region_Taiwan, ticker_TSM), reference its EXACT existing nodeId in edges — do NOT create a duplicate node.
2. Be COMPREHENSIVE, not conservative. Produce roughly 8-15 exposure links covering the full surface: key SUPPLIERS, major CUSTOMERS, direct COMPETITORS, strategic PARTNERS, regions of operation/revenue concentration, relevant technology themes, input COMMODITIES, macro/rate/fuel sensitivities, and shipping/logistics routes where they genuinely apply. Include both strong and plausible-but-secondary links (use confidence to grade them) — a sparse graph misses cross-impact news.
3. CONNECT TO OTHER WATCHLIST TICKERS when a real relationship exists: if an existing ticker_* node is a supplier, customer, or competitor of the new ticker, add that edge (e.g. competitor_of between two chipmakers, supplier_of from a foundry ticker to a fabless ticker).
4. Use only REAL, well-known entities. Do NOT invent companies.
5. confidence reflects how directly the source moves this ticker intraday (0.9+ = near-certain causal link, 0.6 = relevant, 0.45 = plausible/marginal). Do not omit a real link just because it is secondary — grade it with a lower confidence instead.
6. Every edge's fromNodeId and toNodeId must be either the new ticker node, one of your new nodes, or an existing nodeId from the provided list.
"""


def _bare_ticker_node(ticker: str) -> Dict[str, Any]:
    return {
        "nodeId": f"ticker_{ticker}",
        "nodeType": "ticker",
        "name": ticker,
        "aliases": [],
        "queryTerms": [ticker],
    }


def expand_graph_for_ticker(ticker: str, force: bool = False) -> Dict[str, Any]:
    """
    Discovers and merges exposure-graph nodes/edges for a ticker.

    Behaviour:
      - If the ticker node already exists and ``force`` is False, this is a no-op
        (automatic expansion runs once per ticker).
      - With ``force=True`` (manual re-run), it re-queries the LLM and merges again,
        enriching the existing subgraph (merges are idempotent by nodeId / edge pair).
      - With no LLM keys configured (demo/mock mode), adds only the bare ticker node.
      - Raises GraphExpansionError if a configured LLM call fails or returns unusable output.

    Returns a summary dict. Does NOT persist or update status — see process_ticker_expansion.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise GraphExpansionError("Empty ticker symbol.")

    ticker_node_id = f"ticker_{ticker}"
    existing_nodes = get_graph()["nodes"]
    already_present = any(n["nodeId"] == ticker_node_id for n in existing_nodes)

    # Automatic expansion is once-per-ticker. A manual re-run (force=True) bypasses this.
    if already_present and not force:
        print(f"[graph_expansion] {ticker} already in graph — skipping expansion.")
        return {"ticker": ticker, "addedNodes": 0, "addedEdges": 0, "usedLLM": False, "skipped": True}

    # Demo/mock mode: no LLM available. Register the bare ticker node so cross-impact
    # routing has a valid target; richer links require API keys.
    if not (GEMINI_API_KEY or OPENAI_API_KEY):
        add_graph_node(_bare_ticker_node(ticker))
        print(f"[graph_expansion] No LLM keys configured — added bare node for {ticker} only.")
        return {"ticker": ticker, "addedNodes": 1, "addedEdges": 0, "usedLLM": False}

    # --- LLM-driven expansion ---
    existing_context = [
        {"nodeId": n["nodeId"], "name": n["name"], "nodeType": n["nodeType"]}
        for n in existing_nodes
    ]
    user_prompt = (
        f"NEW TICKER: {ticker}\n\n"
        f"EXISTING GRAPH NODES (reuse these nodeIds in edges where relevant):\n"
        f"{json.dumps(existing_context, indent=2)}\n\n"
        f"Map the causal exposure for {ticker} and return the JSON object."
    )

    try:
        llm = get_llm().with_structured_output(GraphExpansionResult)
        result: GraphExpansionResult = invoke_with_retry(
            llm,
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)],
            label=f"graph expansion for {ticker}",
        )
        payload = result.model_dump()
    except Exception as e:
        raise GraphExpansionError(f"LLM expansion failed for {ticker}: {e}") from e

    raw_nodes = payload["nodes"]
    raw_edges = payload["edges"]

    # --- Validate & collect new nodes ---
    clean_nodes: List[Dict[str, Any]] = []
    seen_node_ids = set()
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        node_id = n.get("nodeId")
        node_type = n.get("nodeType")
        name = n.get("name")
        if not node_id or not name or node_type not in VALID_NODE_TYPES:
            print(f"[graph_expansion] Dropping invalid node: {n}")
            continue
        if node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        clean_nodes.append({
            "nodeId": node_id,
            "nodeType": node_type,
            "name": name,
            "aliases": n.get("aliases", []) or [],
            "queryTerms": n.get("queryTerms", []) or [],
        })

    # Guarantee the ticker node exists even if the LLM omitted it.
    if not any(n["nodeId"] == ticker_node_id for n in clean_nodes):
        clean_nodes.append(_bare_ticker_node(ticker))
        seen_node_ids.add(ticker_node_id)

    # Valid edge endpoints = existing graph nodes + the new nodes we just accepted.
    valid_ids = {n["nodeId"] for n in existing_nodes} | seen_node_ids

    today = _today()
    clean_edges: List[Dict[str, Any]] = []
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        from_id = e.get("fromNodeId")
        to_id = e.get("toNodeId")
        edge_type = e.get("edgeType")
        if from_id not in valid_ids or to_id not in valid_ids or from_id == to_id:
            print(f"[graph_expansion] Dropping edge with unknown/self endpoints: {from_id} -> {to_id}")
            continue
        if edge_type not in VALID_EDGE_TYPES:
            print(f"[graph_expansion] Dropping edge with invalid edgeType '{edge_type}': {from_id} -> {to_id}")
            continue
        try:
            confidence = float(e.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))
        clean_edges.append({
            "fromNodeId": from_id,
            "toNodeId": to_id,
            "edgeType": edge_type,
            "strength": e.get("strength", "medium"),
            "confidence": round(confidence, 2),
            "sourceType": "llm_generated",
            "notes": e.get("notes", ""),
            "lastReviewedAt": today,
        })

    # --- Merge into the live graph ---
    for n in clean_nodes:
        add_graph_node(n)
    for e in clean_edges:
        add_graph_edge(e)

    print(f"[graph_expansion] {ticker}: merged {len(clean_nodes)} nodes, {len(clean_edges)} edges via LLM.")
    return {
        "ticker": ticker,
        "addedNodes": len(clean_nodes),
        "addedEdges": len(clean_edges),
        "usedLLM": True,
    }


def process_ticker_expansion(ticker: str, force: bool = False) -> Dict[str, Any]:
    """
    Background-task entrypoint. Runs the expansion, persists the graph on success, and
    records the outcome in the status store. Never raises — failures are surfaced via
    the status entry so the UI can offer a manual re-run.
    """
    ticker = ticker.strip().upper()
    _set_status(ticker, "running")
    try:
        summary = expand_graph_for_ticker(ticker, force=force)
        save_graph(get_graph())
        final_status = "skipped" if summary.get("skipped") else "done"
        _set_status(
            ticker,
            final_status,
            addedNodes=summary.get("addedNodes", 0),
            addedEdges=summary.get("addedEdges", 0),
            usedLLM=summary.get("usedLLM", False),
        )
        return summary
    except Exception as e:
        print(f"[graph_expansion] Background expansion failed for {ticker}: {e}")
        _set_status(ticker, "failed", error=str(e))
        return {"ticker": ticker, "status": "failed", "error": str(e)}
