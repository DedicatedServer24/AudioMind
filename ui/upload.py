"""Upload-Bereich: Datei-Upload, Optionen und Prompt-Auswahl."""

import logging
import os
from pathlib import Path

import streamlit as st

from config import ALLOWED_FORMATS, MAX_UPLOAD_SIZE_MB, PROMPT_TEMPLATES

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


def render_upload_section():
    """Rendert den Upload-Bereich mit Optionen und Prompt-Auswahl.

    Speichert alle Eingaben in st.session_state:
    - uploaded_file: Die hochgeladene Datei
    - diarize: Sprecher-Labels an/aus
    - timestamps: Zeitstempel an/aus
    - language: Sprachcode oder None (Auto-Detect)
    - template_name: Gewähltes Template (oder None bei eigenem Prompt)
    - custom_prompt: Eigener Prompt-Text (oder None)
    """
    # --- Datei-Upload ---
    allowed_types = [f".{fmt}" for fmt in ALLOWED_FORMATS]
    uploaded_file = st.file_uploader(
        "Audio- oder Videodatei hochladen",
        type=ALLOWED_FORMATS,
        help=f"Erlaubte Formate: {', '.join(allowed_types)} – Max. {MAX_UPLOAD_SIZE_MB} MB",
    )
    st.session_state["uploaded_file"] = uploaded_file

    if not uploaded_file:
        return

    st.info(f"📄 {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.1f} MB)")

    # --- Optionen ---
    st.subheader("Optionen")
    col1, col2, col3 = st.columns(3)
    with col1:
        diarize = st.toggle("Sprecher-Labels", value=False, help="Erkennt verschiedene Sprecher im Audio")
    with col2:
        timestamps = st.toggle("Zeitstempel", value=False, help="Fügt Zeitangaben zum Transkript hinzu")
    with col3:
        language_options = ["Auto-Detect", "Deutsch", "English"]
        language_selection = st.selectbox("Sprache", language_options)
        language_map = {"Auto-Detect": None, "Deutsch": "de", "English": "en"}
        language = language_map[language_selection]

    st.session_state["diarize"] = diarize
    st.session_state["timestamps"] = timestamps
    st.session_state["language"] = language

    # --- Prompt-Vorlage ---
    st.subheader("Zusammenfassung")

    TEMPLATE_DESCRIPTIONS = {
        "Meeting-Protokoll": "Teilnehmer, besprochene Themen, Entscheidungen und Action Items",
        "Zusammenfassung": "Kompakter Überblick mit Kernaussagen und Fazit",
        "Aufgabenliste": "Alle To-Dos mit Verantwortlichen, Fristen und Prioritäten",
        "Interview-Auswertung": "Kernaussagen pro Thema, wichtige Zitate und Gesamteindruck",
        "Eigener Prompt": "Eigene Anweisungen für die Zusammenfassung formulieren",
    }

    template_options = list(PROMPT_TEMPLATES.keys()) + ["Eigener Prompt"]
    selected = st.selectbox(
        "Prompt-Vorlage",
        template_options,
        format_func=lambda x: f"{x} — {TEMPLATE_DESCRIPTIONS[x]}",
    )

    custom_prompt = None
    if selected == "Eigener Prompt":
        custom_prompt = st.text_area(
            "Eigenen Prompt eingeben",
            height=150,
            placeholder="Beschreibe, wie das Transkript zusammengefasst werden soll...",
        )
        st.session_state["template_name"] = None
        st.session_state["custom_prompt"] = custom_prompt
    else:
        st.session_state["template_name"] = selected
        st.session_state["custom_prompt"] = None


def render_process_button():
    """Rendert den Verarbeitungs-Button und reiht den Job in die Queue ein."""
    from services.database import create_job

    uploaded_file = st.session_state.get("uploaded_file")
    if not uploaded_file:
        return

    # Validierung: Eigener Prompt darf nicht leer sein
    if st.session_state.get("template_name") is None and not st.session_state.get("custom_prompt", "").strip():
        st.button("Zusammenfassen", disabled=True, use_container_width=True)
        st.caption("⚠️ Bitte einen eigenen Prompt eingeben.")
        return

    if not st.button("Zusammenfassen", type="primary", use_container_width=True):
        return

    # Upload-Datei persistent speichern
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    extension = Path(uploaded_file.name).suffix
    # Temporäre ID für Dateinamen
    import uuid
    temp_id = str(uuid.uuid4())
    upload_path = os.path.join(UPLOAD_DIR, f"{temp_id}{extension}")

    with open(upload_path, "wb") as f:
        f.write(uploaded_file.getvalue())

    # Job in DB erstellen
    username = st.session_state.get("username", "unknown")
    job_id = create_job(
        username=username,
        filename=uploaded_file.name,
        diarize=st.session_state.get("diarize", False),
        timestamps=st.session_state.get("timestamps", False),
        language=st.session_state.get("language"),
        template_name=st.session_state.get("template_name"),
        custom_prompt=st.session_state.get("custom_prompt"),
        upload_path=upload_path,
    )

    st.session_state["selected_job_id"] = job_id
    st.rerun()
