# VEditor

Standalone, reusable video-review/transcode pipeline using FastAPI and Celery.

## Development Setup

There are two primary ways to run the project locally: fully containerized via Docker, or native app code (via `uv`) alongside containerized data stores.

### Option 1: Fully Containerized (Docker)

To run the entire stack (API, Worker, Postgres, Redis) in Docker:

1. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```

2. Start the services:
   ```bash
   docker compose up -d --build
   ```

3. Check the API health:
   ```bash
   curl http://localhost:8000/health
   ```

### Option 2: Native App + Dockerized DBs (Recommended for Dev)

If you prefer to run the Python application code locally using `uv` (for faster reloading and easier debugging) while keeping Postgres and Redis in Docker, you must have `ffmpeg` installed on your host machine so the Celery workers can process video natively.

1. Install System Dependencies (macOS)
   ```bash
   brew install ffmpeg
   ```

2. Start background services in Docker:
   ```bash
   docker compose up postgres redis -d
   ```

3. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```
   *(Ensure `DATABASE_URL` and `REDIS_URL` point to your localhost ports).*

4. Create a virtual environment and install dependencies using [uv](https://github.com/astral-sh/uv):
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   ```

5. Start the FastAPI server natively:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

6. Run the tests natively:
   ```bash
   uv run pytest
   ```
