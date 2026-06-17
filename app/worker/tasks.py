import os
import json
import uuid
import yt_dlp
import subprocess
from celery import Celery
from database.database import update_job_status, update_chunk_status
from services import transcribe, translate
from core.config import TRANSLATIONS_DIR, TRANSCRIPTIONS_DIR, AUDIOS_DIR, CHUNKS_DIR
from worker.ai_models import get_whisper, get_tokenizer, get_nllb
from database.database import create_chunk_records
from database.database import get_chunk_statuses
from database.database import get_chunk_srt_paths

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))

CHUNK_DURATION = 240 
CHUNKING_THRESHOLD = 300 


# ─── helpers ────────────────────────────────────────────────────────────────

def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def get_audio_duration(audio_path: str) -> float:
    """Return duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def split_audio_into_chunks(audio_path: str) -> list[dict]:
    """
    Split audio_path into CHUNK_DURATION-second mp3 files.
    Returns list of {"chunk_id": str, "path": str, "offset": float, "index": int}.
    """
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    duration = get_audio_duration(audio_path)
    chunks = []
    index = 0
    offset = 0.0

    while offset < duration:
        chunk_id = str(uuid.uuid4())
        chunk_path = os.path.join(CHUNKS_DIR, f"{chunk_id}.mp3")

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", audio_path,
                "-ss", str(offset),
                "-t", str(CHUNK_DURATION),
                "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
                chunk_path,
            ],
            check=True, capture_output=True,
        )

        chunks.append({
            "chunk_id": chunk_id,
            "path": chunk_path,
            "offset": offset,
            "index": index,
        })
        offset += CHUNK_DURATION
        index += 1

    return chunks


# ─── stage 1: extract audio ─────────────────────────────────────────────────

@celery_app.task(queue='audio_extraction_queue')
def extract_audio_task(input_source, job_id, target_lang):
    audio_output_path = os.path.join(AUDIOS_DIR, f"{job_id}.mp3")

    update_job_status(job_id, status="EXTRACTING_AUDIO")

    try:
        if not os.path.exists(audio_output_path):
            is_youtube = "youtube.com" in input_source or "youtu.be" in input_source

            if is_youtube:
                ydl_opts = {
                    'format': 'bestaudio/bestaudio*/best',
                    'outtmpl': os.path.join(AUDIOS_DIR, str(job_id)),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'cookiefile': '/app/cookies.txt',
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([input_source])
            else:
                command = [
                    "ffmpeg", "-i", input_source,
                    "-vn", "-acodec", "libmp3lame",
                    "-ar", "16000", "-ac", "1",
                    "-y", audio_output_path,
                ]
                subprocess.run(command, check=True, capture_output=True)

        if not os.path.exists(audio_output_path):
            raise FileNotFoundError(f"Audio not created at {audio_output_path}")

        update_job_status(job_id, status="AUDIO_EXTRACTED", audio_path=audio_output_path)
        duration = get_audio_duration(audio_output_path)

        if duration <= CHUNKING_THRESHOLD:
            # Short video — single pipeline, no chunking overhead
            chunk_id = str(uuid.uuid4())   # ← give it a proper chunk_id
            create_chunk_records(job_id, [{"chunk_id": chunk_id, "index": 0, "offset": 0.0}])
            update_job_status(job_id, status="TRANSCRIBING", total_chunks=1)
            transcribe_chunk_task.delay(
                audio_output_path,
                job_id,
                chunk_id,    # ← chunk_id
                0,           # ← chunk_index
                0.0,         # ← time_offset (no split, so 0)
                target_lang,
            )
        else:
            # Long video — split and fan out
            chunks = split_audio_into_chunks(audio_output_path)
            create_chunk_records(job_id, [{"chunk_id": c["chunk_id"], "index": c["index"], "offset": c["offset"]} for c in chunks])
            update_job_status(job_id, status="TRANSCRIBING", total_chunks=len(chunks))
            for chunk in chunks:
                transcribe_chunk_task.delay(
                    chunk["path"], job_id, chunk["chunk_id"],
                    chunk["index"], chunk["offset"], target_lang,
                )

    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=f"Extraction Error: {str(e)}")
        raise

# ─── stage 2: transcribe one chunk ──────────────────────────────────────────

@celery_app.task(queue='transcription_queue', bind=True, max_retries=3, default_retry_delay=30)
def transcribe_chunk_task(self, chunk_audio_path, job_id, chunk_id, chunk_index, time_offset, target_lang):
    try:
        transcription_path = os.path.join(TRANSCRIPTIONS_DIR, f"{chunk_id}_transcrip.json")

        detected_language = None
        if not os.path.exists(transcription_path):
            detected_language = transcribe.transcribe_audio(chunk_audio_path, chunk_id, get_whisper())
            update_job_status(job_id, source_language=detected_language)

        update_job_status(job_id, status="TRANSLATING")
        translate_chunk_task.delay(job_id, chunk_id, chunk_index, time_offset, target_lang, detected_language)
        # Audio file is no longer needed once transcription is dispatched
        _cleanup_chunk_files(chunk_audio_path)

    except Exception as e:
        update_chunk_status(chunk_id, status="FAILED", error_log=str(e))
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            update_job_status(job_id, status="FAILED", error_log=f"Chunk {chunk_index} transcription failed after retries: {str(e)}")
            raise


# ─── stage 3: translate one chunk ───────────────────────────────────────────

@celery_app.task(queue='translation_queue', bind=True, max_retries=3, default_retry_delay=30)
def translate_chunk_task(self, job_id, chunk_id, chunk_index, time_offset, target_lang, source_lang=None):
    try:
        transcription_path = os.path.join(TRANSCRIPTIONS_DIR, f"{chunk_id}_transcrip.json")
        with open(transcription_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        translated_texts = translate.translate_segments(
            segments, target_lang, get_tokenizer(), get_nllb(), source_lang
        )

        # Build SRT with timestamps shifted by time_offset
        srt_content = ""
        global_index = chunk_index * 1000  # avoids collisions across chunks when merging
        for i, (segment, translation) in enumerate(zip(segments, translated_texts), start=1):
            start_abs = segment['start'] + time_offset
            end_abs = segment['end'] + time_offset
            srt_content += f"{global_index + i}\n"
            srt_content += f"{format_srt_time(start_abs)} --> {format_srt_time(end_abs)}\n"
            srt_content += f"{translation.strip()}\n\n"

        srt_path = os.path.join(TRANSLATIONS_DIR, f"{chunk_id}_res.srt")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        update_chunk_status(chunk_id, status="COMPLETED", srt_path=srt_path)
        # Transcription JSON is no longer needed once translation is written
        _cleanup_chunk_files(transcription_path)
        _maybe_complete_job(job_id)

    except Exception as e:
        update_chunk_status(chunk_id, status="FAILED", error_log=str(e))
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            update_job_status(job_id, status="FAILED", error_log=f"Chunk {chunk_index} translation failed after retries: {str(e)}")
            raise


def _cleanup_chunk_files(*paths: str):
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"[CLEANUP] Could not remove {path}: {e}")


def _merge_chunk_srts(job_id: str) -> str:
    """Concatenate every chunk's SRT (in order) into one file for the whole video."""
    merged_path = os.path.join(TRANSLATIONS_DIR, f"{job_id}_final.srt")
    with open(merged_path, "w", encoding="utf-8") as out_file:
        for chunk_srt_path in get_chunk_srt_paths(job_id):
            if os.path.exists(chunk_srt_path):
                with open(chunk_srt_path, "r", encoding="utf-8") as in_file:
                    out_file.write(in_file.read())
    return merged_path


def _maybe_complete_job(job_id: str):
    statuses = get_chunk_statuses(job_id)
    if statuses and all(s == "COMPLETED" for s in statuses):
        merged_srt_path = _merge_chunk_srts(job_id)
        update_job_status(job_id, status="COMPLETED", srt_path=merged_srt_path)