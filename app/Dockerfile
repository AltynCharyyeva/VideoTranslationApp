FROM python:3.12-slim

WORKDIR /app

# 1. System dependencies first
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN apt-get update && apt-get install -y ffmpeg nodejs && rm -rf /var/lib/apt/lists/*

# Force the latest version of yt-dlp
RUN pip install --no-cache-dir --upgrade yt-dlp

# 2. Python dependencies (all in one place)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy app code
COPY . .

# 4. Environment
ENV PYTHONUNBUFFERED=1
ENV MODEL_CACHE_DIR=/app/ai_models

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]