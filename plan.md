# Implementation Plan: Background Processing + User History

## Phase 1 — Database Layer (`services/database.py`) ✅ IMPLEMENTED

- Create `services/database.py` with SQLite connection management
- DB path: configurable via env var `AUDIOMIND_DB_PATH`, default `audiomind.db` in project root
- `init_db()`: create `jobs` table if not exists
- `create_job(username, filename, diarize, timestamps, language, template_name, custom_prompt, upload_path) -> job_id`: insert new job with status `queued`
- `get_job(job_id) -> dict`: fetch single job by ID
- `get_jobs_by_user(username) -> list[dict]`: all jobs for a user, newest first
- `update_job_status(job_id, status, progress=None)`: update status and optional progress text
- `update_job_progress_percent(job_id, percent)`: update numeric progress (0.0-1.0)
- `complete_job(job_id, transcript, summary)`: set status=completed, store results, set completed_at
- `fail_job(job_id, error_message)`: set status=failed, store error
- `delete_job(job_id, username)`: delete a single job (only if owned by user, not in-progress)
- `delete_all_jobs(username)`: delete all completed/failed jobs for a user
- `get_next_queued_job() -> dict | None`: get oldest queued job (for worker)
- Add `progress_percent` REAL column (0.0-1.0) to jobs table for progress bar
- Add `language` TEXT column (nullable, null = auto-detect)
- Thread-safe: use `check_same_thread=False` on connection

**Checkpoint:** Can import database.py, call init_db(), create/read/update/delete jobs in a Python shell.

---

## Phase 2 — Background Worker (`services/worker.py`) ✅ IMPLEMENTED

- Create `services/worker.py`
- `start_worker()`: starts a daemon thread that runs `_worker_loop()`
- `_worker_loop()`: infinite loop — poll `get_next_queued_job()`, process it, sleep 2s if idle
- `_process_job(job)`: runs the full pipeline for one job:
  1. Update status to `compressing`, progress_percent=0.0
  2. Call `process_upload()` with the saved file bytes from upload_path
  3. Update status to `transcribing`, progress_percent=0.1
  4. Call `transcribe_chunks()` with language param and a progress_callback that updates progress_percent (0.1-0.8 range)
  5. Format transcript (diarized or plain, with/without timestamps)
  6. Update status to `summarizing`, progress_percent=0.8
  7. Call `summarize()` with the transcript and template/prompt
  8. Call `complete_job()` with transcript + summary, progress_percent=1.0
  9. Clean up temp files + uploaded file
- Error handling: catch all exceptions, call `fail_job()`, clean up temp files
- Use a flag/Event to prevent multiple worker threads from starting

**Checkpoint:** Start worker in a test script, insert a queued job manually, verify it gets processed end-to-end and results appear in DB.

---

## Phase 3 — Upload Flow Refactor (`ui/upload.py`) ✅ IMPLEMENTED

- Add **language selector** to `render_upload_section()`:
  - `st.selectbox` with options: "Auto-Detect", "Deutsch", "English"
  - Maps to `None`, `"de"`, `"en"` (ISO-639-1)
  - Add to the options row as a third column (diarize, timestamps, language)
  - Store in `st.session_state["language"]`
- Change `render_process_button()`:
  - On click: save uploaded file to a persistent upload directory
  - Insert job into DB via `create_job()` (including language)
  - Show `st.success("Job eingereiht")`
  - Do NOT process inline anymore — remove all inline processing logic
  - Store the upload file bytes at `/tmp/audiomind_uploads/{job_id}{extension}`
- Remove the `st.status()` progress block (worker handles processing now)

**Checkpoint:** Upload a file, verify job appears in DB with status `queued` and correct language, verify file is saved to upload directory.

---

## Phase 4 — Sidebar History (`ui/sidebar.py`) ✅ IMPLEMENTED

