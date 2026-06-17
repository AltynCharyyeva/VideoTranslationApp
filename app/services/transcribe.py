import json
import os
from core.config import TRANSCRIPTIONS_DIR

def transcribe_audio(audio_path: str, job_id: str, whisper_model) -> str:
    segments_generator, info = whisper_model.transcribe(
        audio_path,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    segments = [
        {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text
        }
        for segment in segments_generator
    ]

    file_path = os.path.join(TRANSCRIPTIONS_DIR, f"{job_id}_transcrip.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=4, ensure_ascii=False)

    print(f"Transcription saved to {file_path}\n")
    return info.language