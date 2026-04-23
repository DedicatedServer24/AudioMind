# AudioMind

Internes Web-Tool für Teams: Audio- und Videoaufnahmen per Drag-and-Drop hochladen, automatisch transkribieren und mit GPT-4o strukturiert zusammenfassen lassen.

Keine Installation, kein technisches Wissen nötig — läuft im Browser. Login-geschützt, bcrypt-gehashte Passwörter, keine Selbstregistrierung.

## Features

- **Transkription** via OpenAI `gpt-4o-transcribe` (optional mit Sprecher-Labels über `gpt-4o-transcribe-diarize`)
- **Zeitstempel** optional einblendbar
- **Sprache**: Auto-Detect oder fest Deutsch / Englisch
- **Prompt-Vorlagen** (Meeting-Protokoll, Zusammenfassung, Aufgabenliste, Interview-Auswertung) oder eigener Prompt
- **Lange Dateien**: automatisches Chunking (bis 500 MB Upload, siehe [Limits](#limits--hardware))
- **Job-Queue** mit SQLite-Persistenz — Jobs überleben Reloads und Restarts
- **History pro User** in der Sidebar mit Such- und Download-Funktion

Mehr Details zur internen Pipeline: siehe [ARCHITECTURE.md](ARCHITECTURE.md).

## Stack

Python 3.11 · Streamlit · streamlit-authenticator · OpenAI SDK · FFmpeg · SQLite · Docker

## Lokale Entwicklung

**Voraussetzungen:** Python 3.11, FFmpeg im `PATH`, OpenAI API Key.

```bash
# Repo klonen und ins Verzeichnis wechseln
git clone <repo-url> audiomind && cd audiomind

# Virtual Environment anlegen
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Config-Dateien anlegen
cp .env.example .env              # dann OPENAI_API_KEY eintragen
cp config.yaml.example config.yaml # dann User anlegen (siehe unten)

# App starten
streamlit run app.py
```

Die App läuft dann auf http://localhost:8501.

## Docker

```bash
docker build -t audiomind:latest .

docker run -d --name audiomind \
  -p 8501:8501 \
  -e OPENAI_API_KEY=sk-... \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/data:/app/data \
  audiomind:latest
```

Für Coolify/Production-Deployment siehe [deployment.md](deployment.md).

## Benutzer verwalten

AudioMind hat **keine Selbstregistrierung** — alle User werden per `config.yaml` gepflegt. Die Datei liegt in Production als gemountetes Volume auf dem Server, Änderungen werden ohne Rebuild übernommen.

### Neuen User hinzufügen

**1. Passwort-Hash lokal generieren** (mit aktivem `.venv`):

```bash
.venv/Scripts/python -c "import bcrypt; print(bcrypt.hashpw(b'DEIN_PASSWORT', bcrypt.gensalt()).decode())"
```

Output sieht aus wie: `$2b$12$abcdefghijklmnop...`

**2. `config.yaml` auf dem Server öffnen:**

```bash
ssh user@dein-server
nano /data/audiomind/config.yaml
```

**3. Neuen User-Block unter `credentials.usernames` eintragen:**

```yaml
credentials:
  usernames:
    anna.schmidt:                 # Login-Username (Kleinschreibung empfohlen)
      email: anna@firma.de
      failed_login_attempts: 0
      first_name: Anna
      last_name: Schmidt
      logged_in: false
      password: $2b$12$...        # den generierten Hash hier einfügen
      roles:
        - user
```

**4. Speichern — fertig.** Kein Restart, kein Rebuild. Der User kann sich sofort einloggen.

### Passwort zurücksetzen

Neuen Hash generieren (Schritt 1), das `password`-Feld des betroffenen Users in `config.yaml` ersetzen, speichern.

### User deaktivieren

Den User-Block in `config.yaml` entfernen (oder auskommentieren). Laufende Sessions mit gültigem Cookie bleiben bis zum Cookie-Ablauf aktiv (Standard: 30 Tage, konfigurierbar unter `cookie.expiry_days`).

## Limits & Hardware

| Limit | Wert | Quelle |
|---|---|---|
| Max. Upload | **500 MB** | `.streamlit/config.toml` und `MAX_UPLOAD_SIZE_MB` |
| Max. Dateigröße OpenAI-API | 25 MB | OpenAI-Limit — größere Dateien werden vorher komprimiert/gechunkt |
| Chunk-Länge | 20 Min mit 5 s Overlap | `MAX_CHUNK_DURATION_SEC`, `CHUNK_OVERLAP_SEC` |
| Erlaubte Formate | `mp3`, `mp4`, `m4a`, `wav`, `webm`, `ogg`, `flac` | `ALLOWED_FORMATS` |

### Was passiert bei einem 400 MB Video?

1. **Upload** durch Streamlit (500-MB-Grenze → 400 MB geht durch).
2. **Persistieren** in `uploads/` auf dem Volume.
3. **Worker** liest die Datei als Bytes (~400 MB **RAM-Spitze**).
4. **FFmpeg** entfernt die Videospur (`-vn`), konvertiert zu Mono-MP3 bei 16 kHz (bzw. 24 kHz mit Diarization) und splittet in 20-Min-Chunks à ≤ 25 MB.
5. **Transkription**: jeder Chunk einzeln an OpenAI — Fortschritt „Chunk X/Y" in der UI.
6. **Zusammenfassung**: gesamtes Transkript an `gpt-4o`.
7. **Aufräumen** (siehe unten).

**Faustregel Hardware:**

- **RAM**: ≥ 2 GB frei (Worst-Case: Upload-Bytes in RAM + FFmpeg-Puffer + OpenAI-Client). Der Coolify-Server sollte mindestens 2 GB RAM haben, 4 GB ist komfortabel.
- **Disk**: ~2× Dateigröße frei während der Verarbeitung (Original + Chunks im Temp). Für 400 MB Upload also ~1 GB Puffer einplanen.
- **CPU**: FFmpeg-Komprimierung von 400 MB Video dauert je nach CPU 1–5 Min; ein moderner VPS mit 2 vCPUs reicht locker. Die Transkription selbst läuft auf OpenAI-Seite, also API-bound statt CPU-bound.

Ein 400 MB Video mit z.B. 90 Minuten Laufzeit ergibt typischerweise 5–6 Chunks und dauert ca. 3–8 Minuten Gesamtzeit (stark abhängig von OpenAI-Antwortzeit).

### Wann wird die Datei gelöscht?

| Artefakt | Ort | Wann gelöscht? |
|---|---|---|
| Original-Upload | `uploads/{uuid}.ext` | **Nach erfolgreicher Verarbeitung** automatisch |
| Original-Upload (bei Fehler) | `uploads/{uuid}.ext` | **Bleibt** bis zum Retry oder bis der User den Job löscht |
| Temp-Chunks (komprimierte MP3s) | `/tmp/audiomind_*/` | **Immer** nach Job-Ende (auch bei Fehler) |
| Transkript + Zusammenfassung | SQLite `jobs`-Tabelle | Bleibt, bis der User den Job über die Sidebar löscht |

## Projektstruktur

```
audiomind/
├── app.py                 # Entry-Point: Auth, Routing, UI-Orchestration
├── auth.py                # streamlit-authenticator Wrapper
├── config.py              # Env-Validierung + Konstanten
├── config.yaml            # User-Credentials (nicht im Git)
├── prompts/               # Prompt-Templates mit {transcript}, {language}, {speaker_count}
├── services/
│   ├── audio_processing.py # FFmpeg: Validierung, Komprimierung, Chunking
│   ├── transcription.py    # OpenAI Transcription + Diarization
│   ├── summarization.py    # GPT-4o Summarization
│   ├── database.py         # SQLite Job-Queue
│   ├── worker.py           # Background-Thread: verarbeitet queued Jobs
│   └── errors.py           # Domänen-Exceptions
├── ui/
│   ├── upload.py          # Upload + Optionen + Prompt-Auswahl
│   ├── output.py          # Ergebnis-Tabs, Suche, Downloads
│   └── sidebar.py         # History-Liste pro User
├── Dockerfile
├── requirements.txt
├── ARCHITECTURE.md        # Pipeline + Flow-Details
└── deployment.md          # Coolify-Deployment
```

## Links

- [ARCHITECTURE.md](ARCHITECTURE.md) — Pipeline, Datenfluss, Design-Entscheidungen
- [deployment.md](deployment.md) — Coolify-Deployment, Volumes, Domain
- [docs/future-improvements.md](docs/future-improvements.md) — Roadmap
