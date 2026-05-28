"""
Exposure-graph expansion.

Runs ONCE when a new ticker is added to the watchlist. It uses an LLM to discover
the causal exposure surrounding the ticker (suppliers, partners, regions, technology
themes, macro/commodity risk factors, shipping routes) and merges the resulting nodes
and edges into the live exposure graph. It is NOT re-run on pipeline refreshes.
"""
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import GEMINI_API_KEY, OPENAI_API_KEY, get_llm
from backend.routing import get_graph, add_graph_node, add_graph_edge


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
    "technology_exposure",
    "regional_exposure",
    "shipping_exposure",
    "macro_sensitivity",
    "sector_exposure",
    "commodity_exposure",
}


class GraphExpansionError(Exception):
    """Raised when a configured LLM fails to produce a usable expansion."""


def _clean_json_string(text: str) -> str:
    """Strips markdown JSON code fences from LLM output if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


SYSTEM_PROMPT = """You are a financial exposure-graph architect. A new stock ticker has just been added to an intraday trading watchlist.
Your job is to map the causal exposure surrounding this ticker so a news system can route INDIRECT news \
(supply-chain disruptions, geopolitics, technology themes, macro shocks, commodities, key partners) to this ticker.

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
  "edgeType": "supplier_of" | "technology_exposure" | "regional_exposure" | "shipping_exposure" | "macro_sensitivity" | "sector_exposure" | "commodity_exposure",
  "strength": "high" | "medium" | "low",
  "confidence": 0.0-1.0,
  "notes": "one sentence explaining the causal relationship"
}

Rules:
1. REUSE existing nodes: if an exposure entity already exists in the provided node list (e.g. theme_semiconductors, region_Taiwan, ticker_TSM), reference its EXACT existing nodeId in edges — do NOT create a duplicate node.
2. Produce 3-8 strong, decision-relevant exposure links for intraday trading — not an exhaustive list.
3. Use only REAL, well-known suppliers, partners, regions, and themes. Do NOT invent companies.
4. confidence reflects how directly the source moves this ticker intraday (0.9+ = near-certain causal link, 0.5 = plausible/marginal).
5. Every edge's fromNodeId and toNodeId must be either the new ticker node, one of your new nodes, or an existing nodeId from the provided list.
6. Output ONLY valid JSON. No markdown, no commentary.
"""


def _bare_ticker_node(ticker: str) -> Dict[str, Any]:
    return {
        "nodeId": f"ticker_{ticker}",
        "nodeType": "ticker",
        "name": ticker,
        "aliases": [],
        "queryTerms": [ticker],
    }


def expand_graph_for_ticker(ticker: str) -> Dict[str, Any]:
    """
    Discovers and merges exposure-graph nodes/edges for a newly added ticker.

    Behaviour:
      - If the ticker node already exists, this is a no-op (expansion runs once per ticker).
      - With no LLM keys configured (demo/mock mode), adds only the bare ticker node.
      - With a configured LLM, merges the LLM-generated subgraph. Raises GraphExpansionError
        if the LLM call fails or returns unusable output (caller should reject the change).

    Returns a summary dict.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise GraphExpansionError("Empty ticker symbol.")

    ticker_node_id = f"ticker_{ticker}"
    existing_nodes = get_graph()["nodes"]

    # Expansion is once-per-ticker: if the node is already present, do nothing.
    if any(n["nodeId"] == ticker_node_id for n in existing_nodes):
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
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        payload = json.loads(_clean_json_string(response.content))
    except Exception as e:
        raise GraphExpansionError(f"LLM expansion failed for {ticker}: {e}") from e

    if not isinstance(payload, dict):
        raise GraphExpansionError(f"LLM returned non-object payload for {ticker}.")

    raw_nodes = payload.get("nodes", [])
    raw_edges = payload.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise GraphExpansionError(f"LLM payload missing valid 'nodes'/'edges' lists for {ticker}.")

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
