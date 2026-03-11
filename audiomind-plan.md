# AudioMind – Projektplan

## App-Beschreibung

**AudioMind – Automatische Transkription & Zusammenfassung**

AudioMind ist ein internes Web-Tool für Teams, das Audio- und Videoaufnahmen automatisch in Text umwandelt und strukturiert aufbereitet. Lade eine Datei hoch, konfiguriere die Optionen – und erhalte innerhalb von Minuten ein vollständiges Transkript sowie eine professionelle Zusammenfassung. Keine Installation, kein technisches Wissen nötig, läuft direkt im Browser.

---

## Kompletter Flow (eine Seite)

```
Login (streamlit-authenticator)
  → Username in st.session_state["username"] verfügbar
  ↓
Hauptseite
  ├── 1. Datei hochladen (drag & drop)
  │       ├── Max. Upload: 500 MB
  │       ├── Formate: mp3, mp4, m4a, wav, webm, ogg, flac
  │       └── Validierung: Format + Größe vor Verarbeitung prüfen
  │
  ├── 2. Optionen
  │       ├── Sprecher-Labels?        [Toggle ON/OFF]
  │       │       └── ON  → gpt-4o-transcribe-diarize
  │       │           OFF → gpt-4o-transcribe
  │       ├── Timestamps?             [Toggle ON/OFF]
  │       └── Sprache: Auto-Detect   [fix, kein UI nötig]
  │
  ├── 3. Prompt-Vorlage wählen
  │       ├── Meeting-Protokoll
  │       ├── Zusammenfassung
  │       ├── Aufgabenliste
  │       ├── Interview-Auswertung
  │       └── Eigener Prompt → Textfeld erscheint
  │
  ├── 4. Button "Zusammenfassen"
  │       └── Fortschrittsanzeige (st.status + Schritte)
  │               ├── Datei wird komprimiert...
  │               ├── Transkription läuft... (ggf. Chunk X/Y)
  │               └── Zusammenfassung wird erstellt...
  │
  └── 5. Output
          ├── Vorschau-Bereich
          │       ├── Tab 1: Transkript
          │       │       ├── Suchfeld (Treffer werden gehighlightet)
          │       │       └── Scrollbarer Textbereich
          │       └── Tab 2: Zusammenfassung
          │               └── Scrollbarer Textbereich
          │
          ├── transkript.txt      [Download-Button]
          └── zusammenfassung.txt [Download-Button]
```

---

## Vorschau & Suche – Umsetzung

- `st.tabs()` → Tab-Wechsel Transkript / Zusammenfassung
- `st.text_input()` → Suchfeld über dem Transkript
- `st.markdown()` → Text mit Highlighting (Treffer farbig markiert)
- `Python re/find()` → Suche + Trefferanzahl anzeigen ("3 Treffer gefunden")

Kein externes Package nötig, ~30–40 Zeilen Code.

---

## Modell-Logik

| Option | Modell |
|---|---|
| Sprecher-Labels AN | `gpt-4o-transcribe-diarize` (Output: `diarized_json`) |
| Sprecher-Labels AUS | `gpt-4o-transcribe` |
| Zusammenfassung | `gpt-4o` |

Hinweis: `gpt-4o-transcribe-diarize` erfordert `chunking_strategy` Parameter (z.B. `auto`).

---

## Limits & Chunking

| Limit | Wert |
|---|---|
| Max. Upload-Größe | 500 MB (Streamlit `server.maxUploadSize`) |
| Max. Dateigröße OpenAI API | 25 MB (nach FFmpeg-Komprimierung) |
| Max. Audiodauer pro Chunk | 1500 Sekunden (~25 Min) |

### Chunking-Strategie für lange Audios

1. FFmpeg komprimiert die Datei auf <25 MB pro Chunk
2. Falls Audio >20 Min: FFmpeg splittet in 20-Min-Segmente (mit 5s Overlap)
3. Jedes Segment wird einzeln an OpenAI gesendet
4. Transkripte werden in Reihenfolge zusammengefügt
5. Fortschrittsanzeige zeigt "Chunk X von Y"

