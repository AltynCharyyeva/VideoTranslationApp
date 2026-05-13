import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session
from core.config import UPLOADS_DIR, AUDIOS_DIR
from database.database import get_db
from models import models
from worker.tasks import extract_audio_task
from auth.dependencies import get_current_user
from fastapi import Form, File
from typing import Optional

router = APIRouter(
    prefix="/videos",
    tags=["videos"]
)

@router.post("/translate")
async def translate_video(
    file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    target_language: str = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    job_id = str(uuid.uuid4())
    input_source = ""
    filename = ""

    # 1. Decide if we are using a URL or a File
    if youtube_url:
        input_source = youtube_url
        filename = f"YouTube: {youtube_url}"
    
    elif file:
        filename = file.filename
        file_extension = os.path.splitext(file.filename)[1]
        video_path = os.path.join(UPLOADS_DIR, f"{job_id}{file_extension}")
        input_source = video_path # The input for the worker is the local path

        # Move the saving logic INSIDE this block
        try:
            with open(video_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="Please provide a YouTube URL or a video file.")

    # 2. Create DB record
    new_translation = models.Translation(
        id=job_id,
        filename=filename,
        user_id=current_user.id,
        status="PENDING",
    )
    db.add(new_translation)
    db.commit()

    # 3. Start the background pipeline
    # We pass 'input_source' which is either the URL or the local video_path
    extract_audio_task.delay(input_source, job_id, target_language)

    return {
        "message": "Processing started.",
        "translation_id": job_id,
        "status": "PENDING"
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