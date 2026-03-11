"""OpenAI Transcription Service: Standard und Diarization mit Multi-Chunk-Support."""

import logging
import time
from collections.abc import Callable

from openai import OpenAI, RateLimitError, APIError, APITimeoutError

from config import TRANSCRIPTION_MODEL, DIARIZATION_MODEL, get_openai_api_key
from services.errors import TranscriptionError

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY_SEC = 5


def _create_client() -> OpenAI:
    """Erstellt einen OpenAI-Client mit validiertem API Key."""
    return OpenAI(api_key=get_openai_api_key())


def transcribe_chunk(file_path: str, diarize: bool = False, language: str | None = None) -> dict:
    """Transkribiert einen einzelnen Audio-Chunk.

    Args:
        file_path: Pfad zur Audio-Datei (max. 25 MB).
        diarize: True für Sprecher-Erkennung (gpt-4o-transcribe-diarize).
        language: ISO-639-1 Sprachcode (optional, Auto-Detect wenn None).

    Returns:
        Dict mit 'text' und optional 'segments' (bei Diarization).
        segments: Liste von Dicts mit 'speaker', 'text', 'start', 'end'.

    Raises:
        TranscriptionError: Bei API-Fehlern nach max. Retries.
    """
    client = _create_client()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as audio_file:
                if diarize:
                    response = client.audio.transcriptions.create(
                        model=DIARIZATION_MODEL,
                        file=audio_file,
                        response_format="diarized_json",
                        **({"language": language} if language else {}),
                    )
                    return {
                        "text": response.text,
                        "segments": [
                            {
                                "speaker": seg.speaker,
                                "text": seg.text,
                                "start": seg.start,
                                "end": seg.end,
                            }
                            for seg in response.segments
                        ],
                    }
                else:
                    response = client.audio.transcriptions.create(
                        model=TRANSCRIPTION_MODEL,
                        file=audio_file,
                        response_format="text",
                        **({"language": language} if language else {}),
                    )
                    return {"text": response if isinstance(response, str) else response.text}

        except RateLimitError as e:
            last_error = e
            logger.warning(f"Rate-Limit bei Versuch {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC * attempt)
        except APITimeoutError as e:
            last_error = e
            logger.warning(f"Timeout bei Versuch {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
        except APIError as e:
            raise TranscriptionError(f"OpenAI API Fehler: {e}")
        except Exception as e:
            raise TranscriptionError(f"Unerwarteter Fehler bei Transkription: {e}")

    raise TranscriptionError(f"Transkription nach {MAX_RETRIES} Versuchen fehlgeschlagen: {last_error}")


def transcribe_chunks(
    chunk_paths: list[str],
    diarize: bool = False,
    language: str | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    """Transkribiert mehrere Audio-Chunks und fügt die Ergebnisse zusammen.

    Args:
        chunk_paths: Liste der Pfade zu den Audio-Chunks.
        diarize: True für Sprecher-Erkennung.
        language: ISO-639-1 Sprachcode (optional).
        progress_callback: Optional, wird mit (current_chunk, total_chunks) aufgerufen.

    Returns:
        Dict mit 'text' (zusammengefügter Text) und optional 'segments'.

    Raises:
        TranscriptionError: Bei API-Fehlern.
    """
    total = len(chunk_paths)
    all_text_parts = []
    all_segments = []
    time_offset = 0.0

    for i, chunk_path in enumerate(chunk_paths):
        if progress_callback:
            progress_callback(i + 1, total)

        result = transcribe_chunk(chunk_path, diarize=diarize, language=language)
        all_text_parts.append(result["text"])

        if diarize and "segments" in result:
            for seg in result["segments"]:
                all_segments.append({
                    "speaker": seg["speaker"],
                    "text": seg["text"],
                    "start": seg["start"] + time_offset,
                    "end": seg["end"] + time_offset,
                })
            # Offset für nächsten Chunk: Ende des letzten Segments
            if result["segments"]:
                time_offset = all_segments[-1]["end"]

    combined = {"text": "\n\n".join(all_text_parts)}
    if diarize and all_segments:
        combined["segments"] = all_segments
        # Sprecheranzahl ermitteln
        combined["speaker_count"] = len(set(seg["speaker"] for seg in all_segments))

    return combined


def format_diarized_transcript(segments: list[dict], timestamps: bool = False) -> str:
    """Formatiert Diarization-Segmente als lesbaren Text.

    Args:
        segments: Liste von Segment-Dicts mit speaker, text, start, end.
        timestamps: True um Zeitstempel einzufügen.

    Returns:
        Formatierter Text mit Sprecher-Labels.
    """
    lines = []
    for seg in segments:
        if timestamps:
            start_fmt = _format_time(seg["start"])
            end_fmt = _format_time(seg["end"])
            lines.append(f"[{start_fmt} – {end_fmt}] {seg['speaker']}: {seg['text']}")
        else:
            lines.append(f"{seg['speaker']}: {seg['text']}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    """Formatiert Sekunden als HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
