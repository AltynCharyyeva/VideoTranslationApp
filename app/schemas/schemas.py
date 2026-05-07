from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator

# ── Auth ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Users ─────────────────────────────────────────────
# What we send back to the USER (Includes the generated ID)
class BaseUser(BaseModel):
    id: UUID
    email: str
    model_config = ConfigDict(from_attributes=True)


# What the USER sends us (No ID here!)
class CreateUser(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)


class UpdateUser(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



# Base fields shared by all Translation schemas
class TranslationBase(BaseModel):
    filename: str

# What we send back to the USER
class Translation(TranslationBase):
    id: UUID
    status: str
    srt_path: Optional[str] = None
    created_at: datetime
    user_id: UUID

    model_config = ConfigDict(from_attributes=True)

class UserWithTranslations(BaseUser):
    translations: list[Translation] = []

    model_config = ConfigDict(from_attributes=True)
