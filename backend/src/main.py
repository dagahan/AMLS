from fastapi import FastAPI
from loguru import logger
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Monolith API")

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up the monolith backend...")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Running monolith on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
