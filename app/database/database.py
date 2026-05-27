from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from models.models import Translation, TranslationChunk
import os
import uuid

SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@postgres:5432/{os.getenv('POSTGRES_DB', 'trans_db')}"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_session():
    """Context manager to ensure DB sessions are closed in Celery tasks."""
    db = SessionLocal()
    try:
        yield db
        db.commit() # Auto-commit on success
    except Exception:
        db.rollback() # Rollback on error
        raise
    finally:
        db.close()


def update_job_status(job_id: int, **kwargs):
    """
    Updates specific fields for a Translation record in Postgres.
    
    Args:
        job_id (int): The primary key ID of the translation job.
        **kwargs: Column names and their new values (e.g., status="PROCESSING").
    """
    with get_db_session() as db:
        # 1. Look up the record
        job = db.query(Translation).filter(Translation.id == job_id).first()
        
        if not job:
            # You might want to log this or raise an error if the ID is missing
            print(f"Job {job_id} not found in database.")
            return None

        # 2. Dynamically update the attributes
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
            else:
                print(f"Warning: Translation model has no attribute '{key}'")

        db.flush() 
        return job


def create_chunk_records(job_id: str, chunks: list[dict]):
    print(f"[CREATE_CHUNKS] job_id={job_id}")
    try:
        with get_db_session() as db:
            # Verify parent exists first
            parent = db.query(Translation).filter(
                Translation.id == uuid.UUID(job_id)
            ).first()
            print(f"[CREATE_CHUNKS] parent translation found: {parent is not None}")
            if not parent:
                raise ValueError(f"Translation {job_id} not found — cannot create chunks")
            
            for c in chunks:
                chunk = TranslationChunk(
                    id=uuid.UUID(c["chunk_id"]),
                    translation_id=uuid.UUID(job_id),
                    chunk_index=c["index"],
                    time_offset=c["offset"],
                    status="PENDING",
                )
                db.add(chunk)
                db.flush()
                print(f"[CREATE_CHUNKS] inserted chunk index={c['index']}")
    except Exception as e:
        print(f"[CREATE_CHUNKS] FAILED: {e}")
        raise


def update_chunk_status(chunk_id: str, status: str, srt_path: str = None, error_log: str = None):
    with get_db_session() as db:
        chunk = db.query(TranslationChunk).filter(TranslationChunk.id == uuid.UUID(chunk_id)).first()
        if chunk:
            chunk.status = status
            if srt_path:
                chunk.srt_path = srt_path
            if error_log:
                chunk.error_log = error_log


def get_chunk_statuses(job_id: str) -> list[str]:
    with get_db_session() as db:
        chunks = db.query(TranslationChunk).filter(
            TranslationChunk.translation_id == uuid.UUID(job_id)
        ).all()
        return [c.status for c in chunks]