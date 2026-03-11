"""AudioMind – Entry-Point."""

import streamlit as st

from config import validate_env
from services.errors import ConfigError

# --- Page Config ---
st.set_page_config(page_title="AudioMind", page_icon="🎧", layout="wide")

# --- Env-Validierung ---
try:
    validate_env()
except ConfigError as e:
    st.error(e.user_message)
    st.stop()

# --- Datenbank + Worker starten ---
from services.database import init_db
from services.worker import start_worker

init_db()
start_worker()

# --- Auth ---
from auth import create_authenticator, load_auth_config, show_login

config = load_auth_config()
authenticator = create_authenticator(config)

if not st.session_state.get("authentication_status"):
    show_login(authenticator)
    st.stop()

# --- Eingeloggt ---
username = st.session_state.get("username", "unknown")
authenticator.logout(location="sidebar")
st.sidebar.write(f"Angemeldet als **{st.session_state.get('name')}**")

# --- Sidebar History ---
from ui.sidebar import render_sidebar_history

has_active_jobs = render_sidebar_history(username)

# --- Auto-Refresh bei aktiven Jobs ---
if has_active_jobs:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=3000, key="auto_refresh")

# --- Hauptbereich ---
st.title("AudioMind")

selected_job_id = st.session_state.get("selected_job_id")

if selected_job_id:
    # Job-Detail-Ansicht
    from services.database import create_job, get_job

    job = get_job(selected_job_id)

    if job is None:
        st.warning("Job nicht gefunden.")
        del st.session_state["selected_job_id"]
        st.rerun()
    else:
        # Zurück-Button
        if st.button("← Zurück zur Übersicht"):
            del st.session_state["selected_job_id"]
            st.rerun()

        status = job["status"]

        if status == "completed":
            from ui.output import render_output_section
            render_output_section(
                transcript=job["transcript"],
                summary=job["summary"],
                filename=job["filename"],
            )

        elif status == "failed":
            st.error(f"Verarbeitung fehlgeschlagen: {job.get('error_message', 'Unbekannter Fehler')}")
            if st.button("🔄 Nochmal versuchen"):
                import os
                # Neuen Job mit gleichen Parametern erstellen
                new_job_id = create_job(
                    username=job["username"],
                    filename=job["filename"],
                    diarize=bool(job["diarize"]),
                    timestamps=bool(job["timestamps"]),
                    language=job["language"],
                    template_name=job["template_name"],
                    custom_prompt=job["custom_prompt"],
                    upload_path=job.get("upload_path", ""),
                )
                st.session_state["selected_job_id"] = new_job_id
                st.rerun()

        elif status in ("queued", "compressing", "transcribing", "summarizing"):
            from ui.sidebar import STATUS_LABELS
            label, icon = STATUS_LABELS.get(status, (status, "⚪"))
            st.info(f"{icon} {label}: {job.get('progress', 'Warte auf Verarbeitung...')}")
            progress = job.get("progress_percent", 0.0) or 0.0
            st.progress(progress)

else:
    # Upload-Ansicht
    with st.container(border=True):
        from ui.upload import render_process_button, render_upload_section

        render_upload_section()
        render_process_button()
