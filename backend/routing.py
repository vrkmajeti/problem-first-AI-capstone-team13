from typing import List, Dict, Any, Set
import copy
from backend.seed_data import EXPOSURE_GRAPH

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

def get_cross_impact_keywords(watchlist: List[str]) -> List[str]:
    """
    Finds keywords and query terms from nearby nodes connected to watchlist tickers in the exposure graph.
    Traverses the graph in reverse (from tickers outwards up to 2 hops) to find relevant search terms.
    """
    nodes = {n["nodeId"]: n for n in _graph_store["nodes"]}
    edges = _graph_store["edges"]
    
    # Find start nodes corresponding to the watchlist tickers
    watchlist_node_ids = set()
    ticker_to_node = {}
    for node_id, node in nodes.items():
        if node["nodeType"] == "ticker" and node["name"] in watchlist:
            watchlist_node_ids.add(node_id)
            ticker_to_node[node["name"]] = node_id
            
    if not watchlist_node_ids:
        return []
        
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
    
    # Collect query terms
    keywords = set()
    for node_id in relevant_nodes:
        node = nodes[node_id]
        # Skip the watchlist tickers themselves to avoid redundant search
        if node["nodeType"] == "ticker":
            continue
        # Add aliases and queryTerms
        keywords.update(node.get("queryTerms", []))
        
    return list(keywords)

def find_paths_to_watchlist(start_node_id: str, watchlist_node_ids: Set[str], max_hops: int = 3) -> List[List[Dict[str, Any]]]:
    """
    Finds all paths of length <= max_hops from start_node_id to any node in watchlist_node_ids.
    Returns a list of paths, where each path is a list of edge dicts.
    """
    edges = _graph_store["edges"]
    
    # Simple BFS/DFS pathfinding
    paths = []
    
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
                dfs(t, current_path + [edge], visited | {t})
            elif t == current_id and f not in visited:
                # Reverse edge traversal is valid since relationship is bi-directional exposure
                # We create a reversed version of the edge for path building
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
        if node["nodeType"] == "ticker" and node["name"] in watchlist:
            watchlist_node_ids.add(node_id)
            ticker_to_node[node["name"]] = node_id
            
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
    
    # Check node match
    for node_id, node in nodes.items():
        node_name_lower = node["name"].lower()
        node_aliases_lower = [a.lower() for a in node.get("aliases", [])]
        node_terms = [node_name_lower] + node_aliases_lower
        
        # If any query terms match
        for term in node_terms:
            if term in event_terms:
                matched_node_ids.add(node_id)
                break
        
        # Check substring match for safety
        for et in event_terms:
            if et in node_name_lower or any(et in a for a in node_aliases_lower):
                matched_node_ids.add(node_id)
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
            target_ticker = nodes[final_node_id]["name"]
            
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
