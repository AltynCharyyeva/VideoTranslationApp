from fastapi import FastAPI
from api.endpoints import videos, users, auth
from database.database import engine
from database.base import Base
from fastapi.middleware.cors import CORSMiddleware

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Video Translator")

# Define the origins that are allowed to talk to your API
origins = [
    "http://localhost:3000",  # React default port
    "http://127.0.0.1:3000",
    # Add your production domain here later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Allows specific origins
    allow_credentials=True,           # Allows cookies and headers like Authorization
    allow_methods=["*"],              # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],              # Allows all headers
)

app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(users.router)

@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to the Video Translation API. Visit /docs for the UI."
    }