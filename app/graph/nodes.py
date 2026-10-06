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
from ..schemas import Citation, CriticSignal, IntentSignal
from ..core import precedence as prec
from ..core import escalation as esc
from ..core import pii
from ..data import tools as T
from ..data import policy
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
- Never promise a refund, credit or account change — those are approved by a human.
- Be concise and specific (steps, error codes, exact limits). Do not reveal secrets."""

CRITIC_SYSTEM = """You are a strict reviewer of a draft support answer. Given the draft
and the sources it must be based on, return JSON:
  groundedness: number 0..1 (fraction of the draft that is directly supported by the sources)
  coverage: complete | partial | none
  decision: answer | revise | escalate
Judge ONLY grounding and coverage. Do not consider PII or policy here."""

# Unapproved-action promises that must NEVER reach the customer. This is the code
# backstop that catches a refund/credit/account-change promise even if a weak model is
# tricked into drafting one (prompt injection) — policy_risk=high -> escalate, so the
# promise is replaced by the calm escalation message. Tuned to avoid matching safe policy
# explanations like "refunds are approved by billing".
_PROMISE = re.compile(
    r"(\brefunded\b.{0,25}\byour\s+(card|account)\b"
    r"|\brefund(ed)?\b.{0,20}\b(has been|was|is|now)\s+(approved|processed|issued)\b"
    r"|\bapproved\b[:\s].{0,20}\$?\d[\d,. ]*\s*refund"
    r"|\$\s?\d[\d,.]*\s*(has been |was )?(refunded|credited)\b"
    r"|\bi(?:['’]ve| have| will| ll| can| can now| am going to)?\s+(refund|credit|cancel|cancelled|"
    r"upgrade|downgrade|reset)\s+(you|your)\b"
    r"|\byour account (has been|is|will be) (cancelled|canceled|upgraded|downgraded|credited|closed|deleted)\b)",
    re.IGNORECASE,
)


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
    elif has("429", "rate limit", "usage", "plan limit", "run limit", "how close",
             "my limit", "approaching", "how many runs", "seats", "quota"):
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


def _normalize_intent(intent: dict, msg: str) -> dict:
    """Deterministic floor over the LLM's classification for safety-critical signals, so
    refund/billing/security never get misrouted and escalation (Phase 4) sees the right
    intent. Code refines the model signal; it does not trust it blindly."""
    t = msg.lower()

    def has(*ws):
        return any(w in t for w in ws)

    if has("forgot my password", "forgot password", "reset my password", "reset link",
           "password reset", "can't log in", "cannot log in", "locked out",
           "account hacked", "compromised"):
        intent["type"] = "security"
    elif has("refund", "charged twice", "double charged", "duplicate charge", "charge me",
             "chargeback", "billing dispute", "money back"):
        intent["type"] = "complaint" if has("manager", "unacceptable", "third time",
                                             "furious", "ridiculous", "fed up") else "billing"
    # Own this signal deterministically — the small model over-reports it. Keyword
    # present => True, absent => False (override the LLM either way).
    intent["explicit_human_request"] = has(
        "manager", "speak to a human", "speak to someone", "real person",
        "talk to someone", "talk to a person", "get me a human", "human agent",
        "live agent", "speak with a human")
    if has("unacceptable", "ridiculous", "furious", "third time", "fed up", "get me a manager"):
        intent["sentiment"] = "angry"
    return intent


def classify(state: dict) -> dict:
    llm = get_llm()
    sig = llm.structured(
        system=CLASSIFY_SYSTEM, user=state.get("message", ""),
        schema=IntentSignal, mock=lambda: _heuristic_intent(state.get("message", "")),
    )
    intent = _normalize_intent(sig.model_dump(), state.get("message", ""))
    return {"intent": intent, "route": state.get("route", []) + ["classify"]}


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

    # Relevance gate (R2): if even the best authoritative chunk is too dissimilar, the KB
    # doesn't cover this -> drop grounding so compose returns not_found (never invent).
    authoritative = pr.authoritative[: s.top_k]
    if authoritative:
        best = min((c.get("distance") if c.get("distance") is not None else 9e9)
                   for c in authoritative)
        if best > s.relevance_max_distance:
            authoritative = []

    precedence_dict = {
        "authoritative": [{"source_id": c["metadata"].get("source_id"),
                           "section": c["metadata"].get("section"),
                           "doc_type": c["metadata"].get("doc_type"),
                           "authority_level": c["metadata"].get("authority_level"),
                           "product_versions": c["metadata"].get("product_versions"),
                           "last_updated": c["metadata"].get("last_updated"),
                           "distance": c.get("distance"),
                           "text": c["text"]} for c in authoritative],
        "supporting": [{"source_id": c["metadata"].get("source_id"),
                        "outdated": c["metadata"].get("outdated")} for c in pr.supporting],
        "conflicts": pr.conflicts,
        "upcoming_deprecations": pr.upcoming_deprecations,
        "dropped": pr.dropped,
    }
    return {"candidates": hits, "precedence": precedence_dict,
            "conflicts": pr.conflicts, "route": state.get("route", []) + ["retrieve"]}


# ---------------------------------------------------------------------------
# tools (LLM picks via tools_needed; code executes deterministically) — R7
# ---------------------------------------------------------------------------
INTENT_TOOLS = {
    "account": ["lookup_account", "get_usage", "get_plan_limits"],
    "billing": ["lookup_account", "get_invoices", "check_refund_eligibility"],
    "complaint": ["lookup_account", "get_invoices", "check_refund_eligibility"],
    "security": ["lookup_account", "send_password_reset"],
    "troubleshooting": [],
    "how_to": [],
}


def _augment_tools(needed: list[str], msg: str) -> list[str]:
    """Code-guaranteed tool selection: ensure the right tools run from message content,
    regardless of the LLM's tools_needed (R7 — account facts never come from LLM text)."""
    t = msg.lower()

    def has(*ws):
        return any(w in t for w in ws)

    def add(*ts):
        for x in ts:
            if x not in needed:
                needed.append(x)

    if has("429", "rate limit", "usage", "plan limit", "run limit", "how many runs",
           "quota", "seats", "over my limit", "exceed", "how close"):
        add("lookup_account", "get_usage", "get_plan_limits")
    if has("refund", "charged", "charge", "invoice", "billing", "duplicate", "money back",
           "chargeback", "past due", "past_due", "payment"):
        add("lookup_account", "get_invoices", "check_refund_eligibility")
    if has("forgot my password", "forgot password", "reset my password", "reset link",
           "password reset", "can't log in", "cannot log in", "locked out"):
        add("lookup_account", "send_password_reset")
    if has("status", "outage", "down", "degraded", "cf-503"):
        add("check_platform_status")
    return needed


