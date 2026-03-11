"""Sidebar: Job-History mit Status-Badges, Fortschritt und Aktionen."""

from datetime import datetime

import streamlit as st

from services.database import delete_all_jobs, delete_job, get_jobs_by_user

STATUS_LABELS = {
    "queued": ("In Warteschlange", "🔵"),
    "compressing": ("Komprimierung", "🟠"),
    "transcribing": ("Transkription", "🟠"),
    "summarizing": ("Zusammenfassung", "🟠"),
    "completed": ("Fertig", "🟢"),
    "failed": ("Fehlgeschlagen", "🔴"),
}

ACTIVE_STATUSES = {"queued", "compressing", "transcribing", "summarizing"}


def render_sidebar_history(username: str) -> bool:
    """Rendert die Job-History. Muss innerhalb von `with st.sidebar:` aufgerufen werden.

    Returns:
        True wenn mindestens ein Job aktiv ist.
    """
    jobs = get_jobs_by_user(username)
    has_active = any(j["status"] in ACTIVE_STATUSES for j in jobs)

    st.markdown("---")
    st.subheader("Verlauf")

    if not jobs:
        st.caption("Noch keine Aufträge.")
        return False

    for job in jobs:
        _render_job_entry(job, username)

    # "Alle löschen" Button
    completed_or_failed = [j for j in jobs if j["status"] in ("completed", "failed")]
    if completed_or_failed:
        st.markdown("---")
        if st.button("🗑️ Alle löschen", use_container_width=True, key="delete_all"):
            delete_all_jobs(username)
            if st.session_state.get("selected_job_id"):
                selected_id = st.session_state["selected_job_id"]
                if any(j["id"] == selected_id for j in completed_or_failed):
                    del st.session_state["selected_job_id"]
            st.rerun()

    return has_active


def _render_job_entry(job: dict, username: str) -> None:
    """Rendert einen einzelnen Job-Eintrag."""
    job_id = job["id"]
    status = job["status"]
    label, icon = STATUS_LABELS.get(status, (status, "⚪"))

    # Dateiname kürzen
    filename = job["filename"]
    if len(filename) > 25:
        filename = filename[:22] + "..."

    # Datum formatieren
    created = job["created_at"]
    try:
        dt = datetime.fromisoformat(created)
        date_str = dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        date_str = ""

    # Container für den Eintrag
    col1, col2 = st.columns([5, 1])

    with col1:
        if st.button(
            f"{icon} {filename}\n{date_str} · {label}",
            key=f"job_{job_id}",
            use_container_width=True,
        ):
            st.session_state["selected_job_id"] = job_id
            st.rerun()

    with col2:
        if status in ("completed", "failed"):
            if st.button("🗑️", key=f"del_{job_id}"):
                delete_job(job_id, username)
                if st.session_state.get("selected_job_id") == job_id:
                    del st.session_state["selected_job_id"]
                st.rerun()

    # Fortschrittsbalken für aktive Jobs
    if status in ACTIVE_STATUSES:
        progress = job.get("progress_percent", 0.0) or 0.0
        st.progress(progress, text=job.get("progress", ""))
