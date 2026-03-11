# Quick Fixes & Verbesserungen – Implementierungsplan

---

## 1. Copy-to-Clipboard

Buttons zum Kopieren von Transkript und Zusammenfassung in die Zwischenablage.

**Datei:** `ui/output.py`

- [x] In `_render_transcript_tab()`: Copy-Button über dem Textbereich einfügen (neben dem Download-Button)
  - `st.button("📋 Kopieren")` mit JavaScript-Workaround via `st.components.v1.html()` (Streamlit hat kein natives Clipboard-API)
  - Alternativ: `st.code()` hat eingebauten Copy-Button — prüfen ob das für den Anwendungsfall ausreicht
- [x] In `_render_summary_tab()`: Gleichen Copy-Button einfügen
- [x] Helper-Funktion `_copy_to_clipboard(text, key)` erstellen, die ein kleines HTML/JS-Snippet rendert
- [x] Testen: Button klicken → Text ist in Zwischenablage

**Hinweis:** Streamlit hat keine native Clipboard-Unterstützung. Beste Option: kleines `st.components.v1.html()`-Snippet mit `navigator.clipboard.writeText()`. Alternativ `pyperclip` serverseitig — funktioniert aber nur lokal, nicht im Docker.

---

## 2. Retry fehlgeschlagene Jobs (Bugfix + Verbesserung)

Button in der Sidebar um fehlgeschlagene Jobs neu zu starten.

**Status:** Teilweise implementiert in `app.py:107-120`, aber **Bug**: Der Worker löscht die `upload_path`-Datei nach Verarbeitung (`worker.py:140-143`). Ein Retry mit gelöschter Datei schlägt sofort fehl.

### Bugfix

**Datei:** `app.py`

- [x] Vor dem Retry prüfen ob `upload_path` noch existiert
- [x] Falls Datei nicht mehr existiert: Fehlermeldung anzeigen ("Datei nicht mehr verfügbar. Bitte erneut hochladen.")
- [x] Upload-Datei bei fehlgeschlagenen Jobs **nicht** löschen — nur bei `completed` löschen

**Datei:** `services/worker.py`

- [x] In `_process_job()` finally-Block: Upload-Datei nur löschen wenn Job erfolgreich war (`status == completed`)
- [x] Bei `failed` Jobs: Upload-Datei behalten für Retry

### Sidebar-Retry-Button

**Datei:** `ui/sidebar.py`

- [x] In `_render_job_entry()`: Bei `status == "failed"` zusätzlich einen 🔄-Button neben dem 🗑️-Button anzeigen
- [x] Button-Logik: Neuen Job mit gleichen Parametern erstellen (wie in `app.py:109-119`), alten Job löschen
- [x] Testen: Job fehlschlagen lassen → Retry in Sidebar → Job wird neu eingereiht

---

## 3. Wortanzahl & Dauer

Wortanzahl im Transkript + geschätzte Audiodauer in der Ergebnis-Ansicht anzeigen.

**Datei:** `ui/output.py`

- [x] In `render_output_section()`: Metrik-Zeile über den Tabs einfügen mit `st.columns()` + `st.metric()`
- [x] Wortanzahl: `len(transcript.split())` — als `st.metric("Wörter", "1.234")`
- [x] Geschätzte Lesedauer: `word_count // 200` Minuten (Ø Lesegeschwindigkeit) — als `st.metric("Lesedauer", "~6 Min.")`
- [x] Zeichenanzahl: `len(transcript)` — als `st.metric("Zeichen", "12.345")`

**Datei:** `services/database.py` (optional, für Audiodauer)

- [x] Neues Feld `audio_duration_sec` in der `jobs`-Tabelle (optionales Feld, ALTER TABLE oder Migration)

**Datei:** `services/worker.py` (optional, für Audiodauer)

- [x] Nach FFmpeg-Komprimierung: Audiodauer mit `ffprobe` ermitteln und in DB speichern
- [x] Dauer in der Ergebnis-Ansicht anzeigen: `st.metric("Audiodauer", "12:34")`

**Hinweis:** Wortanzahl + Lesedauer sind sofort umsetzbar ohne DB-Änderung. Audiodauer erfordert eine DB-Migration — kann als separater Schritt gemacht werden.

---

## 4. Markdown-Export

Zusammenfassung als `.md` downloaden (Formatierung bleibt erhalten).

**Datei:** `ui/output.py`