---

## Authentifizierung

- **Package:** `streamlit-authenticator`
- **User-Daten:** `config.yaml` (gehashte Passwörter, als Docker-Volume mounten)
- **Session-State:** `st.session_state["username"]`, `st.session_state["name"]`
- **Mehrere Benutzer:** In `config.yaml` definiert, jeder hat eigenen Login
- **User-Kontext:** Der aktuelle Username ist in der gesamten App über Session-State verfügbar (für spätere Features wie History, Logging)

```yaml
# Beispiel config.yaml
credentials:
  usernames:
    max.mustermann:
      name: Max Mustermann
      password: $2b$12$...  # bcrypt-Hash
    anna.schmidt:
      name: Anna Schmidt
      password: $2b$12$...
```

---

## Fehlerbehandlung

### Definierte Error-Klassen (`services/errors.py`)

| Error | Auslöser | User-Meldung |
|---|---|---|
| `FileValidationError` | Ungültiges Format, Datei zu groß | "Dieses Dateiformat wird nicht unterstützt." |
| `CompressionError` | FFmpeg schlägt fehl | "Fehler bei der Audio-Komprimierung." |
| `TranscriptionError` | OpenAI API Fehler, Timeout | "Transkription fehlgeschlagen. Bitte erneut versuchen." |
| `SummarizationError` | GPT-4o Fehler, Rate-Limit | "Zusammenfassung fehlgeschlagen. Bitte erneut versuchen." |
| `ConfigError` | Fehlende Env-Vars, ungültige Config | "App-Konfiguration fehlerhaft. Admin kontaktieren." |

### Validierungs-Reihenfolge

1. **Startup:** Env-Vars prüfen (`OPENAI_API_KEY` vorhanden + Format)
2. **Upload:** Dateiformat + Größe prüfen, bevor Verarbeitung startet
3. **Komprimierung:** FFmpeg-Exit-Code prüfen
4. **API-Calls:** Try/Except mit spezifischen OpenAI-Exceptions, Retry bei Rate-Limit (max 2 Versuche)
5. **UI:** Fehler werden als `st.error()` mit verständlicher Meldung angezeigt

---

## Prompt-Templates (mit Variablen)

Templates nutzen `{variable}`-Platzhalter, die vor dem API-Call ersetzt werden.

### Verfügbare Variablen

| Variable | Beschreibung |
|---|---|
| `{transcript}` | Das vollständige Transkript |
| `{language}` | Erkannte Sprache des Audios |
| `{speaker_count}` | Anzahl erkannter Sprecher (falls Diarization) |

### Beispiel: `prompts/meeting.txt`

```
Erstelle ein strukturiertes Meeting-Protokoll aus folgendem Transkript.

Sprache des Outputs: {language}

Struktur:
- Teilnehmer (falls erkennbar)
- Besprochene Themen
- Entscheidungen
- Offene Punkte / Action Items

Transkript:
{transcript}
```

---

## Env-Validierung (`config.py`)

Beim App-Start werden geprüft:

| Variable | Prüfung |
|---|---|
| `OPENAI_API_KEY` | Vorhanden, beginnt mit `sk-` |
| `STREAMLIT_MAX_UPLOAD_SIZE` | Optional, Default: 500 |

Bei fehlender/ungültiger Konfiguration: App zeigt Fehlermeldung statt Login-Screen.

---

## Projektstruktur

