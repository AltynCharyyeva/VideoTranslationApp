from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database.database import get_db
from models.models import Role, User
import os
from uuid import UUID

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")

# TOKEN_BLOCKLIST: set[str] = set()

# ── Config ────────────────────────────────────────────
SECRET_KEY  = "a7ac14824c1e67ddf870c66c4addf422fecc4dd6e9cfd8aec37e98cb09866531"   # use os.environ in prod
ALGORITHM   = "HS256"
TOKEN_EXPIRE_MINUTES = 240

pwd_context   = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = HTTPBearer()

# ── Password helpers ──────────────────────────────────
def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# ── Token helpers ─────────────────────────────────────
def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ── Core dependency: who is calling? ──────────────────
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials

    # if token in TOKEN_BLOCKLIST:  # ← check blocklist first
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Token has been invalidated, please log in again",
    #     )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = UUID(payload.get("sub"))
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# ── Role guard factory ────────────────────────────────
ROLE_RANK = {Role.USER: 1, Role.ADMIN: 2}

def require_role(min_role: Role):
    """
    Usage:  Depends(require_role(Role.ADMIN))
    Passes if the caller's role rank >= min_role rank.
    """
    def guard(current_user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK[current_user.role] < ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role.value} role or higher",
            )
        return current_user
    return guard

# ── Convenience shortcuts ─────────────────────────────
AnyUser    = Depends(get_current_user)
AdminOnly  = Depends(require_role(Role.ADMIN))