- Create `ui/sidebar.py`
- `render_sidebar_history(username)`:
  - Fetch all jobs for user via `get_jobs_by_user()`
  - For each job, render a clickable entry:
    - Filename (truncated if long)
    - Date (formatted)
    - Status badge: color-coded (blue=queued, orange=processing, green=completed, red=failed)
  - For in-progress jobs: show `st.progress()` bar using `progress_percent`
  - On click: set `st.session_state["selected_job_id"]` and trigger rerun
  - Delete button (icon) per completed/failed entry
  - "Alle loschen" button at the bottom
- Auto-refresh: use `st.rerun()` triggered by a short `streamlit-autorefresh` interval (3-5 seconds) while any job is queued/processing

**Checkpoint:** Sidebar shows job list, status badges update, clicking a job sets session state, delete works.

---

## Phase 5 — Main Area: History View + Output Integration ✅ IMPLEMENTED

- Modify `app.py`:
  - Call `init_db()` at startup
  - Call `start_worker()` at startup (only once, use a guard)
  - Render sidebar history after auth
  - If `selected_job_id` in session state: show that job's results instead of upload form
- When viewing a selected job:
  - If status is `completed`: show transcript + summary using existing `render_output_section()` (adapt to accept data as params instead of reading from session state)
  - If status is `failed`: show error message with "Nochmal versuchen" button (re-queues the job with same params)
  - If status is `queued`/processing: show progress bar + status text
  - "Zuruck" button to return to upload view (clears `selected_job_id`)
- Refactor `ui/output.py` `render_output_section()` to accept transcript, summary, and filename as parameters (instead of only reading from session state)

**Checkpoint:** Full flow works: upload -> job queued -> worker processes -> sidebar updates -> click job -> see results. Refresh page -> results still there. Log out, log back in -> history preserved.

---

## Phase 6 — UI Polish ✅ IMPLEMENTED

- Switch `layout="centered"` to `layout="wide"` in `app.py`
- Group upload section with `st.container(border=True)` for visual separation
- Compact options row: 3 columns (diarize toggle, timestamps toggle, language select)
- Better upload confirmation: replace `st.caption` with `st.info` showing filename + size
- Consistent output styling: use same container style for both transcript and summary tabs
- **Download filenames**: use pattern `transkript_YYYY-MM-DD_originalname.txt` and `zusammenfassung_YYYY-MM-DD_originalname.txt`
  - `originalname` = uploaded filename without extension, sanitized (lowercase, spaces to hyphens)
  - Example: Upload "App Meeting.mp4" on 2026-03-11 -> `transkript_2026-03-11_app-meeting.txt`
- **Retry failed jobs**: "Nochmal versuchen" button on failed jobs creates a new job with same parameters
- Add `streamlit-autorefresh` to requirements.txt
- While any job for the current user is `queued` or processing: auto-refresh every 3 seconds
- When no jobs are active: disable auto-refresh (no unnecessary reruns)

**Checkpoint:** UI looks clean and consistent, downloads have descriptive filenames, retry works, auto-refresh is smooth.

---

## Phase 7 — Edge Cases & Robustness ✅ IMPLEMENTED

- Test edge cases:
  - Multiple jobs queued by same user
  - Multiple users submitting jobs
  - Refresh during processing
  - Delete while processing (should be prevented)
  - Worker crash recovery (job stays in processing state — consider a stale job timeout)
- Add `audiomind.db` to `.gitignore`

**Checkpoint:** All edge cases handled gracefully.

---

## Phase 8 — Docker & Deployment Updates ✅ IMPLEMENTED

- Update `.dockerignore` if needed
- Update `deployment.md`: add volume mount for SQLite DB (`/data/audiomind/audiomind.db:/app/audiomind.db`)
- Update `config.py`: add `DB_PATH` constant from env var
- Test full Docker build + run with the new features
- Verify volume persistence: restart container, history still there

**Checkpoint:** Docker container runs with persistent DB. Redeploy preserves all history data.
