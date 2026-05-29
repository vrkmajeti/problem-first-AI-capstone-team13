from typing import List, Dict, Any, Set
import copy
import re
from backend.seed_data import EXPOSURE_GRAPH

def _is_match(event_term: str, node_text: str) -> bool:
    event_term = event_term.strip().lower()
    node_text = node_text.strip().lower()
    
    if not event_term or not node_text:
        return False
        
    # Exact match
    if event_term == node_text:
        return True
        
    # Word boundary match (highly robust and avoids substring issues like "ai" in "taiwan" or "hon hai")
    pattern = r'\b' + re.escape(event_term) + r'\b'
    if re.search(pattern, node_text):
        return True
        
    # Plural/Singular stem matching for terms of length >= 4
    if len(event_term) >= 4:
        # Check if one is a plural/singular variation of the other
        if event_term.endswith('s') and event_term[:-1] == node_text:
            return True
        if node_text.endswith('s') and node_text[:-1] == event_term:
            return True
            
    return False


# In-memory storage for exposure graph, initialized with seed data
_graph_store = copy.deepcopy(EXPOSURE_GRAPH)

def get_graph() -> Dict[str, Any]:
    """Returns the current state of the exposure graph."""
    return _graph_store

def add_graph_node(node: Dict[str, Any]):
    """Adds or updates a node in the exposure graph."""
    # Ensure node has required fields
    node_id = node.get("nodeId")
    if not node_id:
        raise ValueError("nodeId is required")
    
    # Remove existing if any
    _graph_store["nodes"] = [n for n in _graph_store["nodes"] if n["nodeId"] != node_id]
    _graph_store["nodes"].append(node)

def add_graph_edge(edge: Dict[str, Any]):
    """Adds or updates an edge in the exposure graph."""
    from_id = edge.get("fromNodeId")
    to_id = edge.get("toNodeId")
    if not from_id or not to_id:
        raise ValueError("fromNodeId and toNodeId are required")
        
    # Remove existing if any
    _graph_store["edges"] = [
        e for e in _graph_store["edges"] 
        if not (e["fromNodeId"] == from_id and e["toNodeId"] == to_id)
    ]
    _graph_store["edges"].append(edge)

def set_graph(graph: Dict[str, Any]):
    global _graph_store
    _graph_store = graph

def reset_graph() -> Dict[str, Any]:
    """Restores the exposure graph to the curated seed, discarding all runtime additions."""
    global _graph_store
    _graph_store = copy.deepcopy(EXPOSURE_GRAPH)
    return _graph_store

from typing import Tuple

def get_cross_impact_queries(watchlist: List[str]) -> Tuple[List[str], List[str]]:
    """
    Finds keywords and query terms from nearby nodes connected to watchlist tickers in the exposure graph.
    Traverses the graph in reverse (from tickers outwards up to 2 hops) to find relevant search terms.
    Returns a tuple: (cross_impact_keywords, extra_tickers)
    """
    nodes = {n["nodeId"]: n for n in _graph_store["nodes"]}
    edges = _graph_store["edges"]
    
    # Find start nodes corresponding to the watchlist tickers
    watchlist_node_ids = set()
    for node_id, node in nodes.items():
        if node["nodeType"] == "ticker" and node.get("ticker") in watchlist:
            watchlist_node_ids.add(node_id)
            
    if not watchlist_node_ids:
        return [], []
        
    # Collect query terms from these nodes and their 1-hop and 2-hop neighbors
    relevant_nodes = set(watchlist_node_ids)
    
    # 1st Hop
    neighbors_1 = set()
    for edge in edges:
        f, t = edge["fromNodeId"], edge["toNodeId"]
        if f in relevant_nodes:
            neighbors_1.add(t)
        if t in relevant_nodes:
            neighbors_1.add(f)
            
    relevant_nodes.update(neighbors_1)
    
    # 2nd Hop
    neighbors_2 = set()
    for edge in edges:
        f, t = edge["fromNodeId"], edge["toNodeId"]
        if f in neighbors_1:
            neighbors_2.add(t)
        if t in neighbors_1:
            neighbors_2.add(f)
            
    relevant_nodes.update(neighbors_2)
    
    # Collect query terms and extra tickers
    keywords = set()
    extra_tickers = set()
    for node_id in relevant_nodes:
        node = nodes[node_id]
        # Include company name, aliases, and query terms to search Currents by name
        keywords.update(node.get("queryTerms", []))
        keywords.add(node["name"])
        keywords.update(node.get("aliases", []))
        
        # If this node represents a company with a ticker and is not on the watchlist,
        # collect its ticker to query Finnhub
        node_ticker = node.get("ticker")
        if node_ticker and node_ticker not in watchlist:
            extra_tickers.add(node_ticker)
            
    return list(keywords), list(extra_tickers)


