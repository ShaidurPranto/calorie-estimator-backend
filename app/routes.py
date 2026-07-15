import json
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import glob
from fastapi.responses import FileResponse
import numpy as np

from app.main import app, WORKING_DIR
from app.helpers import (
    _safe_extension,
    _save_upload_file,
    clean_working_directory,
    analyze_food_volume,
    display_food_views,
    get_npy_files,
    get_subfolders_with_npy,
    _clear_existing_files,
    clean_working_directory_all
)



@app.get("/")
def root():
    """Redirect to the UI test page if present, otherwise return a short message."""
    return {"message": "server is running"}


@app.get("/test")
async def test_api():
    """Test endpoint for API validation."""
    return JSONResponse({"ok": True, "message": "API is working correctly."})


################################
################################
################################
# basic apis to make estimation
################################
################################
################################


@app.post("/upload/top")
async def upload_top(file: UploadFile = File(...)):
    """Upload the top view image, delete any existing top images, and save the new one."""
    ext = _safe_extension(file.filename)
    target_dir = WORKING_DIR / "input_images"
    dest = target_dir / f"top{ext}"
    
    # 1. Clear out any old 'top' images (e.g., top.png, top.jpeg)
    _clear_existing_files(target_dir, "top")
    
    # 2. Save the new file
    await _save_upload_file(file, dest)
    
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.post("/upload/side")
async def upload_side(file: UploadFile = File(...)):
    """Upload the side view image, delete any existing side images, and save the new one."""
    ext = _safe_extension(file.filename)
    target_dir = WORKING_DIR / "input_images"
    dest = target_dir / f"side{ext}"
    
    # 1. Clear out any old 'side' images (e.g., side.png, side.jpeg)
    _clear_existing_files(target_dir, "side")
    
    # 2. Save the new file
    await _save_upload_file(file, dest)
    
    return JSONResponse({"ok": True, "saved_as": str(dest)})


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
        # display_food_views(WORKING_DIR / "input_images")
        final_output_path = WORKING_DIR / "final_nutrition_output.json"
        analyze_food_volume(WORKING_DIR / "food_volumes_summary.json", final_output_path)

        # Ensure the file exists before reading it
        if not final_output_path.exists():
            raise FileNotFoundError(f"Expected output file missing at {final_output_path}")

        # Read the generated JSON file
        with open(final_output_path, "r") as f:
            nutrition_data = json.load(f)

        # delete the outputs of working directory
        # clean_working_directory_all()

        # Return the success message along with the loaded JSON data
        return JSONResponse({
            "ok": True, 
            "message": "Processing completed successfully",
            "data": nutrition_data
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


################################
################################
################################
# results of processing
################################
################################
################################


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

    progress_dir = WORKING_DIR / "progress"
    done_file = progress_dir / "segmentation_top.json"

    if not progress_dir.exists() or not done_file.exists():
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

    progress_dir = WORKING_DIR / "progress"
    done_file = progress_dir / "segmentation_side.json"

    if not progress_dir.exists() or not done_file.exists():
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

    progress_dir = WORKING_DIR / "progress"
    done_file = progress_dir / "classification_top.json"

    if not progress_dir.exists() or not done_file.exists():
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

    progress_dir = WORKING_DIR / "progress"
    done_file = progress_dir / "classification_side.json"

    if not progress_dir.exists() or not done_file.exists():
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


################################
################################
################################
# fetching numpy file content
################################
################################
################################


@app.get("/result/segmentation/top/content/{filename}")
async def get_top_segmentation_file_content(filename: str):
    """
    Load a specific segmentation .npy file from:
    working/segmentation-outputs/masks/top
    and return its contents as a JSON response.
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

    try:
        # Load the numpy array from disk
        # allow_pickle=False is a good security practice if you're just loading standard arrays
        array_data = np.load(target_file, allow_pickle=False)
        
        # Convert the numpy array to a standard nested Python list so it can be JSON serialized
        mask_list = array_data.tolist()
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading or parsing the segmentation file: {str(e)}"
        )

    return JSONResponse({
        "ok": True,
        "filename": filename,
        "mask": mask_list
    })



@app.get("/result/segmentation/side/content/{filename}")
async def get_side_segmentation_file_content(filename: str):
    """
    Load a specific segmentation .npy file from:
    working/segmentation-outputs/masks/side
    and return its contents as a JSON response.
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

    try:
        array_data = np.load(target_file, allow_pickle=False)
        mask_list = array_data.tolist()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading the segmentation file: {str(e)}"
        )

    return JSONResponse({
        "ok": True,
        "filename": filename,
        "mask": mask_list
    })


@app.get("/result/classification/top/content/{category}/{filename}")
async def get_top_classification_file_content(category: str, filename: str):
    """
    Load a specific classified .npy file from:
    working/categorized_top_npy/<category>/
    and return its contents as a JSON response.
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

    try:
        array_data = np.load(target_file, allow_pickle=False)
        mask_list = array_data.tolist()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading the classification file: {str(e)}"
        )

    return JSONResponse({
        "ok": True,
        "category": category,
        "filename": filename,
        "mask": mask_list
    })


@app.get("/result/classification/side/content/{category}/{filename}")
async def get_side_classification_file_content(category: str, filename: str):
    """
    Download a specific classified .npy file from:
    working/categorized_side_npy/<category>/<filename>
    and return its contents as a JSON response.
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

    try:
        array_data = np.load(target_file, allow_pickle=False)
        mask_list = array_data.tolist()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading the classification file: {str(e)}"
        )

    return JSONResponse({
        "ok": True,
        "category": category,
        "filename": filename,
        "mask": mask_list
    })


