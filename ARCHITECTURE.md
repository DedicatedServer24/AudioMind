# AudioMind – Architektur

Öffentliche, entwicklerorientierte Beschreibung der App. Internes Planungsdokument (nicht committet): `audiomind-plan.md`, `plan.md`.

## Prinzipien

- **Single-File Streamlit-App** als Entry-Point (`app.py`), UI und Business-Logik strikt getrennt (`ui/` vs. `services/`).
- **Asynchrone Job-Queue** mit SQLite + Background-Thread — Uploads blockieren die UI nicht, Jobs überleben Browser-Reloads und Container-Restarts.
- **Nur lokale State-Persistenz**: SQLite für Jobs, Dateisystem für Uploads/Temp-Chunks. Kein externes Message-Broker, kein Redis, keine Cloud-Storage.
- **OpenAI als einziger externer Dienst** für Transkription (`gpt-4o-transcribe` / `gpt-4o-transcribe-diarize`) und Summarization (`gpt-4o`).
- **Auth via `streamlit-authenticator`** mit bcrypt-gehashten Passwörtern in `config.yaml` (als Volume gemountet, keine Selbstregistrierung).

## Komponenten

```
┌─────────────── Streamlit UI ───────────────┐
│  app.py     ui/upload.py   ui/output.py    │
│             ui/sidebar.py  auth.py         │
└──────┬─────────────────────────────┬────────┘
       │  create_job                 │  polling (3s fragment)
       ▼                             │
┌─────────────── SQLite ──────────────────────┐
│  services/database.py    (jobs-Tabelle)     │
└──────┬──────────────────────────────────────┘
       │  get_next_queued_job
       ▼
┌─────────────── Worker-Thread ───────────────┐
│  services/worker.py                         │
│    1. audio_processing.process_upload()     │
│    2. transcription.transcribe_chunks()     │
│    3. summarization.summarize()             │
└──────┬──────────────────────────────────────┘
       │
       ▼
   OpenAI API
```

## Pipeline (pro Job)

Alle Statusübergänge werden in der `jobs`-Tabelle protokolliert und vom UI-Fragment alle 3 s gepollt, solange der Job aktiv ist.

| Schritt | Status | Was passiert | Quelle |
|---|---|---|---|
| 1 | `queued` | Job wird in DB eingetragen, Upload in `uploads/{uuid}.ext` persistiert | `ui/upload.py`, `database.create_job` |
| 2 | `compressing` | FFmpeg entfernt Video, konvertiert zu Mono-MP3 (16 kHz bzw. 24 kHz mit Diarization), splittet bei Dauer > 20 min in Chunks à ≤ 25 MB mit 5 s Overlap | `services/audio_processing.py` |
| 3 | `transcribing` | Jeder Chunk einzeln an OpenAI Transcription API, Progress-Callback aktualisiert DB pro Chunk (10 % → 80 %) | `services/transcription.py` |
| 4 | `summarizing` | Gesamttranskript + Prompt-Template → `gpt-4o` (Progress 80 % → 99 %) | `services/summarization.py` |
| 5 | `completed` / `failed` | Ergebnis in DB, Temp-Chunks gelöscht, Upload bei Erfolg gelöscht (bei Fehler bleibt er für Retry) | `services/worker.py` |

### Recovery

Beim App-Start setzt `worker._recover_stale_jobs()` alle Jobs zurück auf `queued`, die beim letzten Shutdown in einem Zwischenstatus (`compressing`, `transcribing`, `summarizing`) waren. Der Worker verarbeitet sie dann von vorne.

### Retry

Fehlgeschlagene Jobs zeigen in der Detailansicht einen „Nochmal versuchen"-Button, sofern das Original-Upload noch existiert. Ein neuer Job wird mit identischen Optionen erzeugt, der alte gelöscht.

## Datenmodell (SQLite)

Eine Tabelle `jobs` mit diesen Spalten (siehe `services/database.py:init_db`):

