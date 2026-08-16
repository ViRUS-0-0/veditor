# VEditor

Standalone, reusable video-review/transcode pipeline using FastAPI and Celery.

## Development Setup

There are two primary ways to run the project locally: fully containerized via Docker, or completely native on your host machine.

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

### Option 2: Full Native Setup (Recommended for Dev)

If you prefer to run the entire stack locally without Docker (for faster reloading and easier debugging), you must install the application, `ffmpeg`, Postgres, and Redis directly on your host machine.

1. Install System Dependencies (macOS via Homebrew)
   ```bash
   brew install ffmpeg postgresql redis
   ```

2. Start background services:
   ```bash
   brew services start postgresql
   brew services start redis
   ```

3. Create the database and user (if not already set up):
   ```bash
   psql postgres -c "CREATE USER veditor WITH PASSWORD 'password';"
   psql postgres -c "CREATE DATABASE veditor OWNER veditor;"
   ```

4. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```
   *(Ensure the `POSTGRES_*` and `REDIS_URL` variables point to your local native instances).*

5. Create a virtual environment and install dependencies using [uv](https://github.com/astral-sh/uv):
   ```bash
   uv venv
   source .venv/bin/activate
   uv sync
   uv run pre-commit install
   ```

6. Start the FastAPI server natively:
   ```bash
   uv run uvicorn app.main:app --reload
   ```

7. Start the Celery worker natively (in a separate terminal):
   ```bash
   uv run celery -A app.tasks worker --loglevel=info
   ```

8. Run the tests natively:
   ```bash
   uv run pytest
   ```
