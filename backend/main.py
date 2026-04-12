from fastapi import FastAPI
from api.endpoints import videos, users
from database.database import engine
from database.base import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Video Translator")

app.include_router(videos.router)
app.include_router(users.router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to the Video Translation API. Visit /docs for the UI."
    }