```
audiomind/
├── app.py                      # Entry-Point, minimal (Login + Page-Routing)
├── config.py                   # Settings, Env-Validierung, Konstanten
├── auth.py                     # Login-Logik (streamlit-authenticator)
├── config.yaml                 # Benutzer & gehashte Passwörter
├── prompts/
│   ├── meeting.txt             # Meeting-Protokoll (mit {variable}-Platzhaltern)
│   ├── zusammenfassung.txt     # Allgemeine Zusammenfassung
│   ├── aufgaben.txt            # Aufgabenliste extrahieren
│   └── interview.txt           # Interview-Auswertung
├── ui/
│   ├── upload.py               # Upload-Bereich + Optionen-UI
│   └── output.py               # Ergebnis-Tabs, Suche, Downloads
├── services/
│   ├── errors.py               # Definierte Exception-Klassen
│   ├── transcription.py        # OpenAI Transcription + Chunking-Logik
│   ├── summarization.py        # GPT-4o Zusammenfassung
│   └── audio_processing.py     # FFmpeg Komprimierung, Validierung, Splitting
├── Dockerfile
├── requirements.txt
├── .env                        # OPENAI_API_KEY (nicht im Git!)
└── .gitignore
```

### Begründung der Struktur

- **`app.py`** → nur Entry-Point (~50 Zeilen): Login prüfen, dann UI rendern
- **`ui/`** → UI-Logik getrennt von Business-Logik
- **`services/`** → Business-Services statt generische `utils/` (klarere Semantik)
- **`services/errors.py`** → zentrale Error-Definitionen für konsistente Fehlerbehandlung
- **`config.py`** → alle Settings + Env-Validierung an einem Ort
- **Transcription und Summarization getrennt** → Single Responsibility

---

## Dockerfile (Konzept)

```
- Base: python:3.11-slim
- ffmpeg via apt installieren
- requirements installieren
- Streamlit auf Port 8501 starten
- config.yaml als Volume mounten (User-Verwaltung ohne Rebuild)
```

---

## Deployment Coolify

```
1. Privates GitHub Repo erstellen
2. OPENAI_API_KEY als Environment Variable in Coolify setzen
3. config.yaml als persistentes Volume mounten
4. New Service → Dockerfile → Port 8501
5. Domain + HTTPS aktivieren
   → https://audiomind.deinedomain.de
```

---

## Roadmap – Mittelfristig (V2)

| Feature | Beschreibung | Aufwand |
|---|---|---|
| Background-Worker | Celery/Redis für asynchrone Verarbeitung ohne UI-Blockade | hoch |
| Batch-Verarbeitung | Mehrere Dateien gleichzeitig hochladen, Ergebnisse als ZIP | mittel |
| History pro Nutzer | Letzte X Transkriptionen abrufbar (SQLite-DB) | mittel |
| Transkript editieren | Vor der Zusammenfassung manuell korrigieren | gering |
| Ergebnis per Mail | Button "An mich senden" nach Verarbeitung | gering |
| Export als PDF/DOCX | Zusätzlich zu .txt auch .pdf und .docx anbieten | mittel |
| Unit-Tests | Tests für eigene Logik: Chunking, Validierung, Template-Variablen | gering |

---

## Roadmap – Langfristig

| Feature | Beschreibung | Aufwand |
|---|---|---|
| Prompt-Bibliothek | Nutzer können eigene Prompts speichern & benennen | mittel |
| Admin-Dashboard | Nutzungsübersicht, API-Kosten im Blick, User verwalten | hoch |
| URL-Import | Direkt-Link zu Zoom/Teams/YouTube-Recording eingeben | mittel |
| Sprecher benennen | Vor Zusammenfassung "Sprecher 1" → "Max Mustermann" umbenennen | mittel |
| Mehrsprachige UI | App-Oberfläche in DE/EN umschaltbar | gering |

---

## V1 – Bewusst weggelassen

- Keine Datenbank / History
- Kein Admin-Panel
- Keine Batch-Verarbeitung
- Kein Mail-Versand
- Kein Background-Worker (kommt in V2)

---

## Umsetzungsplan V1

### Phase 1 – Fundament (Config, Errors, Auth)

Dateien: `config.py`, `services/errors.py`, `auth.py`, `config.yaml`, `.env`, `.gitignore`, `requirements.txt`