def get_cross_impact_keywords(watchlist: List[str]) -> List[str]:
    """Finds keywords and query terms from nearby nodes. Maintained for backward compatibility."""
    keywords, _ = get_cross_impact_queries(watchlist)
    return keywords

def find_paths_to_watchlist(start_node_id: str, watchlist_node_ids: Set[str], max_hops: int = 3) -> List[List[Dict[str, Any]]]:
    """
    Finds all paths of length <= max_hops from start_node_id to any node in watchlist_node_ids.
    Returns a list of paths, where each path is a list of edge dicts.
    """
    nodes = {n["nodeId"]: n for n in _graph_store["nodes"]}
    edges = _graph_store["edges"]
    company_types = {"ticker", "private_company"}
    
    # Simple BFS/DFS pathfinding
    paths = []
    
    def is_allowed_transition(current_id: str, neighbor_id: str, edge: Dict[str, Any]) -> bool:
        c_node = nodes.get(current_id)
        n_node = nodes.get(neighbor_id)
        if not c_node or not n_node:
            return False
            
        c_type = c_node.get("nodeType")
        n_type = n_node.get("nodeType")
        
        # If it is an exposure/sensitivity edge:
        if edge.get("edgeType") in {
            "regional_exposure", "technology_exposure", "shipping_exposure", 
            "macro_sensitivity", "sector_exposure", "commodity_exposure"
        }:
            is_c_company = c_type in company_types
            is_n_company = n_type in company_types
            
            if is_c_company and not is_n_company:
                # Company -> Macro transition is NOT allowed for exposure edges (exposure flows macro -> company)
                return False
                
            if not is_c_company and is_n_company:
                # Macro -> Company transition IS allowed
                return True
                
            if not is_c_company and not is_n_company:
                # Both are macro nodes. Follow the edge's original direction.
                # Traverse only if current_id is the original fromNodeId and neighbor_id is the original toNodeId
                return edge.get("fromNodeId") == current_id and edge.get("toNodeId") == neighbor_id
                
        # For company-to-company edges (supplier_of, customer_of, competitor_of, partner_of), bi-directional is fine.
        return True
    
    def dfs(current_id: str, current_path: List[Dict[str, Any]], visited: Set[str]):
        if len(current_path) > max_hops:
            return
            
        if current_id in watchlist_node_ids:
            paths.append(list(current_path))
            # Keep searching in case there are other paths
            
        # Find neighbors (can traverse edges in both directions or directed.
        # Since exposures can represent causal influence, they can flow both ways in terms of correlation, 
        # but typically we traverse from Event Node -> Ticker.
        # Let's check both directions, representing general connection.
        for edge in edges:
            f, t = edge["fromNodeId"], edge["toNodeId"]
            if f == current_id and t not in visited:
                if is_allowed_transition(current_id, t, edge):
                    dfs(t, current_path + [edge], visited | {t})
            elif t == current_id and f not in visited:
                # Reverse edge traversal is valid since relationship is bi-directional exposure
                # We create a reversed version of the edge for path building
                if is_allowed_transition(current_id, f, edge):
                    rev_edge = copy.deepcopy(edge)
                    rev_edge["fromNodeId"], rev_edge["toNodeId"] = t, f
                    dfs(f, current_path + [rev_edge], visited | {f})
                
    dfs(start_node_id, [], {start_node_id})
    return paths

