import os
import json
import yt_dlp
import subprocess
from celery import Celery
from database.database import update_job_status
from services import transcribe, translate
from core.config import TRANSLATIONS_DIR, TRANSCRIPTIONS_DIR, AUDIOS_DIR
from worker.ai_models import get_whisper, get_tokenizer, get_nllb

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))


@celery_app.task(queue='audio_extraction_queue')
def extract_audio_task(input_source, job_id, target_lang):
    audio_output_path = os.path.join(AUDIOS_DIR, f"{job_id}.mp3")
    
    # 1. Check if audio already exists (Checkpoint)
    if os.path.exists(audio_output_path):
        return transcribe_task.delay(audio_output_path, job_id, target_lang)

    update_job_status(job_id, status="EXTRACTING_AUDIO")

    try:
        # 2. Check if input is a YouTube URL
        is_youtube = "youtube.com" in input_source or "youtu.be" in input_source

        if is_youtube:
            # YouTube Path
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(AUDIOS_DIR, str(job_id)), # Template for name
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([input_source])
            # yt-dlp adds the .mp3 extension automatically based on preferredcodec
        
        else:
            # Local File Path (FFmpeg)
            # -i: input, -vn: disable video, -acodec libmp3lame: use mp3 encoder, -y: overwrite
            command = [
                "ffmpeg", "-i", input_source,
                "-vn", "-acodec", "libmp3lame", 
                "-ar", "16000", "-ac", "1", # 16kHz Mono is perfect for Whisper
                "-y", audio_output_path
            ]
            subprocess.run(command, check=True, capture_output=True)

        # 3. Finalize and Move to next step
        if os.path.exists(audio_output_path):
            update_job_status(job_id, status="AUDIO_EXTRACTED", audio_path=audio_output_path)
            transcribe_task.delay(audio_output_path, job_id, target_lang)
        else:
            raise FileNotFoundError(f"Audio file was not created at {audio_output_path}")

    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=f"Extraction Error: {str(e)}")
        raise e
    

@celery_app.task(queue='transcription_queue')
def transcribe_task(audio_path, job_id, target_lang): 
    update_job_status(job_id, status="TRANSCRIBING")
    try:
        transcribe.transcribe_audio(audio_path, str(job_id), get_whisper())
        translate_task.delay(job_id, target_lang)
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise

def format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

@celery_app.task(queue='translation_queue')
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