- [x] `config.py` → Env-Validierung, Konstanten (Limits, erlaubte Formate)
- [x] `services/errors.py` → alle Exception-Klassen
- [x] `auth.py` → Login/Logout mit streamlit-authenticator
- [x] `config.yaml` → Test-User anlegen
- [x] `.env` → `OPENAI_API_KEY` Platzhalter
- [x] `.gitignore` → `.env`, `.venv/`, `__pycache__/`
- [x] `requirements.txt` → alle Dependencies
- [x] `app.py` → minimaler Entry-Point: Env-Check → Login → "Willkommen {name}"

**Checkpoint:** App startet, Login funktioniert, ungültige Env-Vars zeigen Fehlermeldung.

---

### Phase 2 – Audio-Verarbeitung (FFmpeg + OpenAI Transcription)

Dateien: `services/audio_processing.py`, `services/transcription.py`

- [x] `audio_processing.py` → Datei-Validierung (Format, Größe)
- [x] `audio_processing.py` → FFmpeg-Komprimierung auf <25 MB
- [x] `audio_processing.py` → Splitting in 20-Min-Chunks bei langen Audios
- [x] `audio_processing.py` → Temp-Dateien sauber aufräumen
- [x] `transcription.py` → OpenAI API-Call mit `gpt-4o-transcribe`
- [x] `transcription.py` → Diarization mit `gpt-4o-transcribe-diarize` + `chunking_strategy`
- [x] `transcription.py` → Multi-Chunk-Transkription (Chunks einzeln senden, zusammenfügen)
- [x] `transcription.py` → Error-Handling (Retry bei Rate-Limit, spezifische Exceptions)

**Checkpoint:** Ein Audio-File kann per Python-Script transkribiert werden (mit und ohne Diarization). Chunking funktioniert für Dateien >25 Min.

---

### Phase 3 – Zusammenfassung (Prompts + GPT-4o)

Dateien: `services/summarization.py`, `prompts/*.txt`

- [x] Alle 4 Prompt-Templates mit `{variable}`-Platzhaltern erstellen
- [x] `summarization.py` → Template laden, Variablen ersetzen
- [x] `summarization.py` → GPT-4o API-Call mit befülltem Prompt
- [x] `summarization.py` → Error-Handling (Rate-Limit, Timeout)

**Checkpoint:** Transkript rein → Zusammenfassung raus. Alle 4 Templates + eigener Prompt funktionieren.

---

### Phase 4 – UI (Upload, Optionen, Output)

Dateien: `ui/upload.py`, `ui/output.py`, `app.py` erweitern

- [x] `ui/upload.py` → Datei-Upload (Drag & Drop) mit Format-/Größenvalidierung
- [x] `ui/upload.py` → Optionen (Sprecher-Labels Toggle, Timestamps Toggle)
- [x] `ui/upload.py` → Prompt-Vorlage wählen (Selectbox + Textfeld bei "Eigener Prompt")
- [x] `ui/upload.py` → "Zusammenfassen"-Button mit Fortschrittsanzeige (`st.status`)
- [x] `ui/output.py` → Tabs (Transkript / Zusammenfassung)
- [x] `ui/output.py` → Suche im Transkript mit Highlighting
- [x] `ui/output.py` → Download-Buttons (.txt)
- [x] `app.py` → Upload- und Output-Bereiche einbinden, Flow verbinden

**Checkpoint:** Kompletter Flow funktioniert im Browser: Upload → Optionen → Verarbeitung → Ergebnis mit Suche + Download.

---

### Phase 5 – Docker & Deployment

Dateien: `Dockerfile`, `.streamlit/config.toml`

- [x] `.streamlit/config.toml` → `maxUploadSize = 500`, Theme-Settings
- [x] `Dockerfile` → Build + Run konfigurieren (python:3.11-slim, ffmpeg, Port 8501)
- [x] Docker lokal testen (`docker build` + `docker run`)
- [x] Deployment-Anleitung für Coolify finalisieren

**Checkpoint:** App läuft im Docker-Container. Bereit für Coolify-Deployment.
