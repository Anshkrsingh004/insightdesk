r"""Assemble the LangGraph. Mostly linear with a code-controlled branch after classify
(the orchestrator decides retrieve-vs-decline). Tool / critic / escalation branches are
added in Phases 3-4.

    START -> authorize -> classify -> (route) -> retrieve -> compose -> finalize -> END
                                           \-> decline -----------------^
"""
from __future__ import annotations

import time
import uuid
from functools import lru_cache
from typing import Optional

from langgraph.graph import END, START, StateGraph

from ..llm import get_llm
from . import nodes
from .state import GraphState


def _route_after_classify(state: dict) -> str:
    if state.get("cross_account"):
        return "decline"
    if (state.get("intent") or {}).get("type") == "out_of_scope":
        return "decline"
    return "retrieve"


@lru_cache
def get_graph():
    g = StateGraph(GraphState)
    g.add_node("authorize", nodes.authorize)
    g.add_node("classify", nodes.classify)
    g.add_node("retrieve", nodes.retrieve)
    g.add_node("compose", nodes.compose)
    g.add_node("decline", nodes.decline)
    g.add_node("finalize", nodes.finalize)

    g.add_edge(START, "authorize")
    g.add_edge("authorize", "classify")
    g.add_conditional_edges("classify", _route_after_classify,
                            {"retrieve": "retrieve", "decline": "decline"})
    g.add_edge("retrieve", "compose")
    g.add_edge("compose", "finalize")
    g.add_edge("decline", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def run_support(*, message: str, account_id: Optional[str], conversation_id: Optional[str],
                product_version: Optional[str], as_of_date: str, channel: str = "web") -> dict:
    trace_id = uuid.uuid4().hex[:8]
    conv_id = conversation_id or f"C-{uuid.uuid4().hex[:6]}"
    init: dict = {
        "message": message, "account_id": account_id, "conversation_id": conv_id,
        "product_version": product_version, "as_of_date": as_of_date, "channel": channel,
        "trace_id": trace_id, "route": [], "t_start": time.time(),
        "llm_calls_start": get_llm().calls,
        "tools_invoked": [], "citations": [], "conflicts": [],
    }
    return get_graph().invoke(init)
