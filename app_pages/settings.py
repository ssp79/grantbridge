"""Account — sign-in, password, what is sent to the AI model, AI usage and cost, and account deletion."""

from datetime import datetime, timedelta, timezone

import streamlit as st

from grantbridge import auth, llm, session, trace, ui, validation
from grantbridge import components as c
from grantbridge.config import ConfigError, resolve_settings

user = session.require_user()

c.header("Account", ":material/account_circle:",
         "Your sign-in, your password, what GrantBridge sends to the AI model, and your AI usage.")

notice = st.session_state.pop("settings_notice", None)
if notice:
    st.success(notice, icon=":material/check_circle:")

account_col, model_col = st.columns(2)
with account_col:
    with st.container(border=True, key="card-account", height="stretch"):
        st.subheader("Your account", anchor=False)
        st.markdown(f"**Email:** {user.email}")
        st.caption(
            f"You are signed out after {session.IDLE_MINUTES} minutes of inactivity "
            "or when you refresh or close this tab."
        )
        here, everywhere = st.columns(2)
        if here.button("Log out", icon=":material/logout:", width="stretch", type="primary",
                       help="Ends this session. Everything you have saved stays in your account."):
            session.end("You have been logged out.")
            st.rerun()
        if everywhere.button("Log out everywhere", icon=":material/devices:", width="stretch",
                             help="Ends this account's sessions on every device and browser tab, including this "
                                  "one."):
            auth.log_out_everywhere(user.id)
            session.end("You logged out of all sessions.")
            st.rerun()
with model_col:
    with st.container(border=True, key="card-model", height="stretch"):
        st.subheader("AI model", anchor=False)
        try:
            status = resolve_settings().status()
        except ConfigError:
            st.error(
                "No API key found. Add PORTKEY_API_KEY to a .env file in the app folder "
                "or the folder above it, then restart the app. Everything except AI answers still works, "
                "in labeled mock mode.",
                icon=":material/key_off:",
            )
        else:
            st.markdown(f"**Model:** {status['model']}  \n**Provider:** {status['provider']}  \n"
                        f"**API key:** {status['key']}")

st.subheader("Change password", anchor=False)
with st.form("change_password", clear_on_submit=True):
    current = st.text_input("Current password", type="password", autocomplete="current-password",
                            max_chars=validation.PASSWORD_MAX)
    new = st.text_input("New password", type="password", autocomplete="new-password",
                        max_chars=validation.PASSWORD_MAX,
                        help=f"At least {validation.PASSWORD_MIN} characters.")
    again = st.text_input("Confirm new password", type="password", autocomplete="new-password",
                          max_chars=validation.PASSWORD_MAX)
    if st.form_submit_button("Update password", type="primary", icon=":material/lock_reset:"):
        if new != again:
            st.error("The new passwords do not match.", icon=":material/error:")
        else:
            try:
                auth.change_password(user.id, current, new)
            except (auth.AuthError, validation.ValidationError) as err:
                st.error(str(err), icon=":material/error:")
            else:
                session.keep_current_session(user.id)  # this tab stays signed in; every other session ends
                st.session_state["settings_notice"] = "Password updated. Your other sessions were signed out."
                st.rerun()

st.subheader("What GrantBridge sends to the AI model", anchor=False)
st.markdown(
    "- **When you use an AI feature** (Explain fit, AI Grant Advisor, facts, drafts, reviews), GrantBridge sends "
    "the facts from your Organization Profile, the facts you typed for that answer, your message or answer text, "
    "and the grant's text to gpt-6-luna through the course's Portkey gateway, which forwards it to Azure OpenAI. "
    "The gateway may keep logs and saved copies of answers, and Azure reports a 30-day data-retention setting for "
    "the course's model resource. GrantBridge asks the model provider not to store responses (`store=false`).\n"
    "- **Email addresses and phone numbers are removed first**, wherever they appear. Your login email and "
    "password are never sent.\n"
    "- **Never sent:** API keys, other accounts' data, or anything from mock mode (mock mode makes no AI calls).\n"
    "- **Live grant search** sends only your search filters and keyword to Grants.gov."
)

st.subheader("About this demo's security", anchor=False)
st.markdown(
    "- Passwords are stored only as salted Argon2id hashes.\n"
    "- Every record is tied to your account and checked on each read and write.\n"
    "- After 5 wrong passwords, an account is locked for 15 minutes.\n"
    "- The AI never sees API keys. Text from grants or pastes is treated as data, and every AI answer is "
    "scrubbed of secrets, tracking images, unknown links, and copies of GrantBridge's instructions.\n"
    "- AI use is limited per minute, per day, and per server; when a limit is reached you get a labeled "
    "mock answer or a plain message instead of an error.\n"
    "- **Not included:** email verification, password reset by email, HTTPS (add a "
    "reverse proxy for that), and per-IP rate limiting. This is a course demo, not a "
    "production system. Use sample data only."
)

with st.expander("Technical details: your AI usage and estimated cost", icon=":material/monitoring:"):
    st.markdown("**Your AI usage and estimated cost**")
    day = trace.usage_since(user.id, (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AI runs, last 24 h", day["ai_runs"], help="Each Explain fit, advisor answer, facts check, draft, or "
                                                          "review that called the AI model.")
    c2.metric("Tokens in / out", f"{day['input_tokens']:,} / {day['output_tokens']:,}",
              help=f"{day['cached_tokens']:,} input tokens were read from the prompt cache and "
                   f"{day['cache_write_tokens']:,} written to it; {day['reasoning_tokens']:,} output tokens were "
                   "reasoning.")
    c3.metric("Estimated cost, last 24 h", ui.usd(day["priced_cost_usd"])
              + (" + calls not estimated" if day["unpriced_calls"] else ""))
    c4.metric("Daily budget used",
              f"{min(100, round(100 * llm.tokens_used_today(user.id) / max(1, llm.daily_budget())))}%",
              help=f"{llm.daily_budget():,} input + output tokens per rolling 24 hours. Then AI features switch to "
                   "mock mode or a plain message.")
    recent = [r for r in trace.list_runs(user.id, limit=trace.MAX_RUNS_PER_USER) if r["model_calls"]][:15]
    if recent:
        st.dataframe(ui.run_rows(recent), hide_index=True, width="stretch")
    else:
        st.caption("No AI runs yet. Mock answers make no AI calls and cost nothing.")
    try:
        configured_model = resolve_settings().model
    except ConfigError:
        configured_model = "gpt-6-luna"
    st.caption(ui.price_note(recent[0]["model"] if recent else configured_model)
               + " Token counts are the provider's own numbers for each call. A call whose usage was not reported "
                 "shows no cost rather than a guess.")

with st.expander("Delete account", icon=":material/person_remove:"):
    st.write("This permanently deletes your account, profile, applications, and advisor history.")
    with st.form("delete_account", clear_on_submit=True):
        pw = st.text_input("Password", type="password", autocomplete="current-password",
                           max_chars=validation.PASSWORD_MAX)
        typed = st.text_input('Type DELETE to confirm')
        if st.form_submit_button("Delete my account", icon=":material/delete_forever:"):
            if typed.strip() != "DELETE":
                st.error("Type DELETE to confirm.", icon=":material/error:")
            else:
                try:
                    auth.delete_account(user.id, pw)
                except auth.AuthError as err:
                    st.error(str(err), icon=":material/error:")
                else:
                    session.end("Your account has been deleted.")
                    st.rerun()
