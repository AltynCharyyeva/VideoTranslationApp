from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

# What we send back to the USER (Includes the generated ID)
class BaseUser(BaseModel):
    id: int
    email: str
    # We do NOT include password here for security!
    #password: str
    model_config = ConfigDict(from_attributes=True)


# What the USER sends us (No ID here!)
class CreateUser(BaseModel):
    email: str
    password: str

    model_config = ConfigDict(from_attributes=True)


class UpdateUser(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)



# Base fields shared by all Translation schemas
class TranslationBase(BaseModel):
    filename: str
    #target_language: str # Useful to store what language they picked

# What we send back to the USER
class Translation(TranslationBase):
    id: int
    status: str
    srt_path: Optional[str] = None
    created_at: datetime
    user_id: int

    model_config = ConfigDict(from_attributes=True)

# If you want to see the translations inside the User object
class UserWithTranslations(BaseUser):
    translations: list[Translation] = []

    model_config = ConfigDict(from_attributes=True)
