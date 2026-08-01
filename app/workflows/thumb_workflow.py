import json
from pathlib import Path
from app.modules.thumb_module import FingerDetectorAndCalibrator, CALIBRATION_PKG_DIR, WORK_DIR
import os


def create_json_file(directory_path, file_name):
    """Creates an empty .json file with the given name in the specified directory."""
    # Ensure the file name ends with .json
    if not file_name.endswith(".json"):
        file_name += ".json"

    # Combine the directory path and file name safely
    file_path = os.path.join(directory_path, file_name)

    # Optional: Create the directory if it doesn't exist yet
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    # Write an empty JSON object ({}) to the file
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump({}, json_file)

    print(f"Successfully created: {file_path}")


def thumb_main():
    """Run thumb detection and calibration for top and side segmented folders."""
    # Set segmented images for top and side views
    BASE_DIR = Path(__file__).resolve().parents[1]
    SEGMENTED_TOP_DIR = BASE_DIR / "working" / "segmentation-outputs" / "segments" / "top"
    SEGMENTED_SIDE_DIR = BASE_DIR / "working" / "segmentation-outputs" / "segments" / "side"
    MODEL_PATH = CALIBRATION_PKG_DIR / 'finger_detector.joblib'
    ALLOW_LOW_CONFIDENCE = True

    # Create and load the module once
    module = FingerDetectorAndCalibrator()
    module.load_model(MODEL_PATH)

    # Process both views using the method defined in the module
    result_top = module.process_view(
        'top',
        SEGMENTED_TOP_DIR,
        allow_low_confidence=ALLOW_LOW_CONFIDENCE,
        work_dir=WORK_DIR,
    )

    # progresss tracking code block
    progress_dir = os.path.join(WORK_DIR, "progress")
    create_json_file(progress_dir, f"thumb_top.json")
    print(f"file created: thumb_top.json")

    result_side = module.process_view(
        'side',
        SEGMENTED_SIDE_DIR,
        allow_low_confidence=ALLOW_LOW_CONFIDENCE,
        work_dir=WORK_DIR,
    )

    # progresss tracking code block
    progress_dir = os.path.join(WORK_DIR, "progress")
    create_json_file(progress_dir, f"thumb_side.json")
    print(f"file created: thumb_side.json")

    print('Top cm_per_pixel:', result_top['calibration']['cm_per_pixel'])
    print('Side cm_per_pixel:', result_side['calibration']['cm_per_pixel'])

