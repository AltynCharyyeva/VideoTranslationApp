from fastapi import FastAPI
from api.endpoints import videos, users, auth, streaming
from database.database import engine
from database.base import Base
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from contextlib import asynccontextmanager
from api.endpoints.streaming import whisper_executor, nllb_executor
from core.minio_client import init_bucket

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_bucket()
    print("MinIO bucket ready.")
    print("Warming up worker processes...")
    loop = asyncio.get_event_loop()

    # Warm up whisper pool (1 worker)
    whisper_futures = [
        loop.run_in_executor(whisper_executor, _noop)
        for _ in range(1)
    ]
    # Warm up nllb pool (1 worker)
    nllb_futures = [
        loop.run_in_executor(nllb_executor, _noop)
        for _ in range(1)
    ]

    await asyncio.gather(*whisper_futures, *nllb_futures)
    print("All workers warmed up — Whisper and NLLB models loaded.")
    yield

def _noop():
    pass

app = FastAPI(title="AI Video Translator", lifespan=lifespan)
Base.metadata.create_all(bind=engine)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(users.router)
app.include_router(streaming.router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to the Video Translation API. Visit /docs for the UI."
    }