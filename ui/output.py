"""Output-Bereich: Ergebnis-Tabs, Suche im Transkript und Downloads."""

import re
from datetime import datetime

import streamlit as st


def render_output_section(transcript: str | None = None, summary: str | None = None, filename: str | None = None):
    """Rendert den Ergebnis-Bereich mit Tabs, Suche und Downloads.

    Args:
        transcript: Formatiertes Transkript (falls None, liest aus session_state).
        summary: Zusammenfassung (falls None, liest aus session_state).
        filename: Original-Dateiname für Download-Benennung.
    """
    if transcript is None:
        transcript = st.session_state.get("transcript")
    if summary is None:
        summary = st.session_state.get("summary")

    if not transcript and not summary:
        return

    st.divider()
    st.subheader("Ergebnis")

    # Download-Dateinamen generieren
    transcript_dl_name, summary_dl_name = _generate_download_names(filename)

    tab_transcript, tab_summary = st.tabs(["📄 Transkript", "📝 Zusammenfassung"])

    with tab_transcript:
        _render_transcript_tab(transcript, transcript_dl_name)

    with tab_summary:
        _render_summary_tab(summary, summary_dl_name)


def _generate_download_names(filename: str | None) -> tuple[str, str]:
    """Generiert beschreibende Download-Dateinamen."""
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
            )
    return (f"transkript_{date_str}.txt", f"zusammenfassung_{date_str}.txt")


def _render_transcript_tab(transcript: str | None, dl_name: str = "transkript.txt"):
    """Rendert den Transkript-Tab mit Suchfunktion und Download."""
    if not transcript:
        st.info("Kein Transkript vorhanden.")
        return

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

    # Download
    st.download_button(
        "📥 Transkript herunterladen",
        data=transcript,
        file_name=dl_name,
        mime="text/plain",
        use_container_width=True,
    )


def _render_summary_tab(summary: str | None, dl_name: str = "zusammenfassung.txt"):
    """Rendert den Zusammenfassungs-Tab mit Download."""
    if not summary:
        st.info("Keine Zusammenfassung vorhanden.")
        return

    st.markdown(summary)

    st.download_button(
        "📥 Zusammenfassung herunterladen",
        data=summary,
        file_name=dl_name,
        mime="text/plain",
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


def _escape_html(text: str) -> str:
    """Escaped HTML-Sonderzeichen."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