- [x] In `_render_summary_tab()`: Zweiten Download-Button hinzufügen für `.md`-Export
- [x] Download-Dateiname: `zusammenfassung_{date}_{filename}.md` (gleiche Logik wie `.txt`)
- [x] `_generate_download_names()` erweitern: Auch `.md`-Dateinamen zurückgeben (oder separate Funktion)
- [x] Layout: Beide Download-Buttons nebeneinander in `st.columns(2)`
- [x] Testen: Download → Datei öffnet korrekt in Markdown-Editor/Viewer

**Aufwand:** Minimal — die Zusammenfassung ist bereits Markdown-formatiert, es ändert sich nur die Dateiendung und der MIME-Type (`text/markdown`).

---

## 5. Streaming-Zusammenfassung *(übersprungen — siehe docs/future-improvements.md)*

GPT-4o-Response streamen für schnelleres Feedback in der UI.

**Achtung:** Höherer Aufwand als die anderen Quick Fixes, da die aktuelle Architektur (Background-Worker + DB-Polling) nicht für Streaming ausgelegt ist. Zwei mögliche Ansätze:

### Ansatz A: Streaming in DB schreiben (einfacher)

**Datei:** `services/summarization.py`

- [x] Neue Funktion `summarize_streaming()` die `stream=True` nutzt
- [x] Chunks akkumulieren und regelmäßig (alle ~500 Zeichen) in DB schreiben

**Datei:** `services/database.py`

- [x] Neue Funktion `update_job_summary_partial(job_id, partial_summary)` — schreibt Zwischenstand

**Datei:** `services/worker.py`

- [x] In `_process_job()`: `summarize_streaming()` statt `summarize()` aufrufen
- [x] Partial-Summary während des Streamings in DB updaten

**Datei:** `app.py`

- [x] Im `job_status_fragment()`: Wenn Status `summarizing` und `summary` nicht leer → partial Summary anzeigen
- [x] Fragment pollt ohnehin alle 3s — zeigt automatisch den Zwischenstand

### Ansatz B: Direkt in UI streamen (komplexer, bessere UX)

- [x] Zusammenfassung nicht im Worker machen, sondern nach Transkription direkt im Streamlit-Thread mit `st.write_stream()`
- [x] Worker-Pipeline aufteilen: Worker macht nur Komprimierung + Transkription, Zusammenfassung wird separat getriggert
- [x] Erfordert größere Architektur-Änderung

**Empfehlung:** Ansatz A — minimale Architektur-Änderung, trotzdem Live-Feedback.

- [x] Testen: Job starten → während "Zusammenfassung wird erstellt" → Text erscheint stückweise

---

## 6. Transkript editieren

Vor der Zusammenfassung manuell korrigieren (Texteditor-Modus).

**Datei:** `ui/output.py`

- [x] In `_render_transcript_tab()`: Toggle "Transkript bearbeiten" hinzufügen
- [x] Wenn aktiv: `st.text_area()` statt read-only Anzeige, vorausgefüllt mit dem Transkript
- [x] "Änderungen übernehmen"-Button: Speichert editiertes Transkript in DB
- [x] "Neu zusammenfassen"-Button: Erstellt neue Zusammenfassung basierend auf editiertem Transkript

### Sprecher umbenennen (bei Diarization)

Wenn der Job mit Sprecher-Labels erstellt wurde, erscheinen Sprecher im Format `Speaker 1: Text`, `Speaker 2: Text` etc. Der Nutzer soll diese vor der Zusammenfassung umbenennen können.

**Datei:** `ui/output.py`

- [x] Sprecher aus dem Transkript extrahieren: Regex `^(Speaker \d+):` über alle Zeilen, unique Set sammeln
- [x] Nur anzeigen wenn Sprecher gefunden werden (= Job hatte `diarize=True`)
- [x] Pro Sprecher ein `st.text_input()` rendern, z.B.: `Speaker 1` → Eingabefeld mit Placeholder "z.B. Jan"
- [x] Layout: `st.columns(2)` — links der Original-Name, rechts das Eingabefeld
- [x] "Sprecher umbenennen"-Button: Führt String-Replace im Transkript durch (`Speaker 1:` → `Jan:`)
- [x] Reihenfolge beachten: Längste Sprechernamen zuerst ersetzen (verhindert `Speaker 10` → `JanSpeaker 0`)
- [x] Nach Umbenennung: Transkript in DB aktualisieren + Anzeige refreshen
- [x] Umbenennung und freie Textbearbeitung kombinierbar: Erst Sprecher umbenennen, dann Feinschliff im Texteditor

**Datei:** `services/database.py`

- [x] Neue Funktion `update_job_transcript(job_id, transcript)` — überschreibt gespeichertes Transkript

**Datei:** `app.py` oder `ui/output.py`

