from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from database.base import Base 
import enum
import uuid

class Role(str, enum.Enum):
    ADMIN = "admin"
    USER  = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role     = Column(SAEnum(Role), default=Role.USER, nullable=False)
    
    # Link to the Translation
    translations = relationship("Translation", back_populates="owner")

class Translation(Base):
    __tablename__ = "translations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String)
    status = Column(String, default="PENDING")
    srt_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    audio_path = Column(String, nullable=True)
    source_language = Column(String, nullable=True)
    target_language = Column(String, nullable=True)
    
    # Foreign Key linking to User
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    owner = relationship("User", back_populates="translations")
    chunks = relationship("TranslationChunk", back_populates="translation", order_by="TranslationChunk.chunk_index")

class TranslationChunk(Base):
    __tablename__ = "translation_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    translation_id = Column(UUID(as_uuid=True), ForeignKey("translations.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)   # 0-based order
    status = Column(String, default="PENDING")      # PENDING | COMPLETED | FAILED
    srt_path = Column(String, nullable=True)
    time_offset = Column(Float, default=0.0)        # seconds into the original video
    error_log = Column(String, nullable=True)

    translation = relationship("Translation", back_populates="chunks")