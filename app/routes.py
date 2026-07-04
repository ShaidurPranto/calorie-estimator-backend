import json
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import glob

from app.main import app, WORKING_DIR
from app.helpers import (
    _safe_extension,
    _save_upload_file,
    clean_working_directory,
    analyze_food_volume,
    display_food_views,
)


@app.get("/test")
async def test_api():
    """Test endpoint for API validation."""
    return JSONResponse({"ok": True, "message": "API is working correctly."})


@app.post("/upload/top")
async def upload_top(file: UploadFile = File(...)):
    """Upload the top view image and save as `top<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / "input_images" / f"top{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.post("/upload/side")
async def upload_side(file: UploadFile = File(...)):
    """Upload the side view image and save as `side<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / "input_images" / f"side{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.get("/")
def root():
    """Redirect to the UI test page if present, otherwise return a short message."""
    return {"message": "server is running"}


@app.post("/process")
async def process():
    """Check if both top and side images exist, then run full processing workflow.
    
    Returns:
        - {"ok": True, "message": "Processing completed"} on success
        - 400 error if either image is missing
        - 500 error if processing fails
    """
    # Check if both top and side images exist
    top_files = glob.glob(str(WORKING_DIR / "input_images" / "top.*"))
    side_files = glob.glob(str(WORKING_DIR / "input_images" / "side.*"))
    
    if not top_files:
        raise HTTPException(status_code=400, detail="Top image not found in input_images folder")
    if not side_files:
        raise HTTPException(status_code=400, detail="Side image not found in input_images folder")
    

    # delete everything from /working except /working/input_images
    clean_working_directory()

    
    try:
        # Import and run the segmentation workflow
        from app.workflows.segmentation_workflow import seg_main
        seg_main()

        # Import and run thumb workflow
        from app.workflows.thumb_workflow import thumb_main
        thumb_main()

        # Import and run classifier workflow
        from app.workflows.classification_workflow import class_main
        class_main()

        # Import and run volume workflow
        from app.workflows.volume_workflow import vol_main
        vol_main()

        # Generate final output
        display_food_views(WORKING_DIR / "input_images")
        final_output_path = WORKING_DIR / "final_nutrition_output.json"
        analyze_food_volume(WORKING_DIR / "food_volumes_summary.json", final_output_path)

        # Ensure the file exists before reading it
        if not final_output_path.exists():
            raise FileNotFoundError(f"Expected output file missing at {final_output_path}")

        # Read the generated JSON file
        with open(final_output_path, "r") as f:
            nutrition_data = json.load(f)

        # Return the success message along with the loaded JSON data
        return JSONResponse({
            "ok": True, 
            "message": "Processing completed successfully",
            "data": nutrition_data
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