def route_cross_impact(canonical_event: Dict[str, Any], watchlist: List[str]) -> List[Dict[str, Any]]:
    """
    Routes an untickered canonical event to watchlist tickers using exposure graph path traversal.
    """
    nodes = {n["nodeId"]: n for n in _graph_store["nodes"]}
    watchlist_node_ids = set()
    ticker_to_node = {}
    
    for node_id, node in nodes.items():
        if node["nodeType"] == "ticker" and node.get("ticker") in watchlist:
            watchlist_node_ids.add(node_id)
            ticker_to_node[node.get("ticker")] = node_id
            
    if not watchlist_node_ids:
        return []
        
    # Match event entities and tags to graph nodes
    matched_node_ids = set()
    
    # Search fields in canonical event
    event_entities = [e.lower() for e in canonical_event.get("entities", [])]
    event_tags = [t.lower() for t in canonical_event.get("eventTags", [])]
    event_regions = [r.lower() for r in canonical_event.get("regions", []) or []]
    event_themes = [t.lower() for t in canonical_event.get("technologyThemes", []) or []]
    
    event_terms = set(event_entities + event_tags + event_regions + event_themes)
    
    # Check node match using word-boundary and stem matching
    for node_id, node in nodes.items():
        node_name_lower = node["name"].lower()
        node_aliases_lower = [a.lower() for a in node.get("aliases", [])]
        node_terms = [node_name_lower] + node_aliases_lower
        if node.get("ticker"):
            node_terms.append(node["ticker"].lower())
        
        matched = False
        for term in node_terms:
            for et in event_terms:
                if _is_match(et, term):
                    matched_node_ids.add(node_id)
                    matched = True
                    break
            if matched:
                break
                
    candidates = []
    
    # Traverse paths from each matched node to watchlist tickers
    for start_node_id in matched_node_ids:
        paths = find_paths_to_watchlist(start_node_id, watchlist_node_ids, max_hops=3)
        
        for path in paths:
            if not path:
                continue
                
            # Path node list for visualization
            path_nodes = [start_node_id]
            for edge in path:
                path_nodes.append(edge["toNodeId"])
                
            final_node_id = path_nodes[-1]
            target_ticker = nodes[final_node_id].get("ticker") or nodes[final_node_id]["name"]
            
            # Calculate path score
            # path_score = event_severity * average_edge_confidence * path_shortness_bonus
            # Severity mapping from possibleDirectionalPressure
            severity_str = canonical_event.get("possibleDirectionalPressure", "unclear")
            if severity_str in ["positive", "negative"]:
                event_severity = 1.0
            elif severity_str == "mixed":
                event_severity = 0.8
            else:
                event_severity = 0.5
                
            edge_confidences = [edge.get("confidence", 0.8) for edge in path]
            average_edge_confidence = sum(edge_confidences) / len(edge_confidences)
            
            # Path shortness bonus: 1 hop = 1.0, 2 hops = 0.9, 3 hops = 0.75
            hops = len(path)
            if hops == 1:
                path_shortness_bonus = 1.0
            elif hops == 2:
                path_shortness_bonus = 0.9
            else:
                path_shortness_bonus = 0.75
                
            path_score = event_severity * average_edge_confidence * path_shortness_bonus
 
            # Route if path score >= 0.45; tag "strong" (>=0.70) vs "weak" (0.45-0.69)
            # so the synthesis LLM can treat marginal paths as watch items, not primary catalysts
            if path_score >= 0.45:
                # Construct path details/explanation
                explanations = []
                for edge in path:
                    notes = edge.get("notes", "")
                    from_name = nodes[edge["fromNodeId"]]["name"]
                    to_name = nodes[edge["toNodeId"]]["name"]
                    rel_type = edge["edgeType"]
                    explanations.append(f"{from_name} ({rel_type}) -> {to_name}. {notes}")
 
                reason_for_routing = "; ".join(explanations)
                path_strength = "strong" if path_score >= 0.70 else "weak"
 
                candidates.append({
                    "candidateId": f"cand_{target_ticker}_{canonical_event.get('eventId', '')[:8]}",
                    "ticker": target_ticker,
                    "relationshipType": "indirect",
                    "eventId": canonical_event.get("eventId"),
                    "impactPath": [nodes[nid]["name"] for nid in path_nodes],
                    "pathConfidence": round(path_score, 2),
                    "pathStrength": path_strength,
                    "reasonForRouting": reason_for_routing
                })
                
    # Deduplicate candidate connections (take highest score path for a ticker-event pair)
    best_candidates = {}
    for cand in candidates:
        key = (cand["ticker"], cand["eventId"])
        if key not in best_candidates or cand["pathConfidence"] > best_candidates[key]["pathConfidence"]:
            best_candidates[key] = cand
            
    return list(best_candidates.values())

