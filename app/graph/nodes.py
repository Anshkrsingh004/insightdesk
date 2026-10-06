"""LangGraph nodes. Each is a pure-ish function: read state, do one job, return the keys
it changed. LLM nodes return VALIDATED structured signals; policy/precedence/routing is
code. (Tools, critic and escalation nodes are added in Phases 3-4.)
"""
from __future__ import annotations

import json
import re
import time

from ..config import get_settings
from ..db import connection
from ..llm import get_llm
from ..schemas import Citation, IntentSignal
from ..core import precedence as prec
from ..retrieval import vectorstore as vs

ACCOUNT_RE = re.compile(r"\bA\d{4}\b")

CLASSIFY_SYSTEM = """You are an intent classifier for CloudFlow customer support.
Classify the customer message only; do NOT answer it. Return a JSON object with:
  type: one of how_to, troubleshooting, account, billing, complaint, security, out_of_scope
  urgency: one of low, medium, high
  sentiment: one of positive, neutral, negative, frustrated, angry
  pii_detected: boolean (true if the message contains an email, phone, card number or API key)
  tools_needed: array from [lookup_account, get_plan_limits, get_usage, get_invoices,
                check_refund_eligibility, check_platform_status, send_password_reset]
  confidence: number 0..1
  explicit_human_request: boolean (true if they ask for a human/agent/manager)"""

COMPOSE_SYSTEM = """You are the CloudFlow support assistant. Answer the customer's
question USING ONLY the provided sources and tool results. Rules:
- Ground every claim in a source; do not use outside knowledge.
- Cite sources inline using their source_id in square brackets, e.g. [KB-API-RATE-001].
- If an upcoming deprecation is provided, mention it and its date.
- Prefer current documentation over older resolved tickets.
- If the sources do not cover the question, say you don't know rather than inventing.
- Be concise and specific (steps, error codes, exact limits). Do not reveal secrets."""


# ---------------------------------------------------------------------------
# authorize (code) — account comes ONLY from X-Account-Id (R8)
# ---------------------------------------------------------------------------
def authorize(state: dict) -> dict:
    aid = state.get("account_id")
    account = None
    if aid:
        with connection() as conn:
            r = conn.execute("SELECT * FROM accounts WHERE account_id=?", (aid,)).fetchone()
            account = dict(r) if r else None
    # cross-account attempt: message names a DIFFERENT account id (R8 refuse)
    cross = False
    for m in ACCOUNT_RE.findall(state.get("message", "")):
        if aid and m != aid:
            cross = True
    return {"account": account, "cross_account": cross,
            "route": state.get("route", []) + ["authorize"]}


# ---------------------------------------------------------------------------
# classify (LLM structured signal; heuristic in mock mode)
# ---------------------------------------------------------------------------
def _heuristic_intent(msg: str) -> dict:
    t = msg.lower()
    pii = bool(re.search(r"[\w.+-]+@[\w-]+\.\w+|\b\d{12,19}\b|\bsk-[A-Za-z0-9]{8,}\b"
                         r"|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", msg))
    human = any(w in t for w in ["manager", "human", "agent", "speak to someone", "real person"])
    angry = any(w in t for w in ["unacceptable", "ridiculous", "furious", "angry", "third time",
                                 "get me a manager", "fed up", "terrible", "worst"])
    neg = angry or any(w in t for w in ["not working", "still broken", "no reply", "frustrat"])

    def has(*ws):
        return any(w in t for w in ws)

    if has("refund", "charged twice", "double charged", "duplicate charge", "invoice", "billing", "money back"):
        itype, tools = "billing", ["lookup_account", "get_invoices", "check_refund_eligibility"]
    elif has("password", "reset link", "forgot my password", "api key", "token", "security", "hacked"):
        itype, tools = "security", ["lookup_account", "send_password_reset"]
    elif has("429", "rate limit", "usage", "plan limit", "how many runs", "seats"):
        itype, tools = "account", ["lookup_account", "get_usage", "get_plan_limits"]
    elif has("cf-503", "cf-401", "cf-422", "cf-500", "error", "failing", "fails", "not working", "broken"):
        itype, tools = "troubleshooting", []
    elif has("how do i", "how to", "export", "schedule", "set up", "create", "add a", "invite"):
        itype, tools = "how_to", []
    elif has("refund me", "charged") and angry:
        itype, tools = "complaint", ["lookup_account", "get_invoices"]
    elif has("poem", "weather", "sap ariba", "stock price", "joke"):
        itype, tools = "out_of_scope", []
    else:
        itype, tools = "troubleshooting", []
    if angry and has("refund", "charged", "billing", "manager"):
        itype = "complaint"
    sentiment = "angry" if angry else ("negative" if neg else "neutral")
    urgency = "high" if (angry or human) else ("medium" if neg else "low")
    conf = 0.9 if itype != "out_of_scope" else 0.8
    return {"type": itype, "urgency": urgency, "sentiment": sentiment,
            "pii_detected": pii, "tools_needed": tools, "confidence": conf,
            "explicit_human_request": human}


