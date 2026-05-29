"""Iteration 2 pipeline: direct-news briefings WITH catalyst memory (dedup).

fetch -> extract(direct focus) -> route(direct only) -> ledger dedup -> synthesize -> compliance
Adds the catalyst ledger: duplicates are suppressed and ongoing stories accumulate facts.
Cross-impact is NOT active here, so synthesis restores direct story threads only.
"""
from typing import Dict, Any

from langgraph.graph import StateGraph, END

from backend.iterations.common import (
    WorkflowState,
    EXTRACTION_SYSTEM_PROMPT,
    direct_focus,
    run_fetch_and_filter,
    run_extraction,
    route_events,
    run_ledger_dedup,
    run_synthesis,
    run_compliance_gate,
)


def fetch_node(state: WorkflowState) -> Dict[str, Any]:
    return run_fetch_and_filter(state, expand=False)


def extract_node(state: WorkflowState) -> Dict[str, Any]:
    focus = direct_focus(state.get("watchlist", []))
    return run_extraction(state, EXTRACTION_SYSTEM_PROMPT, focus)


def route_node(state: WorkflowState) -> Dict[str, Any]:
    return route_events(state, cross_impact=False)


def memory_node(state: WorkflowState) -> Dict[str, Any]:
    return run_ledger_dedup(state)


def synthesize_node(state: WorkflowState) -> Dict[str, Any]:
    return run_synthesis(state, restore_ledger=True, restore_indirect=False)


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
