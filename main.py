from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="Akatsuki Extractor Service",
    description="Microservice for extracting images and URLs from documents via QStash webhooks.",
    version="1.0.0"
)

app.include_router(router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "ok"}