def run_tools(state: dict) -> dict:
    aid = state.get("account_id")
    intent = state.get("intent") or {}
    itype = intent.get("type", "")
    needed = list(intent.get("tools_needed") or INTENT_TOOLS.get(itype, []))
    needed = _augment_tools(needed, state.get("message", ""))

    invoked: list[dict] = []
    if aid:
        for name in needed:
            fn = T.TOOLS.get(name)
            if not fn:
                continue
            try:
                out = fn(aid, as_of=state.get("as_of_date"))
                invoked.append({"tool": name, "output": out})
            except Exception as e:  # a required tool failed -> recorded; escalation may trigger (Phase 4)
                invoked.append({"tool": name, "output": {"error": str(e)}, "failed": True})
    return {"tools_invoked": invoked, "route": state.get("route", []) + ["tools"]}


def _tool_summary(tools_invoked: list[dict]) -> str:
    lines: list[str] = []
    for ti in tools_invoked:
        name, out = ti.get("tool"), ti.get("output")
        if not out or ti.get("failed"):
            continue
        if name == "lookup_account":
            lines.append(f"Account {out.get('account_id')} is on the {out.get('plan')} plan "
                         f"(status {out.get('status')}, CloudFlow {out.get('product_version')}).")
        elif name == "get_usage" and out.get("limits"):
            u = out["usage"][0] if out.get("usage") else {}
            lim, fl = out["limits"], out.get("flags", {})
            lines.append(f"This period: {u.get('workflow_runs')} runs (limit {lim.get('monthly_workflow_runs')}), "
                         f"peak {u.get('api_calls_peak_per_min')} API req/min (limit {lim.get('api_rate_limit_per_min')}).")
            if fl.get("rate_over_limit"):
                lines.append("You are OVER the per-minute API limit — that is why you see 429 errors.")
            elif fl.get("runs_over_limit"):
                lines.append("You are OVER your monthly workflow-run limit.")
            elif fl.get("runs_at_or_over_limit"):
                lines.append("You are exactly AT your monthly workflow-run limit.")
        elif name == "get_invoices" and out:
            lines.append("Recent invoices: " + "; ".join(
                f"{i['invoice_id']} {i['currency']} {i['amount']} on {i['charged_on']} ({i['status']})"
                for i in out[:3]) + ".")
        elif name == "check_refund_eligibility" and out.get("invoices"):
            i = out["invoices"][0]
            lines.append(f"Invoice {i['invoice_id']} ({i['currency']} {i['amount']} on {i['charged_on']}) was "
                         f"{i['days_since_charge']} days ago; within the {out['refund_window_days']}-day refund "
                         f"window = {i['within_window']}. Refunds are approved and issued by billing, not by me.")
        elif name == "check_platform_status" and out:
            bad = [c for c in out if c.get("status") != "operational"]
            lines.append(("Platform status: " + ", ".join(f"{c['component']}={c['status']}" for c in bad) + ".")
                         if bad else "All platform components are operational.")
        elif name == "send_password_reset" and out.get("sent"):
            lines.append("I've triggered a password-reset link to the account owner's email. "
                         "For security I can't show the link or token here.")
    return " ".join(lines)


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


