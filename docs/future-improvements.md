# Future Improvements

## Background Worker: Celery + Redis

When the team grows and the single-threaded worker becomes a bottleneck, migrate to a proper job queue:

### Architecture

- **Redis** as message broker (job queue)
- **Celery** as task worker (one or more worker processes)
- **Separate Docker container** for the worker (scales independently from the web app)

### Benefits over current approach

- Multiple workers can process jobs in parallel
- Better failure recovery (automatic retries, dead-letter queues)
- Horizontal scaling: add more worker containers as needed
- Job priority support
- Built-in monitoring (Flower dashboard)

### Required changes

- Add `redis` and `celery` to requirements.txt
- Add Redis container to Docker Compose / Coolify
- Add Celery worker container (same codebase, different entrypoint)
- Replace `services/worker.py` thread with Celery tasks
- `services/database.py` stays the same (SQLite or migrate to PostgreSQL for concurrent writes)

### When to migrate

- Multiple users frequently submitting jobs simultaneously
- Single worker can't keep up with job volume
- Need for job prioritization or parallel processing

---

## Sprecher-Erkennung verbessern

### 1. Speaker Hints via OpenAI API

Die OpenAI API unterstützt zwei optionale Parameter für `gpt-4o-transcribe-diarize`:

- **`known_speaker_names[]`** — Liste von Sprechernamen (z.B. `["Jan", "Lisa"]`), max. 4
- **`known_speaker_references[]`** — Kurze Audio-Samples (2-10 Sek.) der jeweiligen Stimme als Data-URLs

**UI-Konzept:**
- Beim Aktivieren von Sprecher-Labels: optionaler Bereich "Sprecher vorab definieren"
- Pro Sprecher: Name-Eingabefeld + Audio-Upload für Stimmprobe
- Max. 4 Sprecher (API-Limit)

**Dateien:** `ui/upload.py`, `services/transcription.py`, `services/database.py` (neue Felder)

### 2. Audio-Qualität für Diarization optimieren

**Status: Implementiert** — Diarization-Jobs nutzen jetzt schonendere Komprimierung:
- Sample-Rate: 24kHz statt 16kHz
- Bitrate: 64-192 kbps statt 32-128 kbps
- Chunks: 96 kbps statt 64 kbps

Weitere mögliche Verbesserungen:
- Noise Reduction vor der Transkription (`ffmpeg -af "afftdn"`)

**Datei:** `services/audio_processing.py`

### 3. Alternative Diarization-Dienste (Hybrid-Ansatz)

Falls OpenAI's Diarization nicht ausreicht, könnte ein spezialisierter Dienst nur für die Sprechertrennung genutzt werden:

| Dienst | Stärke | Typ |
|---|---|---|
| **pyannote.ai** | Beste Open-Source-Genauigkeit (DER ~11-19%), State-of-the-Art | Self-hosted, kostenlos |
| **AssemblyAI** | 30% besser bei Hintergrundgeräuschen, sehr niedrige Speaker-Count-Fehler | API, kostenpflichtig |
| **Deepgram** | Trainiert auf 100k+ Sprecher, 80+ Sprachen, schnellste Verarbeitung | API, kostenpflichtig |

**Hybrid-Ansatz:** Spezialisierten Dienst nur für Diarization nutzen (wer spricht wann), dann die Segmente an OpenAI für die eigentliche Transkription übergeben. Erfordert größere Architektur-Änderung.

---

## Streaming-Zusammenfassung

GPT-4o-Response streamen für schnelleres Feedback in der UI.

### Empfohlener Ansatz: Streaming in DB schreiben

- `services/summarization.py`: Neue Funktion `summarize_streaming()` mit `stream=True`
- Chunks akkumulieren und regelmäßig (~500 Zeichen) in DB schreiben
- `services/database.py`: `update_job_summary_partial(job_id, partial_summary)`
- `services/worker.py`: `summarize_streaming()` statt `summarize()` aufrufen
- `app.py`: Bei Status `summarizing` und vorhandener `summary` → Partial-Summary anzeigen
- Fragment pollt ohnehin alle 3s → zeigt automatisch den Zwischenstand
