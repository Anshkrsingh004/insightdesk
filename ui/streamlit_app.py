"""InsightDesk chat UI (Streamlit). A thin client over POST /support that surfaces the
things judges want to see: the grounded answer, its citations, the tools invoked, the
critic's scores, any source conflicts, and the handoff bundle on escalation.

    streamlit run ui/streamlit_app.py
Set API_URL (default http://localhost:8000) to point at the API.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")

BADGE = {
    "answered": ("✅ Answered", "#1a7f37"),
    "escalated": ("🙋 Escalated to human", "#9a3412"),
    "clarification_needed": ("❓ Needs clarification", "#8250df"),
    "not_found": ("🔍 Not covered", "#6e7781"),
    "refused": ("⛔ Refused", "#cf222e"),
    "out_of_scope": ("🚫 Out of scope", "#6e7781"),
}

st.set_page_config(page_title="InsightDesk — CloudFlow Support", page_icon="🛟", layout="centered")
st.title("🛟 InsightDesk")
st.caption("Self-serve CloudFlow support with safe escalation · Team Overfitting Squad")

# ---- sidebar ----
with st.sidebar:
    st.header("Session")
    account_id = st.text_input("X-Account-Id", value="A1001")
    product_version = st.text_input("product_version (optional)", value="")
    as_of_date = st.text_input("as_of_date", value="2026-10-06")
    st.divider()
    try:
        h = httpx.get(f"{API_URL}/health", timeout=3).json()
        ok = h.get("status") == "ok"
        st.markdown(f"**API:** {'🟢' if ok else '🟠'} {h.get('status')}  ·  **LLM:** `{h.get('llm_provider')}`")
        st.caption(f"sqlite={h.get('sqlite')} · vector={h.get('vector_store')} · llm_ready={h.get('llm')}")
    except Exception as e:
        st.error(f"API not reachable at {API_URL}\n{e}")
    if st.button("🗑️ New conversation"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.caption("Try: *How do I export my run history?* · *Why am I getting 429 errors?* "
               "(A1003) · *Charged twice, get me a manager!* (A1005)")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None


def render_meta(resp: dict):
    label, color = BADGE.get(resp["answer_type"], (resp["answer_type"], "#6e7781"))
    st.markdown(f"<span style='background:{color};color:#fff;padding:2px 8px;border-radius:10px;"
                f"font-size:0.8em'>{label}</span>", unsafe_allow_html=True)

    cits = resp.get("citations") or []
    if cits:
        with st.expander(f"📚 Citations ({len(cits)})", expanded=True):
            for c in cits:
                st.markdown(f"- **[{c['source_id']}]** · {c.get('doc_type','')} · "
                            f"*{c.get('section','')}* · versions {c.get('product_versions','—')} · "
                            f"updated {c.get('last_updated','—')}")

    tools = resp.get("tools_invoked") or []
    if tools:
        with st.expander(f"🔧 Tools invoked ({len(tools)})"):
            for t in tools:
                st.markdown(f"**{t['tool']}**")
                st.json(t.get("output"), expanded=False)

    conflicts = resp.get("conflicts_detected") or []
    if conflicts:
        with st.expander(f"⚔️ Source conflicts ({len(conflicts)}) — documentation wins"):
            for cf in conflicts:
                st.markdown(f"- `{cf.get('loser_source_id')}` ⟶ superseded by "
                            f"**`{cf.get('winner_source_id')}`** ({cf.get('reason')})")

    crit = resp.get("critic")
    if crit:
        with st.expander("🧪 Critic"):
            cols = st.columns(4)
            cols[0].metric("Groundedness", crit.get("groundedness"))
            cols[1].metric("Coverage", crit.get("coverage"))
            cols[2].metric("PII risk", crit.get("pii_risk"))
            cols[3].metric("Policy risk", crit.get("policy_risk"))

    if resp.get("answer_type") == "escalated" and resp.get("handoff"):
        hb = resp["handoff"]
        with st.expander(f"🙋 Handoff bundle · {resp.get('handoff_id')} → {hb.get('queue')}/"
                         f"{hb.get('priority')}", expanded=True):
            st.markdown(f"**Reasons:** {', '.join(hb.get('escalation_reasons', []))}")
            st.markdown(f"**Customer summary:** {hb.get('customer_summary','')}")
            st.markdown(f"**Unresolved:** {', '.join(hb.get('unresolved_questions', []))}")
            st.markdown(f"**PII redacted:** {resp.get('pii_redacted')}")
            st.json(hb.get("evidence"), expanded=False)

    st.caption(f"trace_id `{resp.get('trace_id')}` · intent "
               f"{resp.get('intent',{}).get('type')}/{resp.get('intent',{}).get('sentiment')} · "
               f"GET {API_URL}/audit/{resp.get('trace_id')}")


# replay history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant" and m.get("resp"):
            render_meta(m["resp"])

# input
if prompt := st.chat_input("Ask CloudFlow support…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking (classify → retrieve → tools → critic → decide)…"):
            body = {"message": prompt, "as_of_date": as_of_date or None,
                    "conversation_id": st.session_state.conversation_id}
            if product_version.strip():
                body["product_version"] = product_version.strip()
            try:
                resp = httpx.post(f"{API_URL}/support", headers={"X-Account-Id": account_id},
                                  json=body, timeout=120).json()
            except Exception as e:
                st.error(f"Request failed: {e}")
                st.stop()
        st.session_state.conversation_id = resp.get("conversation_id")
        st.markdown(resp.get("answer", ""))
        render_meta(resp)
    st.session_state.messages.append({"role": "assistant", "content": resp.get("answer", ""),
                                      "resp": resp})