def _tool_citations(tools_invoked: list[dict]) -> list[dict]:
    cites = []
    for ti in tools_invoked:
        pc = (ti.get("output") or {}).get("policy_citation") if isinstance(ti.get("output"), dict) else None
        if pc and pc.get("source_id"):
            cites.append(Citation(source_id=pc["source_id"], doc_type="policy",
                                  section=pc.get("source_section", "")).model_dump())
    return cites


def compose(state: dict) -> dict:
    pr = state.get("precedence", {})
    auth = pr.get("authoritative", [])
    upcoming = pr.get("upcoming_deprecations", [])
    tools_invoked = state.get("tools_invoked", [])
    tool_text = _tool_summary(tools_invoked)

    # merge doc citations + tool/policy citations (dedup by source_id)
    citations = _citations_from(auth)
    seen = {c["source_id"] for c in citations}
    for tc in _tool_citations(tools_invoked):
        if tc["source_id"] not in seen:
            citations.append(tc); seen.add(tc["source_id"])

    if not auth and not tool_text:
        return {"answer": ("I couldn't find this in the CloudFlow knowledge base. I can hand this "
                           "off to a human who can help — would you like that?"),
                "answer_type": "not_found", "citations": [],
                "route": state.get("route", []) + ["compose"]}

    llm = get_llm()
    if llm.provider == "mock":
        doc = _extractive_answer(state.get("message", ""), auth, upcoming) if auth else ""
        answer = (f"{tool_text}\n\n{doc}" if tool_text and doc else (tool_text or doc)).strip()
    else:
        context = "\n\n".join(
            f"[{a['source_id']}] ({a.get('section','')}, versions {a.get('product_versions','')}, "
            f"updated {a.get('last_updated','')}):\n{a['text']}" for a in auth)
        if upcoming:
            context += "\n\nUPCOMING DEPRECATIONS: " + "; ".join(
                f"{u['source_id']} {u.get('title','')} removed {u.get('deprecated_on','')}" for u in upcoming)
        if tool_text:
            context += f"\n\nTOOL RESULTS (authoritative for current account state):\n{tool_text}"
        user = f"Customer question:\n{state.get('message','')}\n\nSources:\n{context}"
        if state.get("revise_feedback"):
            user += f"\n\nREVISION NOTE: {state['revise_feedback']}"
        fallback = (f"{tool_text}\n\n{_extractive_answer(state.get('message',''), auth, upcoming)}"
                    if auth else tool_text).strip()
        answer = llm.complete(system=COMPOSE_SYSTEM, user=user).strip() or fallback

    return {"answer": answer, "answer_type": "answered", "citations": citations,
            "route": state.get("route", []) + ["compose"]}


# ---------------------------------------------------------------------------
# critic (LLM scores groundedness/coverage; code owns pii_risk & policy_risk) — R4
# ---------------------------------------------------------------------------
def _word_overlap(answer: str, sources: str) -> float:
    aw = set(re.findall(r"[a-z0-9]{4,}", answer.lower()))
    sw = set(re.findall(r"[a-z0-9]{4,}", sources.lower()))
    return (len(aw & sw) / len(aw)) if aw else 0.0


def _policy_risk(answer: str) -> str:
    """High if the draft promises an unapproved action (refund/credit/account change)."""
    return "high" if _PROMISE.search(answer or "") else "none"


