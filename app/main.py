from fastapi import FastAPI
from app.routes import ops

app = FastAPI(title="VEditor API")

app.include_router(ops.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
