from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.dependencies import (
    create_access_token,
    hash_password,
    verify_password,
    ADMIN_EMAIL
)
from database.database import get_db
from models.models import User
from schemas.schemas import CreateUser, LoginRequest, TokenResponse, BaseUser
from models.models import Role


router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=BaseUser, status_code=status.HTTP_201_CREATED)
def register(user_in: CreateUser, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    role = Role.ADMIN if user_in.email == ADMIN_EMAIL else Role.USER

    user = User(
        email=user_in.email,
        password=hash_password(user_in.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):

    dummy_hash = hash_password("dummy_password")

    user = db.query(User).filter(User.email == credentials.email).first()
    hash_to_check = user.password if user else dummy_hash

    if not verify_password(credentials.password, hash_to_check) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

# @router.post("/logout", status_code=status.HTTP_200_OK)
# def logout(token: str = Depends(oauth2_scheme)):
#     TOKEN_BLOCKLIST.add(token)
#     return {"message": "Logged out successfully"}