"""Zentrale Exception-Klassen für AudioMind."""


class AudioMindError(Exception):
    """Basis-Exception für alle AudioMind-Fehler."""

    def __init__(self, message: str, user_message: str):
        super().__init__(message)
        self.user_message = user_message


class FileValidationError(AudioMindError):
    """Ungültiges Dateiformat oder Datei zu groß."""

    def __init__(self, message: str = "File validation failed"):
        super().__init__(message, "Dieses Dateiformat wird nicht unterstützt.")


class CompressionError(AudioMindError):
    """FFmpeg-Komprimierung fehlgeschlagen."""

    def __init__(self, message: str = "Compression failed"):
        super().__init__(message, "Fehler bei der Audio-Komprimierung.")


class TranscriptionError(AudioMindError):
    """OpenAI Transcription API Fehler."""

    def __init__(self, message: str = "Transcription failed"):
        super().__init__(message, "Transkription fehlgeschlagen. Bitte erneut versuchen.")


class SummarizationError(AudioMindError):
    """GPT-4o Zusammenfassungs-Fehler."""

    def __init__(self, message: str = "Summarization failed"):
        super().__init__(message, "Zusammenfassung fehlgeschlagen. Bitte erneut versuchen.")


class ConfigError(AudioMindError):
    """Fehlende oder ungültige Konfiguration."""

    def __init__(self, message: str = "Configuration error"):
        super().__init__(message, "App-Konfiguration fehlerhaft. Admin kontaktieren.")
