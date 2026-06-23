import os
import json
import uuid
import tempfile
import yt_dlp
import subprocess
from celery import Celery
from database.database import update_job_status, update_chunk_status
from services import transcribe, translate
from worker.ai_models import get_whisper, get_tokenizer, get_nllb
from database.database import create_chunk_records, get_chunk_statuses, get_chunk_srt_paths
from core import minio_client

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))

CHUNK_DURATION = 240
CHUNKING_THRESHOLD = 300


# ─── key helpers ────────────────────────────────────────────────────────────────

def _audio_key(job_id):        return f"audio/{job_id}.mp3"
def _chunk_key(chunk_id):      return f"chunks/{chunk_id}.mp3"
def _transc_key(chunk_id):     return f"transcriptions/{chunk_id}.json"
def _chunk_srt_key(chunk_id):  return f"srt/chunks/{chunk_id}.srt"
def _final_srt_key(job_id):    return f"srt/{job_id}_final.srt"


# ─── local helpers ───────────────────────────────────────────────────────────────

def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def split_audio_into_chunks(audio_path: str, workdir: str) -> list[dict]:
    duration = get_audio_duration(audio_path)
    chunks = []
    index = 0
    offset = 0.0
    while offset < duration:
        chunk_id = str(uuid.uuid4())
        chunk_path = os.path.join(workdir, f"{chunk_id}.mp3")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path,
             "-ss", str(offset), "-t", str(CHUNK_DURATION),
             "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", chunk_path],
            check=True, capture_output=True,
        )
        chunks.append({"chunk_id": chunk_id, "path": chunk_path, "offset": offset, "index": index})
        offset += CHUNK_DURATION
        index += 1
    return chunks


# ─── stage 1: extract audio ─────────────────────────────────────────────────────

@celery_app.task(queue='audio_extraction_queue')
def extract_audio_task(input_source, job_id, target_lang):
    update_job_status(job_id, status="EXTRACTING_AUDIO")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_audio = os.path.join(tmpdir, f"{job_id}.mp3")
            is_youtube = "youtube.com" in input_source or "youtu.be" in input_source

            if is_youtube:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(tmpdir, str(job_id)),
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
                # input_source is a MinIO key for the uploaded video
                ext = os.path.splitext(input_source)[1]
                local_video = os.path.join(tmpdir, f"{job_id}{ext}")
                minio_client.download_file(input_source, local_video)
                subprocess.run(
                    ["ffmpeg", "-i", local_video,
                     "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1",
                     "-y", local_audio],
                    check=True, capture_output=True,
                )
                minio_client.delete_object(input_source)

            if not os.path.exists(local_audio):
                raise FileNotFoundError(f"Audio not produced at {local_audio}")

            update_job_status(job_id, status="AUDIO_EXTRACTED")
            duration = get_audio_duration(local_audio)

            if duration <= CHUNKING_THRESHOLD:
                chunk_id = str(uuid.uuid4())
                audio_key = _audio_key(job_id)
                minio_client.upload_file(local_audio, audio_key)
                create_chunk_records(job_id, [{"chunk_id": chunk_id, "index": 0, "offset": 0.0}])
                update_job_status(job_id, status="TRANSCRIBING", total_chunks=1)
                transcribe_chunk_task.delay(audio_key, job_id, chunk_id, 0, 0.0, target_lang)
            else:
                chunks = split_audio_into_chunks(local_audio, tmpdir)
                for chunk in chunks:
                    chunk_key = _chunk_key(chunk["chunk_id"])
                    minio_client.upload_file(chunk["path"], chunk_key)
                create_chunk_records(
                    job_id,
                    [{"chunk_id": c["chunk_id"], "index": c["index"], "offset": c["offset"]} for c in chunks],
                )
                update_job_status(job_id, status="TRANSCRIBING", total_chunks=len(chunks))
                for chunk in chunks:
                    transcribe_chunk_task.delay(
                        _chunk_key(chunk["chunk_id"]), job_id,
                        chunk["chunk_id"], chunk["index"], chunk["offset"], target_lang,
                    )

    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=f"Extraction Error: {str(e)}")
        raise


