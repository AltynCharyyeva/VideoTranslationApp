from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum
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
    
    # Foreign Key linking to User
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    owner = relationship("User", back_populates="translations")