# ─────────────────────────────────────────────────────────────
# TruthScan — Dockerfile (flat project, for Render.com)
#
# Folder structure (everything flat, same dir):
#   app.py
#   index.html
#   style.css
#   main.js
#   requirements.txt
#   Dockerfile
#   render.yaml
#   vec_word.pkl     ← add before docker build
#   vec_char.pkl     ← add before docker build
#   scaler.pkl       ← add before docker build
#   ensemble.pkl     ← add before docker build
#   models.pkl       ← add before docker build
# ─────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Native libs needed by lightgbm / xgboost
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire flat project
COPY . .

EXPOSE 8080

ENV PORT=8080

# --preload: models loaded once, shared across workers
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--timeout", "120", \
     "--preload"]