# ─── stage 2: transcribe one chunk ──────────────────────────────────────────────

@celery_app.task(queue='transcription_queue', bind=True, max_retries=3, default_retry_delay=30)
def transcribe_chunk_task(self, chunk_audio_key, job_id, chunk_id, chunk_index, time_offset, target_lang):
    try:
        transc_key = _transc_key(chunk_id)
        detected_language = None

        with tempfile.TemporaryDirectory() as tmpdir:
            if not minio_client.object_exists(transc_key):
                local_audio = os.path.join(tmpdir, f"{chunk_id}.mp3")
                minio_client.download_file(chunk_audio_key, local_audio)
                detected_language, segments = transcribe.transcribe_audio(local_audio, get_whisper())
                minio_client.upload_bytes(
                    json.dumps(segments, ensure_ascii=False).encode("utf-8"),
                    transc_key,
                )
                update_job_status(job_id, source_language=detected_language)
            # audio chunk no longer needed
            minio_client.delete_object(chunk_audio_key)

        update_job_status(job_id, status="TRANSLATING")
        translate_chunk_task.delay(job_id, chunk_id, chunk_index, time_offset, target_lang, detected_language)

    except Exception as e:
        update_chunk_status(chunk_id, status="FAILED", error_log=str(e))
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            update_job_status(
                job_id, status="FAILED",
                error_log=f"Chunk {chunk_index} transcription failed after retries: {str(e)}",
            )
            raise


# ─── stage 3: translate one chunk ───────────────────────────────────────────────

@celery_app.task(queue='translation_queue', bind=True, max_retries=3, default_retry_delay=30)
def translate_chunk_task(self, job_id, chunk_id, chunk_index, time_offset, target_lang, source_lang=None):
    try:
        transc_key = _transc_key(chunk_id)
        segments = json.loads(minio_client.read_bytes(transc_key).decode("utf-8"))

        translated_texts = translate.translate_segments(
            segments, target_lang, get_tokenizer(), get_nllb(), source_lang
        )

        srt_content = ""
        global_index = chunk_index * 1000
        for i, (segment, translation) in enumerate(zip(segments, translated_texts), start=1):
            start_abs = segment['start'] + time_offset
            end_abs = segment['end'] + time_offset
            srt_content += f"{global_index + i}\n"
            srt_content += f"{format_srt_time(start_abs)} --> {format_srt_time(end_abs)}\n"
            srt_content += f"{translation.strip()}\n\n"

        chunk_srt_key = _chunk_srt_key(chunk_id)
        minio_client.upload_bytes(srt_content.encode("utf-8"), chunk_srt_key)

        # transcription JSON no longer needed
        minio_client.delete_object(transc_key)

        update_chunk_status(chunk_id, status="COMPLETED", srt_path=chunk_srt_key)
        _maybe_complete_job(job_id)

    except Exception as e:
        update_chunk_status(chunk_id, status="FAILED", error_log=str(e))
        try:
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            update_job_status(
                job_id, status="FAILED",
                error_log=f"Chunk {chunk_index} translation failed after retries: {str(e)}",
            )
            raise


def _merge_chunk_srts(job_id: str) -> str:
    merged = ""
    for key in get_chunk_srt_paths(job_id):
        merged += minio_client.read_bytes(key).decode("utf-8")
    final_key = _final_srt_key(job_id)
    minio_client.upload_bytes(merged.encode("utf-8"), final_key)
    return final_key


def _maybe_complete_job(job_id: str):
    statuses = get_chunk_statuses(job_id)
    if statuses and all(s == "COMPLETED" for s in statuses):
        final_key = _merge_chunk_srts(job_id)
        update_job_status(job_id, status="COMPLETED", srt_path=final_key)
