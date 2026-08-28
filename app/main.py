from fastapi import FastAPI

from app.queue import redis_conn
from app.routes import ops, talks

app = FastAPI(title="VEditor API")

app.include_router(ops.router)
app.include_router(talks.router)


@app.get("/health")
def health_check():
    redis_conn.ping()
    return {"status": "ok"}
