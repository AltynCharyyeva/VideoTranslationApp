import os
import uuid
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session
from database.database import get_db
from models import models
from worker.tasks import extract_audio_task
from auth.dependencies import get_current_user
from fastapi import Form, File
from typing import Optional
from core import minio_client


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

    if youtube_url:
        input_source = youtube_url
        filename = f"YouTube: {youtube_url}"

    elif file:
        filename = file.filename
        ext = os.path.splitext(file.filename)[1]
        upload_key = f"uploads/{job_id}{ext}"
        minio_client.upload_fileobj(file.file, upload_key)
        input_source = upload_key

    else:
        raise HTTPException(status_code=400, detail="Please provide a YouTube URL or a video file.")

    new_translation = models.Translation(
        id=job_id,
        filename=filename,
        user_id=current_user.id,
        status="PENDING",
        target_language=target_language,
    )
    db.add(new_translation)
    db.commit()

    extract_audio_task.delay(input_source, job_id, target_language)

    return {"message": "Processing started.", "translation_id": job_id, "status": "PENDING"}


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
        if chunk.srt_path:
            try:
                srt_content = minio_client.read_bytes(chunk.srt_path).decode("utf-8")
                chunks_srt.append({"chunk_index": chunk.chunk_index, "srt_content": srt_content})
            except Exception:
                pass

    total_chunks = (
        db.query(models.TranslationChunk)
        .filter(models.TranslationChunk.translation_id == str(translation_id))
        .count()
    )

    return {
        "status": record.status,
        "total_chunks": total_chunks,
        "completed_chunks": len(completed_chunks),
        "srt_content": "\n".join(c["srt_content"] for c in chunks_srt) if record.status == "COMPLETED" else None,
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

    if not record.srt_path or not minio_client.object_exists(record.srt_path):
        raise HTTPException(status_code=404, detail="Subtitle file not available yet")

    safe_stem = "".join(c for c in (record.filename or "") if c.isalnum() or c in (" ", "-", "_")).strip()
    download_name = f"{safe_stem[:60] or translation_id}.srt"

    content = minio_client.read_bytes(record.srt_path)
    return Response(
        content,
        media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
