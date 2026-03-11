"""Background Worker: Verarbeitet Jobs aus der Queue in einem Daemon-Thread."""

import logging
import os
import threading
import time

from services.database import (
    complete_job,
    fail_job,
    get_next_queued_job,
    update_job_progress_percent,
    update_job_status,
)

logger = logging.getLogger(__name__)

_worker_started = threading.Event()


def start_worker() -> None:
    """Startet den Worker-Thread (nur einmal). Setzt stale Jobs zurück."""
    if _worker_started.is_set():
        return
    _worker_started.set()
    _recover_stale_jobs()
    thread = threading.Thread(target=_worker_loop, daemon=True)
    thread.start()
    logger.info("Background worker gestartet.")


def _recover_stale_jobs() -> None:
    """Setzt Jobs zurück, die beim letzten Shutdown in Bearbeitung waren."""
    from services.database import _get_connection
    conn = _get_connection()
    result = conn.execute(
        """UPDATE jobs SET status = 'queued', progress_percent = 0.0, progress = NULL
           WHERE status IN ('compressing', 'transcribing', 'summarizing')""",
    )
    conn.commit()
    if result.rowcount > 0:
        logger.info(f"{result.rowcount} stale Job(s) zurückgesetzt.")


def _worker_loop() -> None:
    """Endlosschleife: Pollt nach queued Jobs und verarbeitet sie."""
    while True:
        try:
            job = get_next_queued_job()
            if job:
                _process_job(job)
            else:
                time.sleep(2)
        except Exception as e:
            logger.error(f"Worker-Loop Fehler: {e}", exc_info=True)
            time.sleep(5)


def _process_job(job: dict) -> None:
    """Verarbeitet einen einzelnen Job durch die komplette Pipeline."""
    from services.audio_processing import cleanup_temp_dir, process_upload
    from services.summarization import summarize
    from services.transcription import format_diarized_transcript, transcribe_chunks

    job_id = job["id"]
    upload_path = job["upload_path"]
    temp_dir = None

    try:
        # Schritt 1: Komprimierung
        update_job_status(job_id, "compressing", "Datei wird komprimiert...")
        update_job_progress_percent(job_id, 0.0)

        with open(upload_path, "rb") as f:
            file_bytes = f.read()

        chunk_paths = process_upload(job["filename"], file_bytes, diarize=bool(job["diarize"]))
        temp_dir = str(__import__("pathlib").Path(chunk_paths[0]).parent)

        # Schritt 2: Transkription
        update_job_status(job_id, "transcribing", "Transkription läuft...")
        update_job_progress_percent(job_id, 0.1)

        total_chunks = len(chunk_paths)

        def progress_callback(current, total):
            percent = 0.1 + (current / total) * 0.7  # 0.1 bis 0.8
            update_job_progress_percent(job_id, percent)
            update_job_status(
                job_id, "transcribing",
                f"Transkription läuft... ({current}/{total} Chunks)",
            )

        language = job["language"]  # None = auto-detect
        diarize = bool(job["diarize"])
        timestamps = bool(job["timestamps"])

        result = transcribe_chunks(
            chunk_paths,
            diarize=diarize,
            language=language,
            progress_callback=progress_callback,
        )

        # Transkript formatieren
        if diarize and "segments" in result:
            transcript_text = format_diarized_transcript(
                result["segments"], timestamps=timestamps,
            )
        else:
            transcript_text = result["text"]

        # Schritt 3: Zusammenfassung
        update_job_status(job_id, "summarizing", "Zusammenfassung wird erstellt...")
        update_job_progress_percent(job_id, 0.8)

        template_name = job["template_name"]
        custom_prompt = job["custom_prompt"]

        summary_text = summarize(
            transcript=result["text"],
            template_name=template_name,
            custom_prompt=custom_prompt,
            speaker_count=result.get("speaker_count"),
        )

        # Abschluss
        complete_job(job_id, transcript_text, summary_text)
        logger.info(f"Job {job_id} erfolgreich abgeschlossen.")

    except Exception as e:
        logger.error(f"Job {job_id} fehlgeschlagen: {e}", exc_info=True)
        fail_job(job_id, str(e))

    finally:
        # Temp-Dateien aufräumen
        if temp_dir:
            cleanup_temp_dir(temp_dir)
        # Upload-Datei nur bei erfolgreichem Job löschen (bei failed bleibt sie für Retry)
        from services.database import get_job as _get_job
        current = _get_job(job_id)
        if current and current["status"] == "completed":
            if upload_path and os.path.exists(upload_path):
                try:
                    os.remove(upload_path)
                except OSError:
                    pass
