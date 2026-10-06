"""All Section 6 endpoints. Phase 0: /health is real; the rest return valid-shaped
placeholders that later phases replace with the LangGraph pipeline.
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from typing import Optional

from ..config import get_settings, today_str
from ..db import connection, healthcheck as db_ok
from ..llm import get_llm
from ..graph.build import run_support
from ..retrieval.ingest import add_source
from ..schemas import (
    Citation, HealthStatus, IngestResult, IntentPublic, SourceMeta,
    SupportRequest, SupportResponse,
)

router = APIRouter()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# GET /health — readiness of API, SQLite, vector store, LLM
# ---------------------------------------------------------------------------
@router.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    s = get_settings()
    sqlite_ok = db_ok(s)
    # Vector store readiness = chroma dir usable. Deep check added in Phase 2.
    try:
        vector_ok = s.chroma_abspath.exists()
    except Exception:
        vector_ok = False
    llm = get_llm()
    llm_ok = llm.available()
    overall = "ok" if (sqlite_ok and vector_ok) else "degraded"
    return HealthStatus(
        status=overall,
        api=True,
        sqlite=sqlite_ok,
        vector_store=vector_ok,
        llm=llm_ok,
        llm_provider=s.llm_provider,
        details={"ollama_model": s.ollama_model, "embeddings": s.embeddings},
    )


# ---------------------------------------------------------------------------
# POST /support — placeholder until Phase 2 wires the graph
# ---------------------------------------------------------------------------
@router.post("/support", response_model=SupportResponse)
def support(req: SupportRequest, x_account_id: Optional[str] = Header(default=None)) -> SupportResponse:
    as_of = req.as_of_date or today_str()
    state = run_support(
        message=req.message, account_id=x_account_id, conversation_id=req.conversation_id,
        product_version=req.product_version, as_of_date=as_of, channel=req.channel or "web",
    )
    intent = state.get("intent") or {}
    return SupportResponse(
        trace_id=state["trace_id"],
        conversation_id=state["conversation_id"],
        answer_type=state.get("answer_type", "not_found"),
        answer=state.get("answer", ""),
        intent=IntentPublic(
            type=intent.get("type", "out_of_scope"), urgency=intent.get("urgency", "low"),
            sentiment=intent.get("sentiment", "neutral"),
            pii_detected=intent.get("pii_detected", False),
            confidence=intent.get("confidence", 0.0),
        ),
        citations=[Citation(**c) for c in state.get("citations", [])],
        tools_invoked=state.get("tools_invoked", []),
        critic=state.get("critic"),
        conflicts_detected=state.get("conflicts", []),
        handoff_id=state.get("handoff_id"),
        handoff=state.get("handoff"),
        pii_redacted=state.get("pii_redacted", False),
        as_of_date=as_of,
    )


# ---------------------------------------------------------------------------
# POST /ingest — add an article or ticket while running (R12). Multipart:
#   metadata : JSON string with Annex B Source Register fields
#   content  : markdown article OR JSON ticket (form field), or uploaded `file`
# Indexed immediately and searchable on the next /support call.
# ---------------------------------------------------------------------------
@router.post("/ingest", response_model=IngestResult)
async def ingest(
    metadata: str = Form(...),
    content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
) -> IngestResult:
    try:
        meta = json.loads(metadata)
    except Exception:
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    body = content
    if file is not None:
        body = (await file.read()).decode("utf-8")
    if not body:
        raise HTTPException(status_code=400, detail="provide `content` form field or a `file`")
    try:
        sm = SourceMeta(**meta)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid Source Register metadata: {e}")
    n = add_source(sm.model_dump(), body)
    return IngestResult(ok=True, source_id=sm.source_id, chunks_indexed=n,
                        message="indexed and searchable immediately")


# ---------------------------------------------------------------------------
# GET /conversations/{id}
# ---------------------------------------------------------------------------
@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    with connection() as conn:
        rows = conn.execute(
            "SELECT role, content, answer_type, route_json, trace_id, created_at "
            "FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)
        ).fetchall()
    msgs = [dict(r) for r in rows]
    for m in msgs:
        if m.get("route_json"):
            try:
                m["route"] = json.loads(m.pop("route_json"))
            except Exception:
                pass
    return {"conversation_id": conversation_id, "messages": msgs}


# ---------------------------------------------------------------------------
# GET /handoffs/{id}
# ---------------------------------------------------------------------------
@router.get("/handoffs/{handoff_id}")
def get_handoff(handoff_id: str) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT * FROM handoffs WHERE handoff_id=?", (handoff_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="handoff not found")
    d = dict(row)
    if d.get("bundle_json"):
        d["bundle"] = json.loads(d.pop("bundle_json"))
    return d


# ---------------------------------------------------------------------------
# GET /audit/{trace_id}
# ---------------------------------------------------------------------------
@router.get("/audit/{trace_id}")
def get_audit(trace_id: str) -> dict:
    with connection() as conn:
        row = conn.execute("SELECT record_json FROM audit_records WHERE trace_id=?", (trace_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="audit record not found")
    return json.loads(row["record_json"])


# ---------------------------------------------------------------------------
# GET /sources — Source Register (Annex B)
# ---------------------------------------------------------------------------
@router.get("/sources")
def get_sources() -> dict:
    with connection() as conn:
        rows = conn.execute(
            "SELECT source_id, doc_type, title, authority_level, product_versions, "
            "last_updated, effective_from, deprecated_on, supersedes, provenance, synthetic "
            "FROM sources ORDER BY source_id"
        ).fetchall()
    return {"count": len(rows), "sources": [dict(r) for r in rows]}