def classify(state: dict) -> dict:
    llm = get_llm()
    sig = llm.structured(
        system=CLASSIFY_SYSTEM, user=state.get("message", ""),
        schema=IntentSignal, mock=lambda: _heuristic_intent(state.get("message", "")),
    )
    return {"intent": sig.model_dump(), "route": state.get("route", []) + ["classify"]}


# ---------------------------------------------------------------------------
# retrieve (code: Chroma + Source Precedence Engine)
# ---------------------------------------------------------------------------
def retrieve(state: dict) -> dict:
    s = get_settings()
    account = state.get("account") or {}
    customer_version = state.get("product_version") or account.get("product_version")
    as_of = state.get("as_of_date")

    # Retrieve wide so outdated tickets surface for conflict detection; authoritative
    # citations are still capped at top_k below.
    hits = vs.query(state.get("message", ""), n_results=max(12, s.top_k * 3))
    pr = prec.apply_precedence(hits, customer_version, as_of)

    precedence_dict = {
        "authoritative": [{"source_id": c["metadata"].get("source_id"),
                           "section": c["metadata"].get("section"),
                           "doc_type": c["metadata"].get("doc_type"),
                           "authority_level": c["metadata"].get("authority_level"),
                           "product_versions": c["metadata"].get("product_versions"),
                           "last_updated": c["metadata"].get("last_updated"),
                           "distance": c.get("distance"),
                           "text": c["text"]} for c in pr.authoritative[: s.top_k]],
        "supporting": [{"source_id": c["metadata"].get("source_id"),
                        "outdated": c["metadata"].get("outdated")} for c in pr.supporting],
        "conflicts": pr.conflicts,
        "upcoming_deprecations": pr.upcoming_deprecations,
        "dropped": pr.dropped,
    }
    return {"candidates": hits, "precedence": precedence_dict,
            "conflicts": pr.conflicts, "route": state.get("route", []) + ["retrieve"]}


# ---------------------------------------------------------------------------
# compose (LLM abstractive; extractive in mock mode) -> answered / not_found
# ---------------------------------------------------------------------------
def _citations_from(auth: list[dict]) -> list[dict]:
    cites = []
    for a in auth:
        cites.append(Citation(
            source_id=a.get("source_id", ""), doc_type=a.get("doc_type", "article"),
            section=a.get("section", ""), product_versions=a.get("product_versions", ""),
            last_updated=a.get("last_updated", ""),
        ).model_dump())
    return cites


def _extractive_answer(question: str, auth: list[dict], upcoming: list[dict]) -> str:
    # Mock mode: ground on the most RELEVANT authoritative chunk (lowest distance),
    # skipping boilerplate link sections. (The LLM path uses all chunks as context.)
    content = [a for a in auth if (a.get("section") or "").lower() not in ("related",)]
    pool = content or auth
    top = min(pool, key=lambda a: a.get("distance") if a.get("distance") is not None else 9e9)
    text = top["text"].strip()
    if len(text) > 700:
        text = text[:700].rsplit(".", 1)[0] + "."
    out = f"{text}\n\n(Source: [{top['source_id']}] — {top.get('section','')})"
    if upcoming:
        u = upcoming[0]
        out += (f"\n\nNote: {u.get('title','')} — the legacy guidance is deprecated and "
                f"will be removed on {u.get('deprecated_on','')} ([{u['source_id']}]).")
    return out


