from fastapi import FastAPI
from pathlib import Path

app = FastAPI(title="Calorie Estimator")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APP_DIR = Path(__file__).resolve().parent
WORKING_DIR = APP_DIR / "working" 
WORKING_DIR.mkdir(parents=True, exist_ok=True)

from app import routes

if __name__ == "__main__":
    # Simple launcher for manual tests
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


# lt --port 8000 --subdomain calorie
# uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
