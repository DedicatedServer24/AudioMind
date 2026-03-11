"""Output-Bereich: Ergebnis-Tabs, Suche im Transkript und Downloads."""

import re
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


def render_output_section(transcript: str | None = None, summary: str | None = None, filename: str | None = None, job_id: str | None = None):
    """Rendert den Ergebnis-Bereich mit Tabs, Suche und Downloads.

    Args:
        transcript: Formatiertes Transkript (falls None, liest aus session_state).
        summary: Zusammenfassung (falls None, liest aus session_state).
        filename: Original-Dateiname für Download-Benennung.
        job_id: Job-ID für Bearbeitungsfunktionen.
    """
    if transcript is None:
        transcript = st.session_state.get("transcript")
    if summary is None:
        summary = st.session_state.get("summary")

    if not transcript and not summary:
        return

    st.divider()
    st.subheader("Ergebnis")

    # Metriken anzeigen
    if transcript:
        word_count = len(transcript.split())
        char_count = len(transcript)
        reading_minutes = max(1, word_count // 200)
        col_words, col_reading, col_chars = st.columns(3)
        with col_words:
            st.metric("Wörter", f"{word_count:,}".replace(",", "."))
        with col_reading:
            st.metric("Lesedauer", f"~{reading_minutes} Min.")
        with col_chars:
            st.metric("Zeichen", f"{char_count:,}".replace(",", "."))

    # Download-Dateinamen generieren
    transcript_dl_name, summary_dl_name, summary_md_name = _generate_download_names(filename)

    tab_transcript, tab_summary = st.tabs(["📄 Transkript", "📝 Zusammenfassung"])

    with tab_transcript:
        _render_transcript_tab(transcript, transcript_dl_name, job_id)

    with tab_summary:
        _render_summary_tab(summary, summary_dl_name, summary_md_name)


def _generate_download_names(filename: str | None) -> tuple[str, str, str]:
    """Generiert beschreibende Download-Dateinamen.

    Returns:
        Tuple aus (transkript.txt, zusammenfassung.txt, zusammenfassung.md).
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    if filename:
        # Extension entfernen, sanitize
        from pathlib import Path
        stem = Path(filename).stem
        sanitized = stem.lower().replace(" ", "-").replace("_", "-")
        # Nur alphanumerisch und Bindestrich
        sanitized = re.sub(r"[^a-z0-9\-]", "", sanitized)
        sanitized = re.sub(r"-+", "-", sanitized).strip("-")
        if sanitized:
            return (
                f"transkript_{date_str}_{sanitized}.txt",
                f"zusammenfassung_{date_str}_{sanitized}.txt",
                f"zusammenfassung_{date_str}_{sanitized}.md",
            )
    return (f"transkript_{date_str}.txt", f"zusammenfassung_{date_str}.txt", f"zusammenfassung_{date_str}.md")


def _render_transcript_tab(transcript: str | None, dl_name: str = "transkript.txt", job_id: str | None = None):
    """Rendert den Transkript-Tab mit Suchfunktion, Bearbeitung und Download."""
    if not transcript:
        st.info("Kein Transkript vorhanden.")
        return

    # Sprecher umbenennen (nur wenn Sprecher-Labels vorhanden)
    speakers = sorted(set(re.findall(r"^(Speaker \d+):", transcript, re.MULTILINE)),
                       key=lambda s: -len(s))
    if speakers and job_id:
        with st.expander("👥 Sprecher umbenennen"):
            rename_map = {}
            cols_per_row = 2
            for i in range(0, len(speakers), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx < len(speakers):
                        with col:
                            new_name = st.text_input(
                                speakers[idx],
                                key=f"rename_{job_id}_{speakers[idx]}",
                                placeholder=f"z.B. Person {idx + 1}",
                            )
                            if new_name.strip():
                                rename_map[speakers[idx]] = new_name.strip()
            if rename_map and st.button("✅ Sprecher umbenennen", key="rename_speakers"):
                updated = transcript
                # Längste zuerst ersetzen
                for speaker in sorted(rename_map.keys(), key=lambda s: -len(s)):
                    updated = updated.replace(f"{speaker}:", f"{rename_map[speaker]}:")
                from services.database import update_job_transcript
                update_job_transcript(job_id, updated)
                st.rerun()

    # Bearbeiten-Toggle
    editing = st.toggle("✏️ Transkript bearbeiten", key="edit_transcript_toggle")

    if editing and job_id:
        edited_text = st.text_area(
            "Transkript bearbeiten",
            value=transcript,
            height=400,
            key="transcript_editor",
            label_visibility="collapsed",
        )
        col_save, col_resummarize = st.columns(2)
        with col_save:
            if st.button("💾 Änderungen übernehmen", use_container_width=True):
                from services.database import update_job_transcript
                update_job_transcript(job_id, edited_text)
                st.rerun()
        with col_resummarize:
            if st.button("🔄 Neu zusammenfassen", use_container_width=True):
                from services.database import get_job, update_job_summary, update_job_transcript
                update_job_transcript(job_id, edited_text)
                job = get_job(job_id)
                with st.spinner("Zusammenfassung wird neu erstellt..."):
                    from services.summarization import summarize
                    new_summary = summarize(
                        transcript=edited_text,
                        template_name=job["template_name"],
                        custom_prompt=job["custom_prompt"],
                    )
                    update_job_summary(job_id, new_summary)
                st.rerun()
    else:
        # Suchfeld
        search_query = st.text_input("🔍 Im Transkript suchen", key="transcript_search")

        if search_query.strip():
            highlighted, count = _highlight_matches(transcript, search_query.strip())
            if count > 0:
                st.caption(f"{count} Treffer gefunden")
                st.markdown(
                    f'<div style="max-height:500px;overflow-y:auto;padding:1rem;'
                    f'background:#f8f9fa;border-radius:0.5rem;white-space:pre-wrap;'
                    f'font-family:monospace;font-size:0.85rem;">{highlighted}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption("Keine Treffer gefunden")
                _render_text_area(transcript)
        else:
            _render_text_area(transcript)

    # Copy + Download
    _copy_to_clipboard(transcript, "transcript")
    st.download_button(
        "📥 Transkript herunterladen",
        data=transcript,
        file_name=dl_name,
        mime="text/plain",
        use_container_width=True,
    )


def _render_summary_tab(summary: str | None, dl_name: str = "zusammenfassung.txt", md_name: str = "zusammenfassung.md"):
    """Rendert den Zusammenfassungs-Tab mit Download."""
    if not summary:
        st.info("Keine Zusammenfassung vorhanden.")
        return

    st.markdown(summary)

    _copy_to_clipboard(summary, "summary")
    col_txt, col_md = st.columns(2)
    with col_txt:
        st.download_button(
            "📥 Als .txt herunterladen",
            data=summary,
            file_name=dl_name,
            mime="text/plain",
            use_container_width=True,
        )
    with col_md:
        st.download_button(
            "📥 Als .md herunterladen",
            data=summary,
            file_name=md_name,
            mime="text/markdown",
            use_container_width=True,
        )


def _render_text_area(text: str):
    """Rendert einen scrollbaren Textbereich."""
    st.markdown(
        f'<div style="max-height:500px;overflow-y:auto;padding:1rem;'
        f'background:#f8f9fa;border-radius:0.5rem;white-space:pre-wrap;'
        f'font-family:monospace;font-size:0.85rem;">{_escape_html(text)}</div>',
        unsafe_allow_html=True,
    )


def _highlight_matches(text: str, query: str) -> tuple[str, int]:
    """Hebt Suchtreffer im Text farbig hervor.

    Returns:
        Tuple aus (HTML-String mit Highlighting, Anzahl Treffer).
    """
    escaped_text = _escape_html(text)
    escaped_query = _escape_html(query)
    pattern = re.compile(re.escape(escaped_query), re.IGNORECASE)
    matches = pattern.findall(escaped_text)
    count = len(matches)
    highlighted = pattern.sub(
        lambda m: f'<mark style="background:#ffd54f;padding:0 2px;border-radius:2px;">{m.group()}</mark>',
        escaped_text,
    )
    return highlighted, count


def _copy_to_clipboard(text: str, key: str) -> None:
    """Rendert einen unsichtbaren Copy-Button via JavaScript."""
    escaped = text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    components.html(
        f"""
        <button id="copy-btn-{key}" onclick="copyText()" style="
            padding: 0.4rem 1rem; border: 1px solid #ccc; border-radius: 0.5rem;
            background: #f0f2f6; cursor: pointer; font-size: 0.85rem;">
            📋 Kopieren
        </button>
        <script>
        function copyText() {{
            const text = `{escaped}`;
            navigator.clipboard.writeText(text).then(() => {{
                const btn = document.getElementById('copy-btn-{key}');
                btn.textContent = '✅ Kopiert!';
                setTimeout(() => {{ btn.textContent = '📋 Kopieren'; }}, 2000);
            }});
        }}
        </script>
        """,
        height=45,
    )


def _escape_html(text: str) -> str:
    """Escaped HTML-Sonderzeichen."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
