import json
from fastapi import UploadFile, File, HTTPException, BackgroundTasks
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
# pipeline state
################################
################################
################################

# The stages a workflow module can mark complete by dropping a
# working/progress/<stage>.json file. This list only exists so /result/state
# can return a stable set of keys — completion itself is decided purely by
# whether the file exists on disk, nothing else is tracked or inferred.
KNOWN_STAGES = [
    "segmentation_top",
    "segmentation_side",
    "thumb_top",
    "thumb_side",
    "classification_top",
    "classification_side",
    "volume",
]


def _progress_dir() -> Path:
    return WORKING_DIR / "progress"


def _stage_done(stage: str) -> bool:
    """A stage is done if and only if working/progress/<stage>.json exists."""
    return (_progress_dir() / f"{stage}.json").exists()


def _completed_stages() -> list:
    """Every *.json file currently sitting in working/progress, as stage names."""
    progress_dir = _progress_dir()
    if not progress_dir.exists():
        return []
    return sorted(p.stem for p in progress_dir.glob("*.json"))


def _run_pipeline_background():
    """Runs the full pipeline sequentially in the background.

    Each workflow module (seg_main, thumb_main, class_main, vol_main) is
    expected to write its own working/progress/<stage>.json marker file the
    moment it finishes — that marker file is the entire state mechanism.
    This function just drives the sequence; it doesn't track or persist any
    status of its own.
    """
    from app.workflows.segmentation_workflow import seg_main
    seg_main()

    from app.workflows.thumb_workflow import thumb_main
    thumb_main()

    from app.workflows.classification_workflow import class_main
    class_main()

    from app.workflows.volume_workflow import vol_main
    vol_main()

    final_output_path = WORKING_DIR / "final_nutrition_output.json"
    analyze_food_volume(WORKING_DIR / "food_volumes_summary.json", final_output_path)


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
async def process(background_tasks: BackgroundTasks):
    """Check if both top and side images exist, queue the full processing
    workflow to run in the background, and return immediately.

    Poll GET /result/state to see which stages have finished, and call
    GET /volume-estimation once the 'volume' stage is done to get the report.

    Returns:
        - {"ok": True, "message": "..."} immediately, once the job is queued
        - 400 error if either image is missing
    """
    top_files = glob.glob(str(WORKING_DIR / "input_images" / "top.*"))
    side_files = glob.glob(str(WORKING_DIR / "input_images" / "side.*"))

    if not top_files:
        raise HTTPException(status_code=400, detail="Top image not found in input_images folder")
    if not side_files:
        raise HTTPException(status_code=400, detail="Side image not found in input_images folder")

    # delete everything from /working except /working/input_images
    # (this also clears out working/progress from any previous run)
    clean_working_directory()

    background_tasks.add_task(_run_pipeline_background)

    return JSONResponse({
        "ok": True,
        "message": "Processing has been started in the background.",
        "check_state_at": "/result/state",
        "result_at": "/volume-estimation",
    })


@app.get("/result/state")
async def get_state():
    """Scans working/progress for *.json marker files and reports back
    exactly what's there — nothing is inferred or tracked beyond that.
    """
    completed = _completed_stages()
    stages = {name: (name in completed) for name in KNOWN_STAGES}
    return JSONResponse({
        "ok": True,
        "completed_stages": completed,
        "stages": stages,
    })


@app.get("/volume-estimation")
async def volume_estimation():
    """Returns the final nutrition report — the same payload /process used
    to return directly before processing became asynchronous.

    Checks working/progress/volume.json first; if it doesn't exist yet,
    responds with 202 and the current list of completed stages instead of
    the report.
    """
    if not _stage_done("volume"):
        return JSONResponse(
            status_code=202,
            content={
                "ok": False,
                "message": "Volume estimation has not completed yet.",
                "completed_stages": _completed_stages(),
            },
        )

    final_output_path = WORKING_DIR / "final_nutrition_output.json"
    if not final_output_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"volume.json marker exists but expected output file missing at {final_output_path}",
        )

    with open(final_output_path, "r") as f:
        nutrition_data = json.load(f)

    return JSONResponse({
        "ok": True,
        "message": "Processing completed successfully",
        "data": nutrition_data,
    })


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
    if not _stage_done("segmentation_top"):
        raise HTTPException(status_code=404, detail="Top segmentation has not completed yet.")

    target_dir = WORKING_DIR / "segmentation-outputs" / "masks" / "top"
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
    if not _stage_done("segmentation_side"):
        raise HTTPException(status_code=404, detail="Side segmentation has not completed yet.")

    target_dir = WORKING_DIR / "segmentation-outputs" / "masks" / "side"
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

    This is a listing endpoint only — it tells you which of the segmentation
    filenames (already fetched from /result/segmentation/top) belong to
    which predicted category. It does not re-serve mask content; the
    segmentation content endpoint already gave you that.
    """
    if not _stage_done("classification_top"):
        raise HTTPException(status_code=404, detail="Top classification has not completed yet.")

    target_dir = WORKING_DIR / "categorized_top_npy"
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

    Listing endpoint only — see note on /result/classification/top.
    """
    if not _stage_done("classification_side"):
        raise HTTPException(status_code=404, detail="Side classification has not completed yet.")

    target_dir = WORKING_DIR / "categorized_side_npy"
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

# NOTE: there is deliberately no equivalent "fetch classification file
# content" endpoint. Every mask that classification groups into a category
# is one of the files segmentation already produced — the client fetches
# mask content once, from these segmentation endpoints, and classification
# is only ever used to look up which of those already-fetched files
# belongs to which category (or no category at all).


@app.get("/result/segmentation/top/content/{filename}")
async def get_top_segmentation_file_content(filename: str):
    """
    Load a specific segmentation .npy file from:
    working/segmentation-outputs/masks/top
    and return its contents as a JSON response.
    """
    if not filename.endswith(".npy"):
        raise HTTPException(status_code=400, detail="Only .npy files are allowed.")

    if not _stage_done("segmentation_top"):
        raise HTTPException(status_code=404, detail="Top segmentation has not completed yet.")

    target_file = WORKING_DIR / "segmentation-outputs" / "masks" / "top" / filename

    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    try:
        array_data = np.load(target_file, allow_pickle=False)
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
        raise HTTPException(status_code=400, detail="Only .npy files are allowed.")

    if not _stage_done("segmentation_side"):
        raise HTTPException(status_code=404, detail="Side segmentation has not completed yet.")

    target_file = WORKING_DIR / "segmentation-outputs" / "masks" / "side" / filename

    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    try:
        array_data = np.load(target_file, allow_pickle=False)
        mask_list = array_data.tolist()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading the segmentation file: {str(e)}")

    return JSONResponse({
        "ok": True,
        "filename": filename,
        "mask": mask_list
    })