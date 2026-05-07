import os
import json
import re
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
        translate_task.apply_async(
            args=[job_id, target_lang],
            queue='nllb_queue'
        )
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise

def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

@celery_app.task(queue='nllb_queue')
def translate_task(job_id, target_lang):
    update_job_status(job_id, status="TRANSLATING")
    try:
        transcription_path = os.path.join(TRANSCRIPTIONS_DIR, f"{job_id}_transcrip.json")
        with open(transcription_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        translated_texts = translate.translate_segments(
            segments, target_lang, get_tokenizer(), get_nllb()
        )

        srt_content = ""
        for i, (segment, translation) in enumerate(zip(segments, translated_texts), start=1):
            start_str = format_srt_time(segment['start'])
            end_str = format_srt_time(segment['end'])
            
            # Standard SRT Block: Index, Times, Text, Empty Line
            srt_content += f"{i}\n"
            srt_content += f"{start_str} --> {end_str}\n"
            srt_content += f"{translation.strip()}\n\n"
        
        # 4. Save to disk
        srt_filename = os.path.join(TRANSLATIONS_DIR, f"{job_id}_res.srt")
        with open(srt_filename, "w", encoding="utf-8") as f:
            f.write(srt_content)

        update_job_status(job_id, status="COMPLETED", srt_path=srt_filename)
        
        print("\nTranslation completed\n")
        # return srt_filename
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise