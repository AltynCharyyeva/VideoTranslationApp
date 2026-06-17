import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from core.config import UPLOADS_DIR
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
        target_language=target_language,
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
    current_user: models.User = Depends(get_current_user),
):
    record = db.query(models.Translation).filter(
        models.Translation.id == str(translation_id),
        models.Translation.user_id == current_user.id,
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Translation not found")

    # Collect every completed chunk's SRT content, ordered by chunk_index
    completed_chunks = (
        db.query(models.TranslationChunk)
        .filter(
            models.TranslationChunk.translation_id == str(translation_id),
            models.TranslationChunk.status == "COMPLETED",
        )
        .order_by(models.TranslationChunk.chunk_index)
        .all()
    )

    chunks_srt = []
    for chunk in completed_chunks:
        if chunk.srt_path and os.path.exists(chunk.srt_path):
            with open(chunk.srt_path, "r", encoding="utf-8") as f:
                chunks_srt.append({
                    "chunk_index": chunk.chunk_index,
                    "srt_content": f.read(),
                })

    # Total chunk count (so the frontend knows progress)
    total_chunks = (
        db.query(models.TranslationChunk)
        .filter(models.TranslationChunk.translation_id == str(translation_id))
        .count()
    )

    print(f"[STATUS] job={translation_id} status={record.status} total={total_chunks} completed={len(completed_chunks)}")

    return {
        "status": record.status,
        "total_chunks": total_chunks,
        "completed_chunks": len(completed_chunks),
        # Legacy flat srt_content still works — just the full merge when done
        "srt_content": "\n".join(c["srt_content"] for c in chunks_srt) if record.status == "COMPLETED" else None,
        # Streaming: partial chunks for progressive loading
        "chunks": chunks_srt,
    }


@router.get("/{translation_id}/download/srt")
async def download_srt(
    translation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    record = db.query(models.Translation).filter(
        models.Translation.id == str(translation_id),
        models.Translation.user_id == current_user.id,
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="Translation not found")

    if not record.srt_path or not os.path.exists(record.srt_path):
        raise HTTPException(status_code=404, detail="Subtitle file not available")

    safe_stem = "".join(c for c in (record.filename or "") if c.isalnum() or c in (" ", "-", "_")).strip()
    download_name = f"{safe_stem[:60] or translation_id}.srt"

    return FileResponse(record.srt_path, media_type="application/x-subrip", filename=download_name)