FROM python:3.11-slim

# System dependencies: FFmpeg, LaTeX, OpenGL, Pango
RUN apt-get update && apt-get install -y \
    ffmpeg \
    texlive-full \
    texlive-latex-extra \
    libpango1.0-dev \
    libcairo2-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend.py .
COPY manim_config.yml .

EXPOSE 8000

CMD uvicorn backend:app --host 0.0.0.0 --port $PORT