- [x] "Neu zusammenfassen"-Logik: Ruft `summarize()` direkt auf (synchron im Streamlit-Thread, da Text bereits vorliegt)
- [x] Während der Zusammenfassung: Spinner anzeigen (`with st.spinner("Zusammenfassung wird neu erstellt...")`)
- [x] Nach Abschluss: Neue Zusammenfassung in DB speichern und Ansicht aktualisieren

**Datei:** `services/database.py`

- [x] Neue Funktion `update_job_summary(job_id, summary)` — überschreibt gespeicherte Zusammenfassung

- [x] Testen: Transkript mit Sprechern → Speaker 1 zu "Jan" umbenennen → Transkript zeigt "Jan:" statt "Speaker 1:"
- [x] Testen: Umbenennen → "Neu zusammenfassen" → Zusammenfassung nutzt echte Namen
- [x] Testen: Transkript ohne Sprecher → Umbenennen-UI wird nicht angezeigt

---

## 7. Bessere Audio-Komprimierung für Diarization

Die aktuelle Komprimierung (16kHz, Mono, 32-128 kbps) ist für reine Transkription optimiert, degradiert aber Stimmmerkmale, die für Sprechertrennung wichtig sind. Wenn Diarization aktiviert ist, soll schonender komprimiert werden.

**Datei:** `services/audio_processing.py`

### `compress_audio()` (Zeile 69-109)

- [x] Parameter `diarize: bool = False` hinzufügen
- [x] Wenn `diarize=True`: Sample-Rate auf `24000` statt `16000` (bessere Stimmunterscheidung)
- [x] Wenn `diarize=True`: Mindest-Bitrate auf `64` statt `32` kbps
- [x] Wenn `diarize=True`: Max-Bitrate auf `192` statt `128` kbps
- [x] Optional: Noise Reduction Filter hinzufügen (`-af "afftdn"`) für Diarization-Jobs

Aktuell (Zeile 87):
```python
target_bitrate_kbps = max(32, min(target_bitrate_kbps, 128))
```
Neu:
```python
min_bitrate = 64 if diarize else 32
max_bitrate = 192 if diarize else 128
sample_rate = "24000" if diarize else "16000"
target_bitrate_kbps = max(min_bitrate, min(target_bitrate_kbps, max_bitrate))
```

### `split_audio()` (Zeile 112-178)

- [x] Parameter `diarize: bool = False` hinzufügen
- [x] `diarize` an `compress_audio()` durchreichen (Zeile 129)
- [x] Inline-FFmpeg-Aufruf für Chunks (Zeile 146-148): Sample-Rate und Bitrate analog anpassen
  - Aktuell hardcoded: `"-ar", "16000"` und `"-b:a", "64k"`
  - Neu: `"-ar", "24000"` und `"-b:a", "96k"` wenn `diarize=True`

### `process_upload()` (Zeile 181-219)

- [x] Parameter `diarize: bool = False` hinzufügen
- [x] `diarize` an `split_audio()` durchreichen (Zeile 208)

### Aufrufer: `services/worker.py` (Zeile 77)

- [x] `diarize`-Flag aus dem Job lesen und an `process_upload()` übergeben:
  ```python
  chunk_paths = process_upload(job["filename"], file_bytes, diarize=bool(job["diarize"]))
  ```

- [x] Testen: Job ohne Diarization → Komprimierung wie bisher (16kHz, 32-128 kbps)
- [x] Testen: Job mit Diarization → höhere Qualität (24kHz, 64-192 kbps)
- [x] Testen: Chunks bleiben unter 25 MB API-Limit auch mit höherer Bitrate

**Hinweis:** Höhere Qualität = größere Dateien = evtl. mehr Chunks. Das ist akzeptabel, da die Sprechergenauigkeit wichtiger ist als minimale Dateigröße.

---

## Empfohlene Reihenfolge

1. **Markdown-Export** — 5 Min. Aufwand, sofort Mehrwert
2. **Bessere Diarization-Komprimierung** — 10 Min., direkter Effekt auf Sprechergenauigkeit
3. **Wortanzahl & Dauer** (ohne Audiodauer) — 10 Min., reine UI-Ergänzung
4. **Copy-to-Clipboard** — 15 Min., braucht JS-Snippet
5. **Retry fehlgeschlagene Jobs** — 20 Min., inkl. Bugfix im Worker
6. **Transkript editieren + Sprecher umbenennen** — 30 Min., neue DB-Funktionen + UI-Logik
7. **Streaming-Zusammenfassung** — 45-60 Min., Ansatz A mit DB-Zwischenstand
