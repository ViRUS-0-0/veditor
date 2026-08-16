from fastapi import FastAPI

app = FastAPI(title="VEditor API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
