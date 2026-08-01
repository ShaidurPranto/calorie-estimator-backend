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
# uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2




# the api works properly but the ui gets stuck , ui fetches the top and side segments and shows them properly , then in ideal scenario it is expected to show the name of the label for each of segment after fetching the classification results...but it does not do that, it does not show labels for the classified segments , and also does not remove masks from segments that are not classified i mean that are not under any category in classification result . But the ui shows the final result of volume like this is the amount of food present and this is the volume