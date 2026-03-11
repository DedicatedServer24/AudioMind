"""Audio-Verarbeitung: Validierung, FFmpeg-Komprimierung und Chunking."""

import os
import subprocess
import tempfile
from pathlib import Path

from config import (
    ALLOWED_FORMATS,
    CHUNK_OVERLAP_SEC,
    MAX_API_FILE_SIZE_MB,
    MAX_CHUNK_DURATION_SEC,
    MAX_UPLOAD_SIZE_MB,
)
from services.errors import CompressionError, FileValidationError


def validate_file(file_name: str, file_size_bytes: int) -> None:
    """Prüft Dateiformat und -größe.

    Args:
        file_name: Name der hochgeladenen Datei.
        file_size_bytes: Dateigröße in Bytes.

    Raises:
        FileValidationError: Bei ungültigem Format oder Überschreitung der Größe.
    """
    extension = Path(file_name).suffix.lstrip(".").lower()
    if extension not in ALLOWED_FORMATS:
        raise FileValidationError(
            f"Ungültiges Format: .{extension}. "
            f"Erlaubt: {', '.join(ALLOWED_FORMATS)}"
        )

    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size_bytes > max_bytes:
        raise FileValidationError(
            f"Datei zu groß: {file_size_bytes / 1024 / 1024:.1f} MB. "
            f"Maximum: {MAX_UPLOAD_SIZE_MB} MB."
        )


def get_audio_duration(file_path: str) -> float:
    """Ermittelt die Dauer einer Audiodatei in Sekunden via ffprobe.

    Raises:
        CompressionError: Falls ffprobe fehlschlägt.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise CompressionError(f"ffprobe Fehler: {result.stderr.strip()}")
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError) as e:
        raise CompressionError(f"Audio-Dauer konnte nicht ermittelt werden: {e}")


def compress_audio(input_path: str, output_path: str, target_size_mb: int = MAX_API_FILE_SIZE_MB, diarize: bool = False) -> str:
    """Komprimiert eine Audiodatei mit FFmpeg auf die Zielgröße.

    Konvertiert zu Mono-MP3 mit angepasster Bitrate.
    Bei diarize=True wird schonender komprimiert (höhere Sample-Rate und Bitrate).

    Returns:
        Pfad zur komprimierten Datei.

    Raises:
        CompressionError: Falls FFmpeg fehlschlägt.
    """
    duration = get_audio_duration(input_path)
    if duration <= 0:
        raise CompressionError("Audio-Dauer ist 0 oder ungültig.")

    # Ziel-Bitrate berechnen: target_size_mb * 8000 kbit / duration_sec, mit Sicherheitspuffer
    target_bitrate_kbps = int((target_size_mb * 8000 * 0.9) / duration)
    min_bitrate = 64 if diarize else 32
    max_bitrate = 192 if diarize else 128
    sample_rate = "24000" if diarize else "16000"
    target_bitrate_kbps = max(min_bitrate, min(target_bitrate_kbps, max_bitrate))

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-vn",  # Video-Stream entfernen
                "-ac", "1",  # Mono
                "-ar", sample_rate,
                "-b:a", f"{target_bitrate_kbps}k",
                "-y",  # Überschreiben ohne Nachfrage
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise CompressionError(f"FFmpeg Komprimierung fehlgeschlagen: {result.stderr.strip()}")
        return output_path
    except subprocess.TimeoutExpired:
        raise CompressionError("FFmpeg Timeout bei der Komprimierung.")


def split_audio(input_path: str, temp_dir: str, diarize: bool = False) -> list[str]:
    """Splittet eine Audiodatei in Chunks von max. MAX_CHUNK_DURATION_SEC Sekunden.

    Bei kurzen Dateien (<= MAX_CHUNK_DURATION_SEC) wird nur komprimiert.
    Chunks haben einen Overlap von CHUNK_OVERLAP_SEC Sekunden.
    Bei diarize=True wird schonender komprimiert.

    Returns:
        Liste der Pfade zu den Chunk-Dateien.

    Raises:
        CompressionError: Falls FFmpeg fehlschlägt.
    """
    duration = get_audio_duration(input_path)

    if duration <= MAX_CHUNK_DURATION_SEC:
        # Kurze Datei: nur komprimieren
        output_path = os.path.join(temp_dir, "chunk_000.mp3")
        compress_audio(input_path, output_path, diarize=diarize)
        return [output_path]

    # Lange Datei: in Chunks splitten
    chunks = []
    chunk_index = 0
    start_time = 0.0
    sample_rate = "24000" if diarize else "16000"
    chunk_bitrate = "96k" if diarize else "64k"

    while start_time < duration:
        output_path = os.path.join(temp_dir, f"chunk_{chunk_index:03d}.mp3")
        chunk_duration = min(MAX_CHUNK_DURATION_SEC, duration - start_time)

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i", input_path,
                    "-ss", str(start_time),
                    "-t", str(chunk_duration),
                    "-vn",
                    "-ac", "1",
                    "-ar", sample_rate,
                    "-b:a", chunk_bitrate,
                    "-y",
                    output_path,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                raise CompressionError(
                    f"FFmpeg Split fehlgeschlagen bei Chunk {chunk_index}: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise CompressionError(f"FFmpeg Timeout bei Chunk {chunk_index}.")

        # Prüfen ob Chunk zu groß ist und ggf. nachkomprimieren
        chunk_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        if chunk_size_mb > MAX_API_FILE_SIZE_MB:
            compressed_path = os.path.join(temp_dir, f"chunk_{chunk_index:03d}_compressed.mp3")
            compress_audio(output_path, compressed_path, diarize=diarize)
            os.remove(output_path)
            os.rename(compressed_path, output_path)

        chunks.append(output_path)
        chunk_index += 1
        start_time += MAX_CHUNK_DURATION_SEC - CHUNK_OVERLAP_SEC

    return chunks


def process_upload(file_name: str, file_bytes: bytes, diarize: bool = False) -> list[str]:
    """Hauptfunktion: Validiert, speichert und verarbeitet eine hochgeladene Datei.

    Gibt eine Liste von Chunk-Pfaden zurück, die für die Transkription bereit sind.
    Der Aufrufer muss das temp_dir anschließend selbst aufräumen (liegt im übergeordneten
    Verzeichnis der zurückgegebenen Chunks).

    Returns:
        Liste der Pfade zu den verarbeiteten Audio-Chunks.

    Raises:
        FileValidationError: Bei ungültigem Format/Größe.
        CompressionError: Bei FFmpeg-Fehlern.
    """
    validate_file(file_name, len(file_bytes))

    # Temp-Verzeichnis erstellen
    temp_dir = tempfile.mkdtemp(prefix="audiomind_")
    extension = Path(file_name).suffix
    input_path = os.path.join(temp_dir, f"upload{extension}")

    try:
        # Upload-Datei speichern
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        # Audio splitten und komprimieren
        chunks = split_audio(input_path, temp_dir, diarize=diarize)

        # Original-Upload löschen (Chunks bleiben)
        if os.path.exists(input_path):
            os.remove(input_path)

        return chunks

    except Exception:
        # Bei Fehler: temp_dir aufräumen
        cleanup_temp_dir(temp_dir)
        raise


def cleanup_temp_dir(temp_dir: str) -> None:
    """Räumt ein temporäres Verzeichnis mit allen Dateien auf."""
    if not temp_dir or not os.path.exists(temp_dir):
        return
    for file in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, file)
        if os.path.isfile(file_path):
            os.remove(file_path)
    os.rmdir(temp_dir)
