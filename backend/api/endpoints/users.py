from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from schemas import schemas 
from models import models
from database.database import get_db

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

# 1. CREATE
@router.post("/", response_model=schemas.BaseUser, status_code=status.HTTP_201_CREATED)
def create_user(user: schemas.CreateUser, db: Session = Depends(get_db)):
    
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    
    new_user = models.User(
        email=user.email,
        password=user.password 
    )
    
    db.add(new_user)
    db.commit()     
    db.refresh(new_user) 
    return new_user

@router.get("/all_users", response_model=list[schemas.UserWithTranslations])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return users

# 2. READ
@router.get("/{user_id}", response_model=schemas.UserWithTranslations)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# 3. UPDATE
@router.patch("/{user_id}", response_model=schemas.BaseUser)
def update_user(user_id: int, user_update: schemas.UpdateUser, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# 4. DELETE
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return None