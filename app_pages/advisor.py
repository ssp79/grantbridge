"""AI Grant Advisor — a grant coach that looks everything up with real tools and says where each fact came from.

The conversation is the main view. The agent's steps, tokens, and cost sit in a collapsed "Technical details"
section at the bottom: there for evidence and debugging, out of the way for everyday use.
"""

import os

import streamlit as st

from grantbridge import advisor, llm, repo, session, trace, ui
from grantbridge import components as c
from grantbridge import validation as v
from grantbridge.config import ConfigError, resolve_settings

EXAMPLES = [
    "Which sample grants fit us best?",
    "What does the Connecticut After-School Learning Grant require?",
    "What is missing from my profile?",
    "How far along are my applications?",
]
SOURCE_TAGS = {"organization profile": ("your profile", "blue"), "grant record": ("grant record", "green"),
               "application record": ("your application", "violet"), "user message": ("your message", "gray")}

user = session.require_user()
org = repo.get_organization(user.id) or {}

c.header("AI Grant Advisor", ":material/forum:",
         f"Hi! I'm your grant advisor for **{ui.md_safe(org.get('name') or 'your organization')}**. Ask which "
         "grants fit, what a grant requires, or how your applications are going. I look everything up in "
         "GrantBridge's records and show where each fact comes from. I can't decide eligibility: only the funder "
         "can.")

try:
    resolve_settings()
    key_found = True
except ConfigError:
    key_found = False
default_mock = (not key_found) or os.getenv("GRANTBRIDGE_ADVISOR_MODE", "").strip().lower() == "mock"
mock = st.toggle(
    "Practice mode (no AI, free)", value=default_mock, disabled=not key_found, key="advisor_mock",
    help="Answers are put together by GrantBridge's fixed rules from the same tools instead of the AI. They are "
         "labeled MOCK and cost nothing.",
)
if not key_found:
    st.caption("No API key was found, so the advisor runs in practice mode (no AI).")

messages = repo.list_messages(user.id)
notice = st.session_state.pop("advisor_notice", None)
if notice:
    st.warning(notice, icon=":material/info:")


def strip_label(content: str) -> str:
    return content.replace(advisor.MOCK_LABEL, "").strip()


def render_assistant(m: dict, number: int, latest: bool) -> None:
    p = m["payload"]
    if m["mode"] == "mock":
        st.markdown(":gray-badge[MOCK ANSWER · practice mode, no AI was used]")
    else:
        st.markdown(":violet-badge[:material/smart_toy: AI-written answer · checked by GrantBridge's guards]")
    st.markdown(ui.md_safe(strip_label(m["content"])))
    if p.get("clarifying_question"):
        st.info(ui.md_safe(p["clarifying_question"]), icon=":material/help:")
    facts, assumptions = p.get("known_facts") or [], p.get("assumptions") or []
    if facts or assumptions:
        with st.expander(f"Sources: {len(facts)} fact(s) from your records · {len(assumptions)} to verify",
                         expanded=latest, icon=":material/fact_check:"):
            st.markdown("**From your records**")
            st.caption("What the advisor looked up for this answer, with its source. Profile facts are self-reported.")
            lines = []
            for f in facts:
                tag, color = SOURCE_TAGS.get(f["source"], (f["source"], "gray"))
                lines.append(f"- {ui.md_safe(f['fact'])} :{color}-badge[{tag}]")
            st.markdown("\n".join(lines) or "- Nothing looked up.")
            st.markdown("**Still to verify**")
            st.markdown("\n".join(f"- {ui.md_safe(a)}" for a in assumptions) or "- None stated.")
    for note in p.get("guard_notes") or []:
        st.caption(f":material/shield: {note}")
    if p.get("notice"):
        st.caption(f":material/info: {p['notice']}")
    st.caption(f"Answer {number} · {m['created_at'][11:16]} UTC · steps and cost under Technical details")


if not messages:
    with st.container(border=True, key="card-starters"):
        st.markdown("**Try one of these to start**")
        with st.container(horizontal=True):
            for example in EXAMPLES:
                if st.button(example, key=f"example_{example}", icon=":material/chat:"):
                    st.session_state["advisor_pending"] = example
                    st.rerun()

answer_number = 0
total_answers = sum(m["role"] == "assistant" for m in messages)
for m in messages:
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(ui.external_md(m["content"]))
    else:
        answer_number += 1
        with st.chat_message("assistant", avatar=":material/support_agent:"):
            render_assistant(m, answer_number, latest=answer_number == total_answers)
if messages and st.button("Clear conversation", icon=":material/delete_sweep:"):
    repo.clear_messages(user.id)
    st.rerun()

answers = [m for m in messages if m["role"] == "assistant" and m["run_id"]]
if answers:
    with st.expander("Technical details: agent activity, tokens, and cost", icon=":material/terminal:"):
        numbers = {m["run_id"]: i for i, m in enumerate(answers, 1)}
        by_run = {m["run_id"]: m for m in answers}
        # The key changes with each new answer, so the selector always opens on the newest one.
        run_id = st.selectbox(
            "Answer", list(reversed(list(by_run))), key=f"activity_run_{len(answers)}",
            format_func=lambda rid: f"Answer {numbers[rid]} · {by_run[rid]['created_at'][11:16]} UTC · "
                                    f"{'mock' if by_run[rid]['mode'] == 'mock' else 'AI'}",
        )
        steps = trace.run_steps(user.id, run_id)
        st.dataframe(ui.trace_rows(steps), hide_index=True, width="stretch")
        totals = trace.summarize_calls(steps)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Model calls", totals["model_calls"])
        m2.metric("Tool calls", totals["tool_calls"])
        m3.metric("Model time", f"{totals['model_ms'] / 1000:.1f} s")
        m4.metric("Estimated cost", ui.usd(totals["cost_usd"]) if totals["model_calls"] else "$0",
                  help="From the token counts the provider reported and the rates in data/pricing.json.")
        if totals["model_calls"]:
            st.markdown(ui.token_breakdown(totals))
            st.caption(ui.price_note(totals["model"]))
            if totals["gateway_hits"]:
                st.caption(f"{totals['gateway_hits']} model call(s) were answered from Portkey's cache: saved copies "
                           "of identical earlier answers. No new tokens were billed for them.")
        else:
            st.caption("Mock answers make no AI calls and cost nothing.")
        st.caption(f"AI tokens used by your account in the last 24 hours: {llm.tokens_used_today(user.id):,} of "
                   f"{llm.daily_budget():,}. When the budget runs out, the advisor switches to mock mode.")
        st.caption("Inputs are redacted: your message and search keywords appear only as their length. "
                   "The trace never stores prompts, replies, or profile text.")

prompt = st.chat_input("Ask about grants, requirements, or your applications…", max_chars=repo.MAX_MESSAGE_CHARS)
prompt = prompt or st.session_state.pop("advisor_pending", None)
if prompt:
    try:
        with st.spinner("Mock planner at work…" if mock else "The advisor is looking things up…"):
            result = advisor.run_turn(user.id, prompt, want_mock=mock)
    except v.ValidationError as err:
        st.session_state["advisor_notice"] = str(err)
    else:
        if result.notice:
            st.session_state["advisor_notice"] = result.notice
    st.rerun()
