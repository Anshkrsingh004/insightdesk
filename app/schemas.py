"""Pydantic v2 models = the fixed API contract (Section 6) + structured LLM I/O.

These types are the single source of truth. Every LLM node returns a validated
instance of one of the *Signal models below (IntentSignal, ComposerSignal,
CriticSignal); deterministic code consumes those signals. Nothing downstream
trusts raw model text.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (as Literals so Pydantic validates model output and rejects garbage)
# ---------------------------------------------------------------------------
IntentType = Literal[
    "how_to", "troubleshooting", "account", "billing",
    "complaint", "security", "out_of_scope",
]
Urgency = Literal["low", "medium", "high"]
Sentiment = Literal["positive", "neutral", "negative", "frustrated", "angry"]
AnswerType = Literal[
    "answered", "clarification_needed", "escalated",
    "not_found", "refused", "out_of_scope",
]
RiskLevel = Literal["none", "low", "medium", "high"]
Coverage = Literal["complete", "partial", "none"]
CriticDecision = Literal["answer", "revise", "escalate"]
DocType = Literal["article", "policy", "release_note", "ticket", "community"]
Priority = Literal["low", "normal", "high", "urgent"]


# ---------------------------------------------------------------------------
# Structured LLM signals (R1 classifier, composer, R4 critic)
# ---------------------------------------------------------------------------
class IntentSignal(BaseModel):
    """R1: structured classification. `tools_needed` guides routing."""
    type: IntentType = "out_of_scope"
    urgency: Urgency = "low"
    sentiment: Sentiment = "neutral"
    pii_detected: bool = False
    tools_needed: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    explicit_human_request: bool = False


class ComposerSignal(BaseModel):
    """Draft answer + which retrieved source_ids it used (for groundedness check)."""
    answer: str = ""
    used_source_ids: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


class CriticSignal(BaseModel):
    """R4: the critic emits SCORES only. Code decides answer/revise/escalate."""
    groundedness: float = 0.0
    coverage: Coverage = "none"
    pii_risk: RiskLevel = "none"
    policy_risk: RiskLevel = "none"
    decision: CriticDecision = "escalate"  # advisory; code may override per Annex A.3
    revisions: int = 0
    notes: str = ""


# ---------------------------------------------------------------------------
# Public response pieces (Section 6.1)
# ---------------------------------------------------------------------------
class IntentPublic(BaseModel):
    type: IntentType
    urgency: Urgency
    sentiment: Sentiment
    pii_detected: bool
    confidence: float


class Citation(BaseModel):
    source_id: str
    doc_type: DocType
    section: str = ""
    product_versions: str = ""
    last_updated: str = ""


class ToolInvocation(BaseModel):
    tool: str
    output: Any


class Conflict(BaseModel):
    """Recorded when sources disagree (Annex A.2 step 3: ticket vs documentation)."""
    reason: str
    winner_source_id: str = ""
    loser_source_id: str = ""


# ---------------------------------------------------------------------------
# Handoff bundle (Annex D)
# ---------------------------------------------------------------------------
class HandoffBundle(BaseModel):
    queue: str = "general"            # billing | technical | security | general
    priority: Priority = "normal"
    intent: str = ""
    urgency: str = ""
    sentiment: str = ""
    escalation_reasons: list[str] = Field(default_factory=list)
    customer_summary: str = ""
    evidence: list[dict] = Field(default_factory=list)
    attempted_answer: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# POST /support — request & response (Section 6.1)
# ---------------------------------------------------------------------------
class SupportRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    channel: Optional[str] = "web"
    product_version: Optional[str] = None
    as_of_date: Optional[str] = None  # YYYY-MM-DD; defaults to today in handler


class SupportResponse(BaseModel):
    trace_id: str
    conversation_id: str
    answer_type: AnswerType
    answer: str
    intent: IntentPublic
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[ToolInvocation] = Field(default_factory=list)
    critic: Optional[CriticSignal] = None
    conflicts_detected: list[Conflict] = Field(default_factory=list)
    handoff_id: Optional[str] = None
    handoff: Optional[HandoffBundle] = None  # inline for escalated (Annex D)
    pii_redacted: bool = False
    as_of_date: str = ""


# ---------------------------------------------------------------------------
# POST /ingest — Source Register metadata (Annex B)
# ---------------------------------------------------------------------------
class SourceMeta(BaseModel):
    source_id: str
    doc_type: DocType
    title: str
    authority_level: int = Field(ge=1, le=5)
    product_versions: str = ""
    last_updated: str = ""
    effective_from: str = ""
    deprecated_on: str = ""
    supersedes: str = ""
    provenance: str = ""
    synthetic: str = "Y"


class IngestResult(BaseModel):
    ok: bool
    source_id: str
    chunks_indexed: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    api: bool = True
    sqlite: bool = False
    vector_store: bool = False
    llm: bool = False
    llm_provider: str = "mock"
    details: dict = Field(default_factory=dict)
