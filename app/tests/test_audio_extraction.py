"""
Functional tests for Stage 1: audio extraction.

The task is called directly (synchronously, no Celery broker needed).
transcribe_chunk_task.delay is mocked so only extraction runs.

Requirements:
  - MinIO reachable at localhost:9000  (Docker port mapping)
  - PostgreSQL reachable at the DATABASE_URL env var
  - MINIO_ENDPOINT=http://localhost:9000 (or set in .env)
"""

import os
import uuid
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("MINIO_ENDPOINT", "http://localhost:9000")

from core import minio_client
from worker.tasks import extract_audio_task, _audio_key, _chunk_key, CHUNKING_THRESHOLD


# ── helpers ────────────────────────────────────────────────────────────────────

def _upload_fixture(local_path: str, job_id: str) -> str:
    ext = os.path.splitext(local_path)[1]
    key = f"uploads/{job_id}{ext}"
    minio_client.upload_file(local_path, key)
    return key


def _cleanup_audio(job_id):
    key = _audio_key(job_id)
    if minio_client.object_exists(key):
        minio_client.delete_object(key)


# ── tests ──────────────────────────────────────────────────────────────────────

@patch("worker.tasks.transcribe_chunk_task.delay")
@patch("worker.tasks.update_job_status")
@patch("worker.tasks.create_chunk_records")
def test_uploaded_video_produces_audio_in_minio(mock_chunks, mock_status, mock_transcribe):
    """A valid uploaded MP4 must produce an MP3 in MinIO (audio/ for short, chunks/ for long)"""
    job_id = str(uuid.uuid4())
    upload_key = _upload_fixture("tests/fixtures/video_1.mp4", job_id)

    extract_audio_task(upload_key, job_id, "ron_Latn")

    # The first argument of every transcribe_chunk_task.delay call is the MinIO audio key.
    # We verify that key actually exists in MinIO rather than hardcoding the path,
    # because long videos are split into chunks (chunks/<id>.mp3) while short videos
    # use audio/<job_id>.mp3.
    assert mock_transcribe.called, "transcribe_chunk_task.delay was never called"
    dispatched_keys = [call.args[0] for call in mock_transcribe.call_args_list]
    for key in dispatched_keys:
        assert minio_client.object_exists(key), \
            f"Audio key dispatched to transcriber not found in MinIO: {key}"
        minio_client.delete_object(key)


@patch("worker.tasks.transcribe_chunk_task.delay")
@patch("worker.tasks.update_job_status")
@patch("worker.tasks.create_chunk_records")
def test_extraction_deletes_original_upload(mock_chunks, mock_status, mock_transcribe):
    """The original uploaded video must be removed from MinIO after audio is extracted"""
    job_id = str(uuid.uuid4())
    upload_key = _upload_fixture("tests/fixtures/video_1.mp4", job_id)

    extract_audio_task(upload_key, job_id, "ron_Latn")

    assert not minio_client.object_exists(upload_key), \
        "Original upload was not cleaned up from MinIO"
    _cleanup_audio(job_id)


@patch("worker.tasks.transcribe_chunk_task.delay")
@patch("worker.tasks.update_job_status")
@patch("worker.tasks.create_chunk_records")
def test_transcription_is_dispatched_after_extraction(mock_chunks, mock_status, mock_transcribe):
    """After successful extraction, transcribe_chunk_task.delay must be called at least once"""
    job_id = str(uuid.uuid4())
    upload_key = _upload_fixture("tests/fixtures/video_1.mp4", job_id)

    extract_audio_task(upload_key, job_id, "ron_Latn")

    assert mock_transcribe.called, "transcribe_chunk_task.delay was never called"
    _cleanup_audio(job_id)


@patch("worker.tasks.transcribe_chunk_task.delay")
@patch("worker.tasks.update_job_status")
@patch("worker.tasks.create_chunk_records")
def test_status_transitions_are_correct(mock_chunks, mock_status, mock_transcribe):
    """Job status must go EXTRACTING_AUDIO → AUDIO_EXTRACTED → TRANSCRIBING"""
    job_id = str(uuid.uuid4())
    upload_key = _upload_fixture("tests/fixtures/video_1.mp4", job_id)

    extract_audio_task(upload_key, job_id, "ron_Latn")

    calls = [c.args[1] for c in mock_status.call_args_list if len(c.args) >= 2]
    # alternatively check kwargs
    statuses = []
    for c in mock_status.call_args_list:
        s = c.kwargs.get("status") or (c.args[1] if len(c.args) > 1 else None)
        if s:
            statuses.append(s)

    assert "EXTRACTING_AUDIO" in statuses
    assert "AUDIO_EXTRACTED" in statuses
    assert "TRANSCRIBING" in statuses
    _cleanup_audio(job_id)


@patch("worker.tasks.transcribe_chunk_task.delay")
@patch("worker.tasks.update_job_status")
@patch("worker.tasks.create_chunk_records")
def test_corrupted_file_marks_job_failed(mock_chunks, mock_status, mock_transcribe):
    """A corrupted video must set job status to FAILED.
    The task re-raises after logging failure (correct Celery behaviour),
    so we expect the exception here and only check the status side-effect."""
    job_id = str(uuid.uuid4())

    bad_key = f"uploads/{job_id}.mp4"
    minio_client.upload_bytes(b"this is not a video", bad_key)

    with pytest.raises(Exception):
        extract_audio_task(bad_key, job_id, "ron_Latn")

    statuses = []
    for c in mock_status.call_args_list:
        s = c.kwargs.get("status") or (c.args[1] if len(c.args) > 1 else None)
        if s:
            statuses.append(s)
    assert "FAILED" in statuses, f"Expected FAILED status, got: {statuses}"
