"""AudioMind – Entry-Point."""

import streamlit as st

from config import validate_env
from services.errors import ConfigError

# --- Page Config ---
st.set_page_config(page_title="AudioMind", page_icon="🎧", layout="centered")

# --- Env-Validierung ---
try:
    validate_env()
except ConfigError as e:
    st.error(e.user_message)
    st.stop()

# --- Auth ---
from auth import create_authenticator, load_auth_config, show_login

config = load_auth_config()
authenticator = create_authenticator(config)

if not st.session_state.get("authentication_status"):
    show_login(authenticator)
    st.stop()

# --- Eingeloggt ---
authenticator.logout(location="sidebar")
st.sidebar.write(f"Angemeldet als **{st.session_state.get('name')}**")

st.title("AudioMind")

# --- Upload, Optionen, Verarbeitung ---
from ui.upload import render_process_button, render_upload_section

render_upload_section()
render_process_button()

# --- Ergebnis-Anzeige ---
from ui.output import render_output_section

render_output_section()
