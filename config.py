"""App-Konfiguration, Env-Validierung und Konstanten."""

import os

from dotenv import load_dotenv

from services.errors import ConfigError

load_dotenv()

# --- Konstanten ---

ALLOWED_FORMATS = ["mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac"]
MAX_UPLOAD_SIZE_MB = int(os.getenv("STREAMLIT_MAX_UPLOAD_SIZE", "500"))
MAX_API_FILE_SIZE_MB = 25
MAX_CHUNK_DURATION_SEC = 1200  # 20 Minuten
CHUNK_OVERLAP_SEC = 5

TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
DIARIZATION_MODEL = "gpt-4o-transcribe-diarize"
SUMMARIZATION_MODEL = "gpt-4o"

PROMPT_TEMPLATES = {
    "Meeting-Protokoll": "prompts/meeting.txt",
    "Zusammenfassung": "prompts/zusammenfassung.txt",
    "Aufgabenliste": "prompts/aufgaben.txt",
    "Interview-Auswertung": "prompts/interview.txt",
}


def validate_env():
    """Prüft, ob alle erforderlichen Env-Variablen gesetzt und gültig sind.

    Raises:
        ConfigError: Falls OPENAI_API_KEY fehlt oder ungültig ist.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ConfigError("OPENAI_API_KEY ist nicht gesetzt.")
    if not api_key.startswith("sk-"):
        raise ConfigError("OPENAI_API_KEY hat ein ungültiges Format (muss mit 'sk-' beginnen).")


def get_openai_api_key() -> str:
    """Gibt den validierten OpenAI API Key zurück."""
    validate_env()
    return os.getenv("OPENAI_API_KEY", "")
