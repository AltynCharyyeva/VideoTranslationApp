import os
import json
from celery import Celery
from database.database import update_job_status
from services import transcribe, translate
from core.config import TRANSLATIONS_DIR, TRANSCRIPTIONS_DIR
from worker.ai_models import get_whisper, get_tokenizer, get_nllb

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))

@celery_app.task(queue='whisper_queue')
def transcribe_task(audio_path, job_id, target_lang): 
    update_job_status(job_id, status="TRANSCRIBING")
    try:
        transcribe.transcribe_audio(audio_path, str(job_id), get_whisper())
        # Dispatch translation directly, segments are on disk
        translate_task.apply_async(
            args=[job_id, target_lang],
            queue='nllb_queue'
        )
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise

@celery_app.task(queue='nllb_queue')
def translate_task(job_id, target_lang):
    update_job_status(job_id, status="TRANSLATING")
    try:
        # Load segments from disk instead of from broker
        transcription_path = os.path.join(TRANSCRIPTIONS_DIR, f"{job_id}_transcrip.json")
        with open(transcription_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        translated_lines = translate.translate_segments(
            segments, target_lang, get_tokenizer(), get_nllb()
        )
        srt_filename = os.path.join(TRANSLATIONS_DIR, f"{job_id}_res.txt")
        with open(srt_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(translated_lines))

        update_job_status(job_id, status="COMPLETED", srt_path=srt_filename)
        print("\nTranslation completed\n")
        return srt_filename
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise