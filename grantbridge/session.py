"""Login state for Streamlit.

Streamlit keeps st.session_state on the server, one per browser connection, so
the logged-in user id never travels to the browser and cannot be edited there.
Every page run re-loads the user from the database, so a deleted account is
signed out right away. Sessions end after IDLE_MINUTES without activity, on
logout, or when the browser tab is refreshed or closed (no persistent cookie).
"""

from __future__ import annotations

import time

import streamlit as st

from grantbridge.auth import User, get_user

AUTH_KEY = "gb_auth"
FLASH_KEY = "gb_flash"
IDLE_MINUTES = 30


def start(user: User) -> None:
    """Begin a fresh session for this user, dropping any earlier state."""
    st.session_state.clear()
    st.session_state[AUTH_KEY] = {"user_id": user.id, "last_seen": time.time(), "epoch": user.session_epoch}


def end(message: str | None = None) -> None:
    st.session_state.clear()
    if message:
        st.session_state[FLASH_KEY] = message


def current_user() -> User | None:
    auth = st.session_state.get(AUTH_KEY)
    if not auth:
        return None
    if time.time() - auth["last_seen"] > IDLE_MINUTES * 60:
        end(f"You were signed out after {IDLE_MINUTES} minutes of inactivity.")
        return None
    user = get_user(auth["user_id"])
    if user is None:
        end("Your session has ended. Please log in again.")
        return None
    if user.session_epoch != auth.get("epoch", 0):
        end("You were signed out because this account logged out of all sessions or changed its password.")
        return None
    auth["last_seen"] = time.time()
    return user


def require_user() -> User:
    """For use at the top of every signed-in page."""
    user = current_user()
    if user is None:
        st.rerun()
    return user


def keep_current_session(user_id: int) -> None:
    """After this session changed the epoch (password change), keep it signed in; others still end."""
    user = get_user(user_id)
    if user is not None and AUTH_KEY in st.session_state:
        st.session_state[AUTH_KEY]["epoch"] = user.session_epoch


def has_flash() -> bool:
    """A sign-in message is waiting (logged out, timed out, signed out elsewhere): show the Sign in page."""
    return FLASH_KEY in st.session_state


def pop_flash() -> str | None:
    return st.session_state.pop(FLASH_KEY, None)
