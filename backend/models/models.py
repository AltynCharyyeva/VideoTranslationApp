from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database.base import Base 

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    
    # Link to the Translations
    translations = relationship("Translation", back_populates="owner")

class Translation(Base):
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    status = Column(String, default="PENDING")
    srt_path = Column(String) 
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Foreign Key linking to User
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="translations")