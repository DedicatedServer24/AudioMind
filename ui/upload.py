"""Upload-Bereich: Datei-Upload, Optionen und Prompt-Auswahl."""

import logging

import streamlit as st

from config import ALLOWED_FORMATS, MAX_UPLOAD_SIZE_MB, PROMPT_TEMPLATES

logger = logging.getLogger(__name__)


def render_upload_section():
    """Rendert den Upload-Bereich mit Optionen und Prompt-Auswahl.

    Speichert alle Eingaben in st.session_state:
    - uploaded_file: Die hochgeladene Datei
    - diarize: Sprecher-Labels an/aus
    - timestamps: Zeitstempel an/aus
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

    st.caption(f"📄 {uploaded_file.name} ({uploaded_file.size / 1024 / 1024:.1f} MB)")

    # --- Optionen ---
    st.subheader("Optionen")
    col1, col2 = st.columns(2)
    with col1:
        diarize = st.toggle("Sprecher-Labels", value=False, help="Erkennt verschiedene Sprecher im Audio")
    with col2:
        timestamps = st.toggle("Zeitstempel", value=False, help="Fügt Zeitangaben zum Transkript hinzu")

    st.session_state["diarize"] = diarize
    st.session_state["timestamps"] = timestamps

    # --- Prompt-Vorlage ---
    st.subheader("Zusammenfassung")
    template_options = list(PROMPT_TEMPLATES.keys()) + ["Eigener Prompt"]
    selected = st.selectbox("Prompt-Vorlage", template_options)

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
    """Rendert den Verarbeitungs-Button und führt den kompletten Flow aus.

    Returns:
        True wenn die Verarbeitung erfolgreich war, sonst False.
    """
    from services.audio_processing import cleanup_temp_dir, process_upload
    from services.errors import AudioMindError
    from services.summarization import summarize
    from services.transcription import (
        format_diarized_transcript,
        transcribe_chunks,
    )

    uploaded_file = st.session_state.get("uploaded_file")
    if not uploaded_file:
        return False

    # Validierung: Eigener Prompt darf nicht leer sein
    if st.session_state.get("template_name") is None and not st.session_state.get("custom_prompt", "").strip():
        st.button("Zusammenfassen", disabled=True, use_container_width=True)
        st.caption("⚠️ Bitte einen eigenen Prompt eingeben.")
        return False

    if not st.button("Zusammenfassen", type="primary", use_container_width=True):
        return False

    # --- Verarbeitung ---
    diarize = st.session_state.get("diarize", False)
    timestamps = st.session_state.get("timestamps", False)
    template_name = st.session_state.get("template_name")
    custom_prompt = st.session_state.get("custom_prompt")

    temp_dir = None
    try:
        with st.status("Verarbeitung läuft...", expanded=True) as status:
            # Schritt 1: Komprimierung
            st.write("🔧 Datei wird komprimiert...")
            chunk_paths = process_upload(uploaded_file.name, uploaded_file.getvalue())
            temp_dir = str(__import__("pathlib").Path(chunk_paths[0]).parent)

            # Schritt 2: Transkription
            total_chunks = len(chunk_paths)
            if total_chunks > 1:
                st.write(f"🎙️ Transkription läuft... (0/{total_chunks} Chunks)")

                def progress_cb(current, total):
                    st.write(f"🎙️ Transkription läuft... ({current}/{total} Chunks)")

                result = transcribe_chunks(chunk_paths, diarize=diarize, progress_callback=progress_cb)
            else:
                st.write("🎙️ Transkription läuft...")
                result = transcribe_chunks(chunk_paths, diarize=diarize)

            # Transkript formatieren
            if diarize and "segments" in result:
                transcript_text = format_diarized_transcript(result["segments"], timestamps=timestamps)
            else:
                transcript_text = result["text"]

            # Schritt 3: Zusammenfassung
            st.write("📝 Zusammenfassung wird erstellt...")
            summary_text = summarize(
                transcript=result["text"],
                template_name=template_name,
                custom_prompt=custom_prompt,
                speaker_count=result.get("speaker_count"),
            )

            status.update(label="Verarbeitung abgeschlossen!", state="complete", expanded=False)

        # Ergebnisse in Session State speichern
        st.session_state["transcript"] = transcript_text
        st.session_state["summary"] = summary_text
        return True

    except AudioMindError as e:
        logger.error(f"Verarbeitung fehlgeschlagen: {e}", exc_info=True)
        st.error(e.user_message)
        return False
    except Exception as e:
        logger.error(f"Unerwarteter Fehler: {e}", exc_info=True)
        st.error("Ein unerwarteter Fehler ist aufgetreten. Bitte erneut versuchen.")
        return False
    finally:
        if temp_dir:
            cleanup_temp_dir(temp_dir)