def critic(state: dict) -> dict:
    answer = state.get("answer", "")
    atype = state.get("answer_type", "")
    pr = state.get("precedence", {})
    sources = " ".join(a.get("text", "") for a in pr.get("authoritative", []))
    sources += " " + _tool_summary(state.get("tools_invoked", []))

    def mock():
        if atype == "not_found" or not answer:
            return {"groundedness": 0.25, "coverage": "none", "decision": "escalate"}
        overlap = round(_word_overlap(answer, sources), 2)
        grounded = max(0.72, overlap) if state.get("citations") else overlap
        return {"groundedness": grounded,
                "coverage": "complete" if len(answer) > 120 else "partial",
                "decision": "answer" if grounded >= 0.6 else "revise"}

    llm = get_llm()
    if llm.provider == "mock" or not get_settings().critic_llm:
        sig = CriticSignal.model_validate(mock())  # fast deterministic groundedness
    else:
        sig = llm.structured(system=CRITIC_SYSTEM,
                             user=f"Draft answer:\n{answer}\n\nSources:\n{sources[:3000]}",
                             schema=CriticSignal, mock=mock)
    data = sig.model_dump()
    # Safety signals are ALWAYS code-computed, never trusted to the model.
    data["pii_risk"] = pii.risk(answer)
    data["policy_risk"] = _policy_risk(answer)
    data["revisions"] = state.get("revisions", 0)
    return {"critic": data, "route": state.get("route", []) + ["critic"]}


# ---------------------------------------------------------------------------
# revise (code) — re-enter compose once with the critic's feedback
# ---------------------------------------------------------------------------
def revise(state: dict) -> dict:
    crit = state.get("critic") or {}
    fb = (f"Your previous draft scored low on grounding (groundedness "
          f"{crit.get('groundedness')}). Rewrite using ONLY the sources, cite them, and "
          f"do not add unsupported claims.")
    return {"revisions": state.get("revisions", 0) + 1, "revise_feedback": fb,
            "route": state.get("route", []) + ["revise"]}


# ---------------------------------------------------------------------------
# escalation (code) — Annex A.3 decision + handoff bundle (Annex D)
# ---------------------------------------------------------------------------
_SLA_TEXT = {"billing": "one business day", "security": "4 hours",
             "technical": "one business day", "general": "one business day"}


def _unresolved_questions(reasons: list[str], tools_invoked: list[dict]) -> list[str]:
    qs = []
    if {"refund_or_credit", "billing_dispute"} & set(reasons):
        inv = None
        for t in tools_invoked:
            if t["tool"] == "get_invoices" and t.get("output"):
                inv = t["output"][0]["invoice_id"] if t["output"] else None
        qs.append(f"Approve refund of {inv}?" if inv else "Approve refund for the disputed charge?")
    if "account_deletion" in reasons:
        qs.append("Confirm identity and proceed with account deletion?")
    if "security_incident" in reasons:
        qs.append("Verify identity and secure the account?")
    if not qs:
        qs.append("Review and respond to the customer.")
    return qs


def escalate(state: dict) -> dict:
    intent = state.get("intent") or {}
    crit = state.get("critic") or {}
    tools_invoked = state.get("tools_invoked", [])
    reasons = state.get("esc_reasons", [])
    queue = state.get("esc_queue", "general")
    priority = state.get("esc_priority", "normal")

    # Evidence = tool outputs + cited sources (PII-redacted)
    evidence = [{"tool": t["tool"], "output": t.get("output")} for t in tools_invoked]
    for c in state.get("citations", []):
        evidence.append({"source_id": c["source_id"], "section": c.get("section", "")})

    bundle = {
        "queue": queue, "priority": priority,
        "intent": intent.get("type", ""), "urgency": intent.get("urgency", ""),
        "sentiment": intent.get("sentiment", ""),
        "escalation_reasons": reasons,
        "customer_summary": _customer_summary(state),
        "evidence": pii.redact_obj(evidence),
        "attempted_answer": pii.redact(state.get("answer", "")),
        "unresolved_questions": _unresolved_questions(reasons, tools_invoked),
    }
    created = T.create_handoff(state.get("conversation_id"), state.get("account_id"),
                              queue, priority, bundle)
    hid = created["handoff_id"]

    cannot = ("issue refunds or credits" if queue == "billing"
              else "make account or security changes" if queue == "security"
              else "resolve this myself")
    msg = (f"I'm sorry about this, and I understand the frustration. I've passed your case to "
           f"our {queue} team with all the details, and you'll hear back within "
           f"{_SLA_TEXT.get(queue, 'one business day')}. I can't {cannot} — a human will take it "
           f"from here (reference {hid}).")

    return {"answer_type": "escalated", "answer": msg, "handoff_id": hid,
            "handoff": bundle, "pii_redacted": True,
            "route": state.get("route", []) + ["escalate"]}


