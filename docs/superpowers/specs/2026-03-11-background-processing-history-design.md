# Design: Background Processing + User History

## Problem

- Streamlit re-runs the entire script on every interaction, so results disappear on refresh
- Long transcriptions (2h+ files) block the UI
- No history — users can't access previous results

## Solution

A single background worker thread processes a global FIFO queue. All job metadata, status, and results are stored in SQLite. Streamlit reads from the DB on every rerun, making everything refresh-safe and persistent.

## Database (SQLite)

File location: `/data/audiomind/audiomind.db` (volume-mounted in Docker, `audiomind.db` locally for dev).

One `jobs` table:

| Column | Type | Description |
|---|---|---|
| id | TEXT (UUID) | Primary key |
| username | TEXT | Owner of the job |
| filename | TEXT | Original upload filename |
| status | TEXT | `queued`, `compressing`, `transcribing`, `summarizing`, `completed`, `failed` |
| progress | TEXT | e.g. "Chunk 3/6" or null |
| diarize | BOOLEAN | Diarization enabled |
| timestamps | BOOLEAN | Timestamps enabled |
| template_name | TEXT | Selected prompt template (nullable) |
| custom_prompt | TEXT | Custom prompt text (nullable) |
| transcript | TEXT | Result (nullable until done) |
| summary | TEXT | Result (nullable until done) |
| error_message | TEXT | Error details if failed |
| created_at | DATETIME | Job submission time |
| completed_at | DATETIME | Job completion time (nullable) |

## Background Worker

- A single daemon thread started once at app startup
- Polls the DB for the next `queued` job (ordered by `created_at`)
- Processes it through the existing pipeline: compress -> transcribe -> summarize
- Updates status + progress in the DB at each step
- On error: sets status to `failed` with error_message
- Short sleep between polls (2-3 seconds) when idle

## Upload Flow (changed)

1. User uploads file + selects options -> clicks "Zusammenfassen"
2. File bytes are saved to a persistent upload directory (not per-request tmpdir)
3. A new job row is inserted into SQLite with status `queued`
4. User sees immediate feedback: "Job eingereiht" — job appears in sidebar
5. User can upload another file immediately (new job goes to queue)

## Sidebar History

- Below logout + user info
- Shows all jobs for the current user, newest first
- Each entry: filename, date, status badge (color-coded)
- Active/processing job shows a progress bar (chunks completed / total)
- Clicking an entry loads transcript + summary in the main area
- "Delete" button per entry, "Alle loschen" button at the bottom
- Auto-refreshes every few seconds while jobs are pending

## Main Area

- Default: upload form (as today)
- When a history entry is clicked: shows transcript + summary (reuses existing output components)
- Back button to return to upload view

## File Structure (new/changed)

```
services/
  database.py          # SQLite init, job CRUD operations
  worker.py            # Background worker thread + queue processing
  audio_processing.py  # unchanged
  transcription.py     # unchanged
  summarization.py     # unchanged
  errors.py            # unchanged
ui/
  upload.py            # changed: saves to DB instead of inline processing
  output.py            # unchanged (reused for history view)
  sidebar.py           # new: history list, status badges, delete buttons
app.py                 # changed: starts worker, adds sidebar history
```

## Progress Bar Calculation

- Compression: 0-10%
- Transcription: 10% + (chunk_index / total_chunks) * 70% -> chunks span 10%-80%
- Summarization: 80%-100%

## Queue Behavior

- Global queue (not per-user): one job processed at a time across all users
- FIFO ordering by `created_at`
- Users can submit multiple jobs — they queue up and process sequentially
- Each job shows its current status in the sidebar

## Deletion

- Users can delete individual history entries (removes DB row)
- "Alle loschen" button deletes all entries for the current user
- Deletion only affects completed/failed jobs, not queued/in-progress ones
