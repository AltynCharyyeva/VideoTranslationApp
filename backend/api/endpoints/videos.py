import asyncio
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session
from core.config import UPLOADS_DIR, AUDIOS_DIR
from database.database import get_db
from models import models
from services import extract_audio
from worker.tasks import transcribe_task

router = APIRouter(
    prefix="/videos",
    tags=["videos"]
)

@router.post("/translate")
async def translate_video(
    file: UploadFile,
    target_language: str,
    db: Session = Depends(get_db)
):
    job_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    video_path = os.path.join(UPLOADS_DIR, f"{job_id}{file_extension}")

    # 1. Save video to disk
    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    # 2. Extract audio in thread pool
    try:
        audio_path = await asyncio.get_event_loop().run_in_executor(
            None, extract_audio.extract_audio, video_path, AUDIOS_DIR
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio extraction failed: {str(e)}")

    # 3. Create DB record
    new_translation = models.Translation(
        filename=file.filename,
        user_id=2,
        status="pending",
    )
    db.add(new_translation)
    db.commit()
    db.refresh(new_translation)

    # 4. Dispatch transcription task — it will trigger translation on completion
    transcribe_task.apply_async(
        args=[audio_path, new_translation.id, target_language],
        queue='whisper_queue'
    )

    return {
        "message": "Video upload successful. Processing started.",
        "translation_id": new_translation.id,
        "status": new_translation.status
    }