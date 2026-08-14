# VEditor

Standalone, reusable video-review/transcode pipeline using FastAPI and Celery.

## Development Setup

The project is designed to be run fully containerized via Docker, ensuring all system dependencies (like `ffmpeg`) and data stores (Postgres, Redis) are isolated and consistent.

### Docker Setup

To run the entire stack (API, Celery Worker, Postgres, Redis):

1. Copy the environment variables:
   ```bash
   cp .env.example .env
   ```

2. Start the services:
   ```bash
   docker compose up -d --build
   ```

3. Check the API health to verify everything is running:
   ```bash
   curl http://localhost:8000/health
   ```
