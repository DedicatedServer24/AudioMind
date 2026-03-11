"""AudioMind – Entry-Point."""

import streamlit as st

from config import APP_VERSION, validate_env
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
from services.database import get_jobs_by_user
from ui.sidebar import ACTIVE_STATUSES, render_sidebar_history

# Prüfe ob aktive Jobs existieren um Polling nur bei Bedarf zu aktivieren
_initial_jobs = get_jobs_by_user(username)
_has_active = any(j["status"] in ACTIVE_STATUSES for j in _initial_jobs)


@st.fragment(run_every=3)
def sidebar_fragment_polling():
    """Sidebar mit Polling: Aktualisiert alle 3s bei aktiven Jobs."""
    render_sidebar_history(username)
    # Wenn der angeschaute Job fertig wird: volle Seite neu laden
    selected_id = st.session_state.get("selected_job_id")
    if selected_id:
        jobs = get_jobs_by_user(username)
        for j in jobs:
            if j["id"] == selected_id and j["status"] in ("completed", "failed"):
                st.rerun()


@st.fragment
def sidebar_fragment_static():
    """Sidebar ohne Polling: Rendert einmal, kein Timer."""
    render_sidebar_history(username)


with st.sidebar:
    if _has_active:
        sidebar_fragment_polling()
    else:
        sidebar_fragment_static()
    st.caption(f"v{APP_VERSION}")

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
                job_id=selected_job_id,
            )

        elif status == "failed":
            import os
            st.error(f"Verarbeitung fehlgeschlagen: {job.get('error_message', 'Unbekannter Fehler')}")
            upload_path = job.get("upload_path", "")
            if upload_path and os.path.exists(upload_path):
                if st.button("🔄 Nochmal versuchen"):
                    from services.database import delete_job
                    new_job_id = create_job(
                        username=job["username"],
                        filename=job["filename"],
                        diarize=bool(job["diarize"]),
                        timestamps=bool(job["timestamps"]),
                        language=job["language"],
                        template_name=job["template_name"],
                        custom_prompt=job["custom_prompt"],
                        upload_path=upload_path,
                    )
                    delete_job(selected_job_id, username)
                    st.session_state["selected_job_id"] = new_job_id
                    st.rerun()
            else:
                st.warning("Datei nicht mehr verfügbar. Bitte erneut hochladen.")

        elif status in ("queued", "compressing", "transcribing", "summarizing"):
            # Job-Status als Fragment: aktualisiert nur diesen Bereich
            @st.fragment(run_every=3)
            def job_status_fragment():
                current_job = get_job(selected_job_id)
                if not current_job:
                    return
                s = current_job["status"]
                if s in ("completed", "failed"):
                    # Job fertig — volle Seite neu laden um Ergebnis anzuzeigen
                    st.rerun()
                    return
                from ui.sidebar import STATUS_LABELS
                label, _ = STATUS_LABELS.get(s, (s, "⚪"))
                progress_text = current_job.get("progress", "Warte auf Verarbeitung...")
                with st.status(f"{label}...", expanded=True, state="running"):
                    st.write(progress_text)
                    progress = current_job.get("progress_percent", 0.0) or 0.0
                    st.progress(progress)

            job_status_fragment()

else:
    # Upload-Ansicht
    with st.container(border=True):
        from ui.upload import render_process_button, render_upload_section

        render_upload_section()
        render_process_button()
