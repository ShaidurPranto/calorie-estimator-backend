from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import shutil
import os
import glob

from app.workflows.thumb_workflow import thumb_main

app = FastAPI(title="Calorie Estimator - Upload API")

# Working directory inside the app package where images should be saved
APP_DIR = Path(__file__).resolve().parent
WORKING_DIR = APP_DIR / "working" / "input_images"
WORKING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_extension(filename: str) -> str:
    """Return a safe extension (including leading dot) from the original filename.
    Falls back to `.jpg` when unknown.
    """
    ext = Path(filename).suffix
    if not ext:
        return ".jpg"
    # Keep only simple alphanumeric + dot extensions like .jpg, .png, .jpeg
    ext = ext.lower()
    if ext.startswith('.') and 1 < len(ext) <= 5:
        return ext
    return ".jpg"


async def _save_upload_file(upload: UploadFile, dest_path: Path) -> None:
    # Read and write in chunks to avoid large memory usage
    try:
        with dest_path.open("wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    finally:
        await upload.close()


def clean_working_directory():
    working_dir = Path("/working")
    keep_dir = working_dir / "input_images"

    # Ensure the base directory exists before attempting to loop
    if not working_dir.exists():
        print(f"Directory {working_dir} does not exist.")
        return

    # Iterate over everything inside /working
    for item in working_dir.iterdir():
        # Skip the directory we want to keep
        if item == keep_dir:
            continue
            
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()  # Deletes files or symlinks
            elif item.is_dir():
                shutil.rmtree(item)  # Deletes directories and their contents
            print(f"Deleted: {item}")
        except Exception as e:
            print(f"Failed to delete {item}. Reason: {e}")


@app.post("/upload/top")
async def upload_top(file: UploadFile = File(...)):
    """Upload the top view image and save as `top<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / f"top{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.post("/upload/side")
async def upload_side(file: UploadFile = File(...)):
    """Upload the side view image and save as `side<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / f"side{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


# Serve the simple frontend under /ui (ui/index.html)
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


@app.get("/")
def root():
    """Redirect to the UI test page if present, otherwise return a short message."""
    index = UI_DIR / "index.html"
    if index.exists():
        return RedirectResponse(url="/ui/index.html")
    return {"message": "Upload API available at /upload/top and /upload/side"}


@app.post("/process")
async def process():
    """Check if both top and side images exist, then run full processing workflow.
    
    Returns:
        - {"ok": True, "message": "Processing completed"} on success
        - 400 error if either image is missing
        - 500 error if processing fails
    """
    # Check if both top and side images exist
    top_files = glob.glob(str(WORKING_DIR / "top.*"))
    side_files = glob.glob(str(WORKING_DIR / "side.*"))
    
    if not top_files:
        raise HTTPException(status_code=400, detail="Top image not found in input_images folder")
    if not side_files:
        raise HTTPException(status_code=400, detail="Side image not found in input_images folder")
    

    # clear outputs from previous processing
    # delete everything from /working except /working/input_images
    # clean_working_directory()

    
    try:
        # Import and run the segmentation workflow
        # from app.workflows.segmentation_workflow import seg_main
        
        # # Call seg_main to run the segmentation
        # seg_main()

        # Import and run thumb workflow
        # from app.workflows.thumb_workflow import thumb_main
        
        # # Call thumb_main to run the thumbnail generation
        # thumb_main()

        # Import and run classifier workflow
        from app.workflows.classification_workflow import class_main
        class_main()

        return JSONResponse({"ok": True, "message": "Processing completed successfully"})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


if __name__ == "__main__":
    # Simple launcher for manual tests
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)
