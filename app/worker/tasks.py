import os
import json
import uuid
import tempfile
import yt_dlp
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import Celery
from database.database import update_job_status, update_chunk_status
from services import transcribe, translate
from worker.ai_models import get_whisper, get_tokenizer, get_nllb
from database.database import create_chunk_records, get_chunk_statuses_ordered
from core import minio_client

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))

CHUNK_DURATION = 240
CHUNKING_THRESHOLD = 300
MAX_PARALLEL_EXTRACTIONS = 4




def _audio_key(job_id):        return f"audio/{job_id}.mp3"
def _chunk_key(chunk_id):      return f"chunks/{chunk_id}.mp3"
def _transc_key(chunk_id):     return f"transcriptions/{chunk_id}.json"
def _chunk_srt_key(chunk_id):  return f"srt/chunks/{chunk_id}.srt"
def _final_srt_key(job_id):    return f"srt/{job_id}_final.srt"



def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def get_audio_duration(media_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", media_path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _extract_audio_segment(source_path, out_path, offset, duration=None):
    cmd = ["ffmpeg", "-y", "-ss", str(offset), "-i", source_path]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


#############################################################################################################################################
# extract audio

@celery_app.task(queue='audio_extraction_queue')
def extract_audio_task(input_source, job_id, target_lang):
    update_job_status(job_id, status="EXTRACTING_AUDIO")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            is_youtube = "youtube.com" in input_source or "youtu.be" in input_source

            if is_youtube:
                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'outtmpl': os.path.join(tmpdir, f"{job_id}.%(ext)s"),
                    'quiet': True,
                    'no_warnings': True,
                    'extractor_args': {
                        'youtube': {'player_client': ['android', 'tv', 'web']},
                    },
                }
                if os.path.isfile('/app/cookies.txt'):
                    ydl_opts['cookiefile'] = '/app/cookies.txt'
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(input_source, download=True)
                    local_source = ydl.prepare_filename(info)
            else:
                ext = os.path.splitext(input_source)[1]
                local_source = os.path.join(tmpdir, f"{job_id}{ext}")
                minio_client.download_file(input_source, local_source)

            if not os.path.exists(local_source):
                raise FileNotFoundError(f"Source media not found at {local_source}")

            duration = get_audio_duration(local_source)
            update_job_status(job_id, status="AUDIO_EXTRACTED")

            if duration <= CHUNKING_THRESHOLD:
                chunk_id = str(uuid.uuid4())
                local_audio = os.path.join(tmpdir, f"{job_id}.mp3")
                _extract_audio_segment(local_source, local_audio, 0.0)

                audio_key = _audio_key(job_id)
                minio_client.upload_file(local_audio, audio_key)
                create_chunk_records(job_id, [{"chunk_id": chunk_id, "index": 0, "offset": 0.0}])
                update_job_status(job_id, status="TRANSCRIBING", total_chunks=1)
                transcribe_chunk_task.delay(audio_key, job_id, chunk_id, 0, 0.0, target_lang)
                return

            plan = []
            offset = 0.0
            index = 0
            while offset < duration:
                plan.append({"chunk_id": str(uuid.uuid4()), "index": index, "offset": offset})
                offset += CHUNK_DURATION
                index += 1

            create_chunk_records(job_id, plan)
            update_job_status(job_id, status="TRANSCRIBING", total_chunks=len(plan))

            def _process_chunk(item):
                chunk_path = os.path.join(tmpdir, f"{item['chunk_id']}.mp3")
                _extract_audio_segment(local_source, chunk_path, item["offset"], CHUNK_DURATION)
                chunk_key = _chunk_key(item["chunk_id"])
                minio_client.upload_file(chunk_path, chunk_key)
                os.remove(chunk_path)
                transcribe_chunk_task.delay(
                    chunk_key, job_id, item["chunk_id"], item["index"], item["offset"], target_lang,
                )

            first_chunk, remaining_chunks = plan[0], plan[1:]
            _process_chunk(first_chunk)

            if remaining_chunks:
                with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_EXTRACTIONS, len(remaining_chunks))) as pool:
                    futures = [pool.submit(_process_chunk, item) for item in remaining_chunks]
                    for future in as_completed(futures):
                        future.result() 

    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=f"Extraction Error: {str(e)}")
        raise


#############################################################################################################################################
#transcribe

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


#############################################################################################################################################
# translate

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


def _maybe_complete_job(job_id: str):
    ordered_chunks = get_chunk_statuses_ordered(job_id)

    contiguous = []
    for chunk_id, status, srt_path in ordered_chunks:
        if status == "COMPLETED" and srt_path:
            contiguous.append(srt_path)
        else:
            break

    if not contiguous:
        return

    merged = ""
    for srt_path in contiguous:
        merged += minio_client.read_bytes(srt_path).decode("utf-8")

    final_key = _final_srt_key(job_id)
    minio_client.upload_bytes(merged.encode("utf-8"), final_key)
    update_job_status(job_id, status="COMPLETED", srt_path=final_key)
