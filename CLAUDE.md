# AudioMind — Projekt-Hinweise für Claude

## Tech-Stack
Python 3.11 · Streamlit · streamlit-authenticator · OpenAI SDK · FFmpeg · SQLite · Docker.

## Python-Venv
Immer `.venv/Scripts/python` (Windows) bzw. `.venv/bin/python` (Unix) verwenden. Nie ins System-Python installieren. `requirements.txt` muss zum Venv synchron gehalten werden.

## Architektur in einem Satz
Streamlit-UI reiht Upload-Jobs in eine SQLite-Queue ein, ein Daemon-Thread (`services/worker.py`) holt sie ab und führt die Pipeline `audio_processing → transcription → summarization` aus.

Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Konventionen

- **UI-Code** gehört nach `ui/`, **Business-Logik** nach `services/`. UI-Module importieren aus `services/`, nicht umgekehrt.
- **Fehler**: im Pipeline-Code eine der Klassen aus `services/errors.py` werfen (`FileValidationError`, `CompressionError`, `TranscriptionError`, `SummarizationError`, `ConfigError`). Die UI zeigt `e.user_message` an — daher beim Werfen eine verständliche Meldung mitgeben.
- **DB-Zugriffe** immer über Funktionen in `services/database.py`, nicht direkt mit `sqlite3.connect(...)`. Die Connection ist ein Singleton mit WAL-Mode.
- **Konstanten & Modellnamen** liegen in `config.py`. Neue Konstanten dort hinzufügen statt inline hardcoden.
- **Prompt-Templates** sind reine Textdateien in `prompts/` mit `{variable}`-Platzhaltern (`{transcript}`, `{language}`, `{speaker_count}`). Registrierung in `config.PROMPT_TEMPLATES`.
- **FFmpeg-Aufrufe** gehen ausschließlich über `services/audio_processing.py`. Bei neuen Aufrufen `subprocess.run` mit `capture_output=True`, Exit-Code prüfen, bei Fehler `CompressionError` werfen, Timeout setzen.
- **Streamlit-Polling**: aktive UI-Updates laufen über `@st.fragment(run_every=3)` — keine `time.sleep()`-Loops im Hauptthread einbauen.

## User-Verwaltung
`config.yaml` (im Volume gemountet, gitignored). Keine Selbstregistrierung. Hash-Generierung siehe [README.md#benutzer-verwalten](README.md#benutzer-verwalten).

## Nicht im Git
`config.yaml`, `.env`, `audiomind-plan.md`, `plan.md`, `data/`, `uploads/`, `error.txt` — siehe `.gitignore`. Nichts davon committen.

## Deployment
Coolify mit Dockerfile, Volumes für `config.yaml` und `data/`. Siehe [deployment.md](deployment.md).