################################
################################
################################
# fetching actual numpy file
################################
################################
################################

# @app.get("/result/segmentation/top/{filename}")
# async def get_top_segmentation_file(filename: str):
#     """
#     Download a specific segmentation .npy file from:
#     working/segmentation-outputs/masks/top
#     """

#     if not filename.endswith(".npy"):
#         raise HTTPException(
#             status_code=400,
#             detail="Only .npy files are allowed."
#         )

#     target_file = (
#         WORKING_DIR
#         / "segmentation-outputs"
#         / "masks"
#         / "top"
#         / filename
#     )

#     if not target_file.exists():
#         raise HTTPException(
#             status_code=404,
#             detail=f"File '{filename}' not found."
#         )

#     return FileResponse(
#         path=target_file,
#         filename=filename,
#         media_type="application/octet-stream"
#     )


# @app.get("/result/segmentation/side/{filename}")
# async def get_side_segmentation_file(filename: str):
#     """
#     Download a specific segmentation .npy file from:
#     working/segmentation-outputs/masks/side
#     """

#     if not filename.endswith(".npy"):
#         raise HTTPException(
#             status_code=400,
#             detail="Only .npy files are allowed."
#         )

#     target_file = (
#         WORKING_DIR
#         / "segmentation-outputs"
#         / "masks"
#         / "side"
#         / filename
#     )

#     if not target_file.exists():
#         raise HTTPException(
#             status_code=404,
#             detail=f"File '{filename}' not found."
#         )

#     return FileResponse(
#         path=target_file,
#         filename=filename,
#         media_type="application/octet-stream"
#     )



# @app.get("/result/classification/top/{category}/{filename}")
# async def get_top_classification_file(
#     category: str,
#     filename: str
# ):
#     """
#     Download a specific classified .npy file from:
#     working/categorized_top_npy/<category>/
#     """

#     if not filename.endswith(".npy"):
#         raise HTTPException(
#             status_code=400,
#             detail="Only .npy files are allowed."
#         )

#     target_file = (
#         WORKING_DIR
#         / "categorized_top_npy"
#         / category
#         / filename
#     )

#     if not target_file.exists():
#         raise HTTPException(
#             status_code=404,
#             detail=f"File '{filename}' not found in category '{category}'."
#         )

#     return FileResponse(
#         path=target_file,
#         filename=filename,
#         media_type="application/octet-stream"
#     )


# @app.get("/result/classification/side/{category}/{filename}")
# async def get_side_classification_file(
#     category: str,
#     filename: str
# ):
#     """
#     Download a specific classified .npy file from:
#     working/categorized_side_npy/<category>/<filename>
#     """

#     if not filename.endswith(".npy"):
#         raise HTTPException(
#             status_code=400,
#             detail="Only .npy files are allowed."
#         )

#     target_file = (
#         WORKING_DIR
#         / "categorized_side_npy"
#         / category
#         / filename
#     )

#     if not target_file.exists():
#         raise HTTPException(
#             status_code=404,
#             detail=f"File '{filename}' not found in category '{category}'."
#         )

#     return FileResponse(
#         path=target_file,
#         filename=filename,
#         media_type="application/octet-stream"
#     )