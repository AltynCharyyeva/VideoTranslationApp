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
from auth.dependencies import get_current_user
from fastapi import Form

router = APIRouter(
    prefix="/videos",
    tags=["videos"]
)

@router.post("/translate")
async def translate_video(
    file: UploadFile,
    target_language: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Save video to disk
    job_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    video_path = os.path.join(UPLOADS_DIR, f"{job_id}{file_extension}")

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    # 2. Extract audio in thread pool
    # run_in_executor -> run this task in the background with one of the threads in a thread pool
    try:
        audio_path = await asyncio.get_event_loop().run_in_executor(
            None, extract_audio.extract_audio, video_path, AUDIOS_DIR
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio extraction failed: {str(e)}")

    # 3. Create DB record
    new_translation = models.Translation(
        filename=file.filename,
        user_id=current_user.id,
        status="pending",
    )
    db.add(new_translation)
    db.commit()
    db.refresh(new_translation)

    # 4. Start transcription task — it then starts translation on completion
    # apply_async -> turns the function call into a distributed background task
    transcribe_task.apply_async(
        args=[audio_path, new_translation.id, target_language],
        queue='whisper_queue'
    )

    return {
        "message": "Video upload successful. Processing started.",
        "translation_id": new_translation.id,
        "status": new_translation.status
    }


@router.get("/{translation_id}")
async def get_status(
    translation_id: uuid.UUID, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    record = db.query(models.Translation).filter(
        models.Translation.id == translation_id,
        models.Translation.user_id == current_user.id
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Translation not found")

    srt_content = None
    if record.status == "COMPLETED" and record.srt_path:
        # Check if the file exists and read it
        print("\n\n", record.srt_path)
        if os.path.exists(record.srt_path):
            with open(record.srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

    return {
        "status": record.status,
        "srt_content": srt_content  # This is what the frontend is looking for
    }