def _customer_summary(state: dict) -> str:
    msg = pii.redact(state.get("message", ""))
    return (msg[:200] + "…") if len(msg) > 200 else msg


# ---------------------------------------------------------------------------
# decide (code) — run the Escalation Policy Engine; set final answer_type
# ---------------------------------------------------------------------------
def decide(state: dict) -> dict:
    intent = state.get("intent") or {}
    crit = state.get("critic") or {}
    # Grounded if compose produced an answer from docs OR tools; "not covered" only when
    # compose itself returned not_found.
    has_grounding = state.get("answer_type") != "not_found"
    threshold, _cite = policy.get_critic_threshold()

    decision = esc.decide(
        intent=intent, critic=crit, tools_invoked=state.get("tools_invoked", []),
        has_grounding=has_grounding, message=state.get("message", ""),
        threshold=threshold, revisions=state.get("revisions", 0),
    )
    return {"esc_decision": decision.escalate, "esc_reasons": decision.reasons,
            "esc_queue": decision.queue, "esc_priority": decision.priority,
            "route": state.get("route", []) + ["decide"]}


# ---------------------------------------------------------------------------
# clarify (code) -> clarification_needed
# ---------------------------------------------------------------------------
def clarify(state: dict) -> dict:
    return {"answer_type": "clarification_needed",
            "answer": ("I want to get this right — could you tell me a bit more? For example, "
                       "which CloudFlow feature or step is affected, and any error code you see "
                       "(like CF-503 or a 429)?"),
            "citations": [], "route": state.get("route", []) + ["clarify"]}


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

    # --- Global PII/secret redaction (R9): responses, bundles AND logs carry none ---
    raw_answer = state.get("answer", "")
    raw_msg = state.get("message", "")
    red_answer = pii.redact(raw_answer)
    red_tools = pii.redact_obj(state.get("tools_invoked", []))
    red_msg = pii.redact(raw_msg)
    pii_flag = (bool(state.get("pii_redacted")) or red_answer != raw_answer
                or bool(pii.detect(raw_msg)))

    route = state.get("route", []) + ["finalize"]
    audit = pii.redact_obj({
        "trace_id": state.get("trace_id"),
        "conversation_id": state.get("conversation_id"),
        "account_id": state.get("account_id"),
        "as_of_date": state.get("as_of_date"),
        "intent": state.get("intent"),
        "route": route,
        "sources_retrieved": [c["metadata"].get("source_id") for c in state.get("candidates", [])],
        "precedence": state.get("precedence"),
        "tools_invoked": red_tools,
        "critic": state.get("critic"),
        "answer_type": state.get("answer_type"),
        "conflicts_detected": state.get("conflicts", []),
        "escalation_reasons": state.get("esc_reasons", []),
        "handoff_id": state.get("handoff_id"),
        "pii_redacted": pii_flag,
        "model": s.ollama_model if llm.provider == "ollama" else llm.provider,
        "llm_provider": llm.provider,
        "latency_ms": latency_ms,
        "llm_calls": llm_calls,
        "tokens": llm.last_tokens,
    })
    with connection() as conn:
        conn.execute("INSERT OR IGNORE INTO conversations (conversation_id, account_id, created_at) "
                     "VALUES (?,?,datetime('now'))",
                     (state.get("conversation_id"), state.get("account_id")))
        conn.execute("INSERT INTO messages (conversation_id, role, content, created_at) "
                     "VALUES (?,?,?,datetime('now'))",
                     (state.get("conversation_id"), "customer", red_msg))  # redacted in logs
        conn.execute("INSERT INTO messages (conversation_id, role, content, answer_type, route_json, "
                     "trace_id, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
                     (state.get("conversation_id"), "assistant", red_answer,
                      state.get("answer_type"), json.dumps(route), state.get("trace_id")))
        conn.execute("INSERT OR REPLACE INTO audit_records (trace_id, conversation_id, account_id, "
                     "created_at, record_json) VALUES (?,?,?,datetime('now'),?)",
                     (state.get("trace_id"), state.get("conversation_id"),
                      state.get("account_id"), json.dumps(audit)))
    return {"answer": red_answer, "tools_invoked": red_tools, "pii_redacted": pii_flag,
            "route": route}
