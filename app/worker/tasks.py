import os
import json
import yt_dlp
import subprocess
import edge_tts
import asyncio
import re
import tempfile
from pydub import AudioSegment
from celery import Celery
from database.database import update_job_status
from services import transcribe, translate, get_voice
from core.config import TRANSLATIONS_DIR, TRANSCRIPTIONS_DIR, AUDIOS_DIR, UPLOADS_DIR, DUBBED_AUDIOS_DIR, DUBBED_VIDEOS_DIR
from worker.ai_models import get_whisper, get_tokenizer, get_nllb

celery_app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL"))


@celery_app.task(queue='audio_extraction_queue')
def extract_audio_task(input_source, job_id, target_lang):
    audio_output_path = os.path.join(AUDIOS_DIR, f"{job_id}.mp3")
    
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
            
        
        else:
            # Local File Path (FFmpeg)
            # -i: input, -vn: disable video, -acodec libmp3lame: use mp3 encoder, -y: overwrite
            command = [
                "ffmpeg", "-i", input_source,
                "-vn", "-acodec", "libmp3lame", 
                "-ar", "16000", "-ac", "1", 
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

        translated_segments = []
        for segment, translation in zip(segments, translated_texts):
            translated_segments.append({
                "start": segment['start'],
                "end": segment['end'],
                "text": translation.strip()
            })

        update_job_status(job_id, status="TRANSLATED", srt_path=srt_filename)

        dubbing_task.delay(job_id, target_lang, translated_segments)
        
        print("\nTranslation completed\n")
        # return srt_filename
    except Exception as e:
        update_job_status(job_id, status="FAILED", error_log=str(e))
        raise


@celery_app.task(queue='dubbing_queue')
def dubbing_task(job_id, target_lang, segments):
    return asyncio.run(run_dubbing_logic(job_id, target_lang, segments))


async def run_dubbing_logic(job_id, target_lang, segments):
    update_job_status(job_id, status="GENERATING_VOICE")
    combined_audio = AudioSegment.silent(duration=0)
    
    for i, seg in enumerate(segments):
        text = seg['text'].strip()
        text = re.sub(r'[\[\(]\d+[.:]\d{2}(?:[.:]\d{2})?[\]\)]', '', text).strip()
        if not text:
            continue
        
        start_ms = int(seg['start'] * 1000)
        end_ms = int(seg['end'] * 1000)
        max_duration = end_ms - start_ms

        # 1. Generate TTS
        temp_path = os.path.join(DUBBED_AUDIOS_DIR, f"temp_{job_id}_{i}.mp3")
        stretched_path = os.path.join(DUBBED_AUDIOS_DIR, f"stretched_{job_id}_{i}.mp3")
        communicate = edge_tts.Communicate(text, voice=get_voice.get_voice_for_lang(target_lang))
        await communicate.save(temp_path)
        
        # 2. Load and stretch with ffmpeg — much better quality than pydub speedup
        segment_audio = AudioSegment.from_file(temp_path)
        MAX_SPEED = 1.3  # Never go faster than 1.3x

        if len(segment_audio) > max_duration:
            speed_factor = min(len(segment_audio) / max_duration, MAX_SPEED)
            
            # atempo only supports 0.5–2.0, chain filters if needed
            if speed_factor <= 2.0:
                atempo_filter = f"atempo={speed_factor:.4f}"
            else:
                # Shouldn't hit this given MAX_SPEED=1.3, but just in case
                atempo_filter = f"atempo=2.0,atempo={speed_factor/2.0:.4f}"

            subprocess.run([
                "ffmpeg", "-y", "-i", temp_path,
                "-filter:a", atempo_filter,
                stretched_path
            ], check=True, capture_output=True)
            
            segment_audio = AudioSegment.from_file(stretched_path)

        # 3. Absolute positioning
        silence_needed = start_ms - len(combined_audio)
        if silence_needed > 0:
            combined_audio += AudioSegment.silent(duration=silence_needed)
        else:
            combined_audio = combined_audio[:start_ms]

        combined_audio += segment_audio
        
        # Cleanup temp files
        for path in [temp_path, stretched_path]:
            if os.path.exists(path):
                os.remove(path)

    dub_path = os.path.join(DUBBED_AUDIOS_DIR, f"{job_id}_dubbed.mp3")
    combined_audio.export(dub_path, format="mp3")
    mix_video_task.delay(job_id, dub_path)


@celery_app.task(queue='video_mixing_queue')
def mix_video_task(job_id, dubbed_audio_path):
    update_job_status(job_id, status="MIXING_VIDEO")
    
    original_video = os.path.join(UPLOADS_DIR, f"{job_id}.mp4")
    output_video = os.path.join(DUBBED_VIDEOS_DIR, f"{job_id}_dubbed.mp4")

    # FFmpeg command to replace audio
    command = [
        "ffmpeg", "-i", original_video, "-i", dubbed_audio_path,
        "-c:v", "copy", # Don't re-encode video (fast!)
        "-map", "0:v:0", "-map", "1:a:0", # Use video from 1st input, audio from 2nd
        "-shortest", "-y", output_video
    ]
    
    subprocess.run(command, check=True)
    update_job_status(job_id, status="COMPLETED", dubbed_video_path=output_video)