"""Iteration 3 pipeline: full cross-impact briefings.

fetch(+graph query expansion) -> extract(cross-impact focus) -> route(direct + cross-impact)
-> ledger dedup -> synthesize -> compliance
Uses the exposure graph to widen the news search, to route untickered macro/sector events to
watchlist tickers, and restores all (direct + indirect) story threads from memory.
"""
from typing import Dict, Any

from langgraph.graph import StateGraph, END

from backend.iterations.common import (
    WorkflowState,
    EXTRACTION_SYSTEM_PROMPT,
    cross_impact_focus,
    run_fetch_and_filter,
    run_extraction,
    route_events,
    run_ledger_dedup,
    run_synthesis,
    run_compliance_gate,
)


def fetch_node(state: WorkflowState) -> Dict[str, Any]:
    return run_fetch_and_filter(state, expand=True)


def extract_node(state: WorkflowState) -> Dict[str, Any]:
    focus = cross_impact_focus(
        state.get("watchlist", []),
        state.get("expansion_tickers", []),
        state.get("expansion_keywords", []),
    )
    return run_extraction(state, EXTRACTION_SYSTEM_PROMPT, focus)


def route_node(state: WorkflowState) -> Dict[str, Any]:
    return route_events(state, cross_impact=True)


def memory_node(state: WorkflowState) -> Dict[str, Any]:
    return run_ledger_dedup(state)


def synthesize_node(state: WorkflowState) -> Dict[str, Any]:
    return run_synthesis(state, restore_ledger=True, restore_indirect=True)


def compliance_node(state: WorkflowState) -> Dict[str, Any]:
    return run_compliance_gate(state)


def build_graph():
    wf = StateGraph(WorkflowState)
    wf.add_node("fetch_and_filter", fetch_node)
    wf.add_node("extract_events", extract_node)
    wf.add_node("route_events", route_node)
    wf.add_node("check_ledger", memory_node)
    wf.add_node("synthesize_ticker_briefings", synthesize_node)
    wf.add_node("compliance_gate", compliance_node)

    wf.set_entry_point("fetch_and_filter")
    wf.add_edge("fetch_and_filter", "extract_events")
    wf.add_edge("extract_events", "route_events")
    wf.add_edge("route_events", "check_ledger")
    wf.add_edge("check_ledger", "synthesize_ticker_briefings")
    wf.add_edge("synthesize_ticker_briefings", "compliance_gate")
    wf.add_edge("compliance_gate", END)
    return wf.compile()
