from pathlib import Path
from app.modules.thumb_module import FingerDetectorAndCalibrator, CALIBRATION_PKG_DIR, WORK_DIR


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
    result_side = module.process_view(
        'side',
        SEGMENTED_SIDE_DIR,
        allow_low_confidence=ALLOW_LOW_CONFIDENCE,
        work_dir=WORK_DIR,
    )

    print('Top cm_per_pixel:', result_top['calibration']['cm_per_pixel'])
    print('Side cm_per_pixel:', result_side['calibration']['cm_per_pixel'])

