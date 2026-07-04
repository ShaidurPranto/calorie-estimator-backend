import json
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import glob
from fastapi.responses import FileResponse

from app.main import app, WORKING_DIR
from app.helpers import (
    _safe_extension,
    _save_upload_file,
    clean_working_directory,
    analyze_food_volume,
    display_food_views,
    get_npy_files,
    get_subfolders_with_npy
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


@app.get("/result/segmentation/top")
async def get_top_segmentation_results():
    """
    Returns all .npy mask files from:
    working/segmentation-outputs/masks/top
    """

    target_dir = (
        WORKING_DIR
        / "segmentation-outputs"
        / "masks"
        / "top"
    )

    if not target_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {target_dir}"
        )

    npy_files = get_npy_files(target_dir)

    return JSONResponse({
        "ok": True,
        "directory": str(target_dir.relative_to(WORKING_DIR)),
        "count": len(npy_files),
        "files": npy_files
    })

@app.get("/result/segmentation/side")
async def get_side_segmentation_results():
    """
    Returns all .npy mask files from:
    working/segmentation-outputs/masks/side
    """

    target_dir = (
        WORKING_DIR
        / "segmentation-outputs"
        / "masks"
        / "side"
    )

    if not target_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {target_dir}"
        )

    npy_files = get_npy_files(target_dir)

    return JSONResponse({
        "ok": True,
        "directory": str(target_dir.relative_to(WORKING_DIR)),
        "count": len(npy_files),
        "files": npy_files
    })


@app.get("/result/classification/top")
async def get_top_classification_results():
    """
    Returns all subfolders and their .npy files from:
    working/categorized_top_npy
    """

    target_dir = (
        WORKING_DIR
        / "categorized_top_npy"
    )

    if not target_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {target_dir}"
        )

    categorized_files = get_subfolders_with_npy(target_dir)

    return JSONResponse({
        "ok": True,
        "directory": str(target_dir.relative_to(WORKING_DIR)),
        "categories": categorized_files
    })


@app.get("/result/classification/side")
async def get_side_classification_results():
    """
    Returns all subfolders and their .npy files from:
    working/categorized_side_npy
    """

    target_dir = (
        WORKING_DIR
        / "categorized_side_npy"
    )

    if not target_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {target_dir}"
        )

    categorized_files = get_subfolders_with_npy(target_dir)

    return JSONResponse({
        "ok": True,
        "directory": str(target_dir.relative_to(WORKING_DIR)),
        "categories": categorized_files
    })


@app.get("/result/segmentation/top/{filename}")
async def get_top_segmentation_file(filename: str):
    """
    Download a specific segmentation .npy file from:
    working/segmentation-outputs/masks/top
    """

    if not filename.endswith(".npy"):
        raise HTTPException(
            status_code=400,
            detail="Only .npy files are allowed."
        )

    target_file = (
        WORKING_DIR
        / "segmentation-outputs"
        / "masks"
        / "top"
        / filename
    )

    if not target_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found."
        )

    return FileResponse(
        path=target_file,
        filename=filename,
        media_type="application/octet-stream"
    )


@app.get("/result/segmentation/side/{filename}")
async def get_side_segmentation_file(filename: str):
    """
    Download a specific segmentation .npy file from:
    working/segmentation-outputs/masks/side
    """

    if not filename.endswith(".npy"):
        raise HTTPException(
            status_code=400,
            detail="Only .npy files are allowed."
        )

    target_file = (
        WORKING_DIR
        / "segmentation-outputs"
        / "masks"
        / "side"
        / filename
    )

    if not target_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found."
        )

    return FileResponse(
        path=target_file,
        filename=filename,
        media_type="application/octet-stream"
    )



@app.get("/result/classification/top/{category}/{filename}")
async def get_top_classification_file(
    category: str,
    filename: str
):
    """
    Download a specific classified .npy file from:
    working/categorized_top_npy/<category>/
    """

    if not filename.endswith(".npy"):
        raise HTTPException(
            status_code=400,
            detail="Only .npy files are allowed."
        )

    target_file = (
        WORKING_DIR
        / "categorized_top_npy"
        / category
        / filename
    )

    if not target_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found in category '{category}'."
        )

    return FileResponse(
        path=target_file,
        filename=filename,
        media_type="application/octet-stream"
    )


@app.get("/result/classification/side/{category}/{filename}")
async def get_side_classification_file(
    category: str,
    filename: str
):
    """
    Download a specific classified .npy file from:
    working/categorized_side_npy/<category>/<filename>
    """

    if not filename.endswith(".npy"):
        raise HTTPException(
            status_code=400,
            detail="Only .npy files are allowed."
        )

    target_file = (
        WORKING_DIR
        / "categorized_side_npy"
        / category
        / filename
    )

    if not target_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found in category '{category}'."
        )

    return FileResponse(
        path=target_file,
        filename=filename,
        media_type="application/octet-stream"
    )