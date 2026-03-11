"""GPT-4o Zusammenfassungs-Service: Template-Laden, Variablen-Ersetzung und API-Call."""

import logging
import time
from pathlib import Path

from openai import OpenAI, RateLimitError, APIError, APITimeoutError

from config import SUMMARIZATION_MODEL, PROMPT_TEMPLATES, get_openai_api_key
from services.errors import SummarizationError

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY_SEC = 5


def _create_client() -> OpenAI:
    """Erstellt einen OpenAI-Client mit validiertem API Key."""
    return OpenAI(api_key=get_openai_api_key())


def load_template(template_name: str) -> str:
    """Lädt ein Prompt-Template aus der prompts/-Verzeichnis.

    Args:
        template_name: Key aus PROMPT_TEMPLATES (z.B. "Meeting-Protokoll").

    Returns:
        Template-Inhalt als String.

    Raises:
        SummarizationError: Falls das Template nicht gefunden wird.
    """
    if template_name not in PROMPT_TEMPLATES:
        raise SummarizationError(f"Unbekanntes Template: {template_name}")

    template_path = Path(__file__).parent.parent / PROMPT_TEMPLATES[template_name]
    try:
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SummarizationError(f"Template-Datei nicht gefunden: {template_path}")


def build_prompt(
    template_text: str,
    transcript: str,
    language: str = "Deutsch",
    speaker_count: int | None = None,
) -> str:
    """Ersetzt Platzhalter im Template mit den tatsächlichen Werten.

    Args:
        template_text: Template-String mit {variable}-Platzhaltern.
        transcript: Das vollständige Transkript.
        language: Erkannte Sprache des Audios.
        speaker_count: Anzahl erkannter Sprecher (optional).

    Returns:
        Fertiger Prompt-String.
    """
    variables = {
        "transcript": transcript,
        "language": language,
        "speaker_count": str(speaker_count) if speaker_count else "unbekannt",
    }
    return template_text.format(**variables)


def summarize(
    transcript: str,
    template_name: str | None = None,
    custom_prompt: str | None = None,
    language: str = "Deutsch",
    speaker_count: int | None = None,
) -> str:
    """Erstellt eine Zusammenfassung des Transkripts mit GPT-4o.

    Entweder template_name ODER custom_prompt muss angegeben werden.

    Args:
        transcript: Das vollständige Transkript.
        template_name: Key aus PROMPT_TEMPLATES (z.B. "Meeting-Protokoll").
        custom_prompt: Eigener Prompt-Text (wird direkt + Transkript verwendet).
        language: Erkannte Sprache des Audios.
        speaker_count: Anzahl erkannter Sprecher (optional).

    Returns:
        Zusammenfassung als String.

    Raises:
        SummarizationError: Bei fehlenden Parametern oder API-Fehlern.
    """
    if not template_name and not custom_prompt:
        raise SummarizationError("Weder Template noch eigener Prompt angegeben.")

    if custom_prompt:
        prompt = f"{custom_prompt}\n\nTranskript:\n{transcript}"
    else:
        template_text = load_template(template_name)
        prompt = build_prompt(template_text, transcript, language, speaker_count)

    return _call_gpt4o(prompt)


def _call_gpt4o(prompt: str) -> str:
    """Sendet den Prompt an GPT-4o mit Retry-Logik.

    Args:
        prompt: Der vollständige Prompt.

    Returns:
        Antwort-Text von GPT-4o.

    Raises:
        SummarizationError: Bei API-Fehlern nach max. Retries.
    """
    client = _create_client()
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=SUMMARIZATION_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content

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
            raise SummarizationError(f"OpenAI API Fehler: {e}")
        except Exception as e:
            raise SummarizationError(f"Unerwarteter Fehler bei Zusammenfassung: {e}")

    raise SummarizationError(
        f"Zusammenfassung nach {MAX_RETRIES} Versuchen fehlgeschlagen: {last_error}"
    )
