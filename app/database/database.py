from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from models.models import Translation
import os

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