def compose(state: dict) -> dict:
    pr = state.get("precedence", {})
    auth = pr.get("authoritative", [])
    upcoming = pr.get("upcoming_deprecations", [])

    if not auth:
        return {
            "answer": ("I couldn't find this in the CloudFlow knowledge base. I can hand this "
                       "off to a human who can help — would you like that?"),
            "answer_type": "not_found", "citations": [],
            "route": state.get("route", []) + ["compose"],
        }

    citations = _citations_from(auth)
    llm = get_llm()
    if llm.provider == "mock":
        answer = _extractive_answer(state.get("message", ""), auth, upcoming)
    else:
        context = "\n\n".join(
            f"[{a['source_id']}] ({a.get('section','')}, versions {a.get('product_versions','')}, "
            f"updated {a.get('last_updated','')}):\n{a['text']}" for a in auth
        )
        if upcoming:
            context += "\n\nUPCOMING DEPRECATIONS: " + "; ".join(
                f"{u['source_id']} {u.get('title','')} removed {u.get('deprecated_on','')}" for u in upcoming)
        user = f"Customer question:\n{state.get('message','')}\n\nSources:\n{context}"
        answer = llm.complete(system=COMPOSE_SYSTEM, user=user).strip() or \
            _extractive_answer(state.get("message", ""), auth, upcoming)

    return {"answer": answer, "answer_type": "answered", "citations": citations,
            "route": state.get("route", []) + ["compose"]}


# ---------------------------------------------------------------------------
# decline (code) -> out_of_scope / refused (no retrieval)
# ---------------------------------------------------------------------------
def decline(state: dict) -> dict:
    if state.get("cross_account"):
        return {"answer": ("For your security I can only help with the account you're signed in "
                           "to. I can't access another account's data."),
                "answer_type": "refused", "citations": [],
                "route": state.get("route", []) + ["decline"]}
    return {"answer": ("That's outside what CloudFlow support can help with. If it's actually about "
                       "CloudFlow, tell me more and I'll try; otherwise I can hand you to a human."),
            "answer_type": "out_of_scope", "citations": [],
            "route": state.get("route", []) + ["decline"]}


# ---------------------------------------------------------------------------
# finalize (code) — persist conversation + audit record (R11)
# ---------------------------------------------------------------------------
def finalize(state: dict) -> dict:
    s = get_settings()
    llm = get_llm()
    latency_ms = int((time.time() - state.get("t_start", time.time())) * 1000)
    llm_calls = llm.calls - state.get("llm_calls_start", 0)

    audit = {
        "trace_id": state.get("trace_id"),
        "conversation_id": state.get("conversation_id"),
        "account_id": state.get("account_id"),
        "as_of_date": state.get("as_of_date"),
        "intent": state.get("intent"),
        "route": state.get("route", []) + ["finalize"],
        "sources_retrieved": [c["metadata"].get("source_id") for c in state.get("candidates", [])],
        "precedence": state.get("precedence"),
        "tools_invoked": state.get("tools_invoked", []),
        "critic": state.get("critic"),
        "answer_type": state.get("answer_type"),
        "conflicts_detected": state.get("conflicts", []),
        "handoff_id": state.get("handoff_id"),
        "model": s.ollama_model if llm.provider == "ollama" else llm.provider,
        "llm_provider": llm.provider,
        "latency_ms": latency_ms,
        "llm_calls": llm_calls,
        "tokens": llm.last_tokens,
    }
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO conversations (conversation_id, account_id, created_at) "
                     "VALUES (?,?,datetime('now'))",
                     (state.get("conversation_id"), state.get("account_id")))
        conn.execute("INSERT INTO messages (conversation_id, role, content, created_at) "
                     "VALUES (?,?,?,datetime('now'))",
                     (state.get("conversation_id"), "customer", state.get("message", "")))
        conn.execute("INSERT INTO messages (conversation_id, role, content, answer_type, route_json, "
                     "trace_id, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
                     (state.get("conversation_id"), "assistant", state.get("answer", ""),
                      state.get("answer_type"), json.dumps(audit["route"]), state.get("trace_id")))
        conn.execute("INSERT OR REPLACE INTO audit_records (trace_id, conversation_id, account_id, "
                     "created_at, record_json) VALUES (?,?,?,datetime('now'),?)",
                     (state.get("trace_id"), state.get("conversation_id"),
                      state.get("account_id"), json.dumps(audit)))
    return {"route": audit["route"]}
