r"""Assemble the LangGraph. A code-controlled branch after classify, the retrieve/tool/
answer path, a bounded one-shot critic→revise loop, and the Escalation Policy Engine
deciding answer-vs-escalate.

  START -> authorize -> classify -> (route) -> retrieve -> tools -> compose -> critic
                           |  \-> clarify -------------------------------------^  |
                           |  \-> decline -----------------------------------^    |
                           |                                   revise <-----------+ (<=1)
                           |                                      ^-> compose
                           +-> decide -> (escalate | finalize) -> END
"""
from __future__ import annotations

import re
import time
import uuid
from functools import lru_cache
from typing import Optional

from langgraph.graph import END, START, StateGraph

from ..llm import get_llm
from . import nodes
from .state import GraphState

_SPECIFIC = re.compile(r"cf-\d{3}|\b429\b|\b401\b|refund|export|password|invoice|rate limit|"
                       r"connector|webhook|salesforce|slack|seat|usage|billing|workflow", re.I)


def _is_vague(message: str) -> bool:
    t = (message or "").strip().lower()
    if len(t.split()) <= 5 and any(p in t for p in (
            "not working", "broken", "doesn't work", "does not work", "help", "issue",
            "problem", "error", "it failed", "stuck")) and not _SPECIFIC.search(t):
        return True
    return False


def _route_after_classify(state: dict) -> str:
    if state.get("cross_account"):
        return "decline"
    if (state.get("intent") or {}).get("type") == "out_of_scope":
        return "decline"
    if _is_vague(state.get("message", "")):
        return "clarify"
    return "retrieve"


def _after_critic(state: dict) -> str:
    crit = state.get("critic") or {}
    if crit.get("decision") == "revise" and state.get("revisions", 0) < 1:
        return "revise"
    return "decide"


def _after_decide(state: dict) -> str:
    return "escalate" if state.get("esc_decision") else "finalize"


@lru_cache
def get_graph():
    g = StateGraph(GraphState)
    for name, fn in [
        ("authorize", nodes.authorize), ("classify", nodes.classify),
        ("retrieve", nodes.retrieve), ("tools", nodes.run_tools),
        ("compose", nodes.compose), ("critique", nodes.critic),
        ("revise", nodes.revise), ("decide", nodes.decide),
        ("escalate", nodes.escalate), ("clarify", nodes.clarify),
        ("decline", nodes.decline), ("finalize", nodes.finalize),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "authorize")
    g.add_edge("authorize", "classify")
    g.add_conditional_edges("classify", _route_after_classify,
                            {"retrieve": "retrieve", "clarify": "clarify", "decline": "decline"})
    g.add_edge("retrieve", "tools")
    g.add_edge("tools", "compose")
    g.add_edge("compose", "critique")
    g.add_conditional_edges("critique", _after_critic, {"revise": "revise", "decide": "decide"})
    g.add_edge("revise", "compose")
    g.add_conditional_edges("decide", _after_decide, {"escalate": "escalate", "finalize": "finalize"})
    g.add_edge("escalate", "finalize")
    g.add_edge("clarify", "finalize")
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
        "tools_invoked": [], "citations": [], "conflicts": [], "revisions": 0,
    }
    return get_graph().invoke(init)
