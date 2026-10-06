"""LangGraph state. One dict threaded through the nodes; each node returns the keys it
changed. Kept intentionally flat and explainable (every member can read it)."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    # inputs
    message: str
    account_id: Optional[str]
    conversation_id: str
    product_version: Optional[str]
    as_of_date: str
    channel: str

    # derived
    account: Optional[dict]
    cross_account: bool
    intent: dict                 # IntentSignal.model_dump()
    candidates: list[dict]       # raw retrieval hits
    precedence: dict             # authoritative/supporting/conflicts/upcoming
    tools_invoked: list[dict]
    critic: Optional[dict]

    # outputs
    answer: str
    answer_type: str
    citations: list[dict]
    conflicts: list[dict]
    handoff_id: Optional[str]
    handoff: Optional[dict]
    pii_redacted: bool

    # audit / observability
    trace_id: str
    route: list[str]
    t_start: float
    llm_calls_start: int