- Identifikation: `id` (UUID), `username`, `filename`
- Optionen: `diarize`, `timestamps`, `language`, `template_name`, `custom_prompt`
- Dateipfade: `upload_path`
- Status: `status`, `progress` (Freitext), `progress_percent` (0.0–1.0)
- Ergebnis: `transcript`, `summary`, `error_message`
- Timestamps: `created_at`, `completed_at`

Verbindung als Singleton mit `check_same_thread=False` und `PRAGMA journal_mode=WAL` — UI-Thread und Worker-Thread teilen sich die Connection gefahrlos.

## Auth-Flow

`auth.load_auth_config()` liest `config.yaml`, `streamlit-authenticator` rendert das Login-Widget und schreibt bei Erfolg `username`, `name`, `authentication_status` in den `st.session_state`. Alle Jobs werden an diesen `username` gebunden und die History nach `username` gefiltert (`database.get_jobs_by_user`).

User-Verwaltung siehe [README.md#benutzer-verwalten](README.md#benutzer-verwalten).

## UI-Rendering

- **Kein manuelles Polling der ganzen Seite** — Streamlit-Fragmente (`@st.fragment(run_every=3)`) aktualisieren gezielt nur Sidebar und Job-Status, solange aktive Jobs existieren. Sobald keine aktiven Jobs mehr da sind, wird auf das statische Fragment umgeschaltet (kein unnötiger Traffic).
- **Job-Detail**: triggert `st.rerun()`, sobald der beobachtete Job `completed` oder `failed` erreicht — dadurch wechselt die Ansicht automatisch vom Fortschrittsindikator zum Ergebnis.

## Konfiguration

| Herkunft | Zweck | Beispiele |
|---|---|---|
| `.env` (nicht im Git) | Secrets | `OPENAI_API_KEY` |
| `config.py` | Fachliche Konstanten + Env-Validierung | Modellnamen, Chunk-Größen, Upload-Limit |
| `.streamlit/config.toml` | Streamlit-Serverkonfiguration | `maxUploadSize`, Port, Theme |
| `config.yaml` (Volume) | User-Credentials | Username → bcrypt-Hash |
| `prompts/*.txt` | Prompt-Templates mit `{variable}`-Platzhaltern | `{transcript}`, `{language}`, `{speaker_count}` |

## Fehlerklassen

Alle domänenspezifischen Fehler sind in `services/errors.py` definiert und werden vom Worker als `error_message` in die DB geschrieben. Die UI zeigt je nach Klasse eine passende User-Meldung (siehe `services/errors.py`).

| Klasse | Auslöser |
|---|---|
| `FileValidationError` | Ungültiges Format, Datei zu groß |
| `CompressionError` | FFmpeg-Fehler (Exit-Code, Timeout) |
| `TranscriptionError` | OpenAI-API-Fehler bei Transkription |
| `SummarizationError` | OpenAI-API-Fehler bei Summarization |
| `ConfigError` | Fehlender/ungültiger `OPENAI_API_KEY` beim Start |

## Bewusste Nicht-Entscheidungen

- **Keine Selbstregistrierung** — internes Team-Tool, Admin pflegt User in `config.yaml`.
- **Kein Redis/Celery/RQ** — ein Thread + SQLite reicht für das erwartete Job-Volumen und spart Ops-Aufwand.
- **Kein S3/Object-Storage** — Volumes auf dem Host genügen, Uploads werden nach Erfolg gelöscht.
- **Keine Streaming-API für Transcription** — Chunk-basiert ist einfacher zu fehlern und zu zeigen.
- **Kein eigenes Frontend-Framework** — Streamlit ist für das Team und die Feature-Dichte ausreichend.

## Erweiterungspfade

Siehe [docs/future-improvements.md](docs/future-improvements.md). Kurze Auswahl:

- Batch-Upload (mehrere Dateien, ZIP-Export der Ergebnisse)
- URL-Import für YouTube/Podcast
- Export als `.pdf`/`.docx`
- Admin-Dashboard mit API-Kosten und User-Verwaltung
- Mehrsprachige UI
