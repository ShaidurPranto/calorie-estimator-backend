# Cell 1: Class definition
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Define Kaggle dataset paths
BASE_DIR = Path(__file__).resolve().parents[1]
DATASET_ROOT = BASE_DIR / "models" / "thumb"
CALIBRATION_PKG_DIR = DATASET_ROOT / 'calibration'

WORK_DIR = BASE_DIR / "working"
WORK_DIR.mkdir(parents=True, exist_ok=True)


if str(DATASET_ROOT) not in sys.path:
    sys.path.insert(0, str(DATASET_ROOT))

from calibration.calibration import CalibrationResult, calibrate_from_image
from calibration.modeling import FingerOneClassDetector

class FingerDetectorAndCalibrator:

    def __init__(self, *, finger_length_cm: float = 6.0, finger_width_cm: float = 1.5) -> None:
        if finger_length_cm <= 0 or finger_width_cm <= 0:
            raise ValueError("finger_length_cm and finger_width_cm must be positive.")
        self.finger_length_cm = float(finger_length_cm)
        self.finger_width_cm = float(finger_width_cm)
        self.detector: FingerOneClassDetector | None = None

    def load_model(
        self,
        model_path: str | Path,
        *,
        device: str | None = None,
    ) -> FingerOneClassDetector:
        """Load and store the trained finger detector model."""
        self.detector = FingerOneClassDetector.load(model_path, device=device)
        return self.detector

    def _require_detector(self) -> FingerOneClassDetector:
        if self.detector is None:
            raise RuntimeError("Model is not loaded. Call load_model() first.")
        return self.detector

    def detect_finger(
        self,
        segmented_dir: str | Path,
        *,
        allow_low_confidence: bool = False,
    ) -> Dict[str, Any]:
        """Detect the most likely finger image from segmented outputs."""
        detector = self._require_detector()

        image_paths = detector.list_images(segmented_dir)
        if not image_paths:
            raise ValueError(f"No images found in segmented_dir={segmented_dir}")

        scores: List[tuple[str, float]] = detector.batch_scores(image_paths)
        best_path, best_score = scores[0]
        threshold = float(detector.threshold)

        if best_score < threshold and not allow_low_confidence:
            raise RuntimeError(
                "No segmented image passed threshold. "
                f"best_score={best_score:.6f}, threshold={threshold:.6f}"
            )

        return {
            "chosen_finger_image": best_path,
            "chosen_image_score": best_score,
            "detector_threshold": threshold,
            "all_scores_desc": [{"path": p, "score": s} for p, s in scores],
        }

    def calibrate_finger_image(self, finger_image_path: str | Path) -> CalibrationResult:
        """Calibrate pixel scale from a chosen finger image."""
        return calibrate_from_image(
            image_path=finger_image_path,
            finger_length_cm=self.finger_length_cm,
            finger_width_cm=self.finger_width_cm,
        )

    def detect_and_calibrate(
        self,
        segmented_dir: str | Path,
        *,
        allow_low_confidence: bool = False,
    ) -> Dict[str, Any]:
        """Run full flow: detect finger image, then calibrate it."""
        detection = self.detect_finger(
            segmented_dir=segmented_dir,
            allow_low_confidence=allow_low_confidence,
        )
        calibration = self.calibrate_finger_image(detection["chosen_finger_image"])

        result: Dict[str, Any] = {
            **detection,
            "calibration": calibration.to_dict(),
            "finger_length_cm": self.finger_length_cm,
            "finger_width_cm": self.finger_width_cm,
        }
        return result

    def process_view(
        self,
        view_name: str,
        segmented_dir: str | Path,
        *,
        allow_low_confidence: bool = False,
        work_dir: str | Path = WORK_DIR,
        cols: int = 4,
    ) -> Dict[str, Any]:
        """Plot all segmented images, run detect_and_calibrate, save outputs, copy non-chosen images, and plot the chosen image."""
        import math
        import shutil
        import matplotlib.pyplot as plt
        from PIL import Image

        segmented_dir = Path(segmented_dir)
        work_dir = Path(work_dir)

        detector = self._require_detector()
        image_paths = detector.list_images(segmented_dir)
        if not image_paths:
            raise ValueError(f"No images found in segmented_dir={segmented_dir}")

        rows = math.ceil(len(image_paths) / cols)
        fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
        axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]

        for ax, image_path in zip(axes, image_paths):
            img = Image.open(image_path)
            ax.imshow(img)
            ax.set_title(Path(image_path).name, fontsize=8)
            ax.axis('off')

        for ax in axes[len(image_paths):]:
            ax.axis('off')

        fig.suptitle(f"All segmented images ({view_name})", fontsize=14)
        plt.tight_layout()
        plt.show()

        result = self.detect_and_calibrate(
            segmented_dir=segmented_dir,
            allow_low_confidence=allow_low_confidence,
        )

        out_json = work_dir / f"{view_name}_view_finger_image_result.json"
        out_txt = work_dir / f"{view_name}_view_finger_image_cm_per_pixel.txt"
        out_json.write_text(json.dumps(result, indent=2), encoding='utf-8')
        out_txt.write_text(f"{result['calibration']['cm_per_pixel']:.12f}\n", encoding='utf-8')

        chosen_path = Path(result['chosen_finger_image'])
        out_folder = work_dir / f"{view_name}_segments"
        out_folder.mkdir(parents=True, exist_ok=True)

        for image_path in image_paths:
            image_path = Path(image_path)
            try:
                same_file = image_path.resolve() == chosen_path.resolve()
            except Exception:
                same_file = str(image_path) == str(chosen_path)
            if not same_file:
                shutil.copy2(image_path, out_folder / image_path.name)

        chosen_img = Image.open(chosen_path)
        plt.figure(figsize=(6, 6))
        plt.imshow(chosen_img)
        plt.title(f"Chosen finger image ({view_name}): {chosen_path.name}")
        plt.axis('off')
        plt.show()

        print(f"Saved JSON: {out_json}")
        print(f"Saved TXT: {out_txt}")
        print(f"Copied {len(list(out_folder.iterdir()))} images (excluding finger image) to {out_folder}")

        return result


def run_module(
    *,
    model_path: str | Path,
    segmented_dir: str | Path,
    finger_length_cm: float = 6.0,
    finger_width_cm: float = 1.5,
    allow_low_confidence: bool = False,
) -> Dict[str, Any]:
    """Functional helper for one-shot usage of the module wrapper."""
    module = FingerDetectorAndCalibrator(
        finger_length_cm=finger_length_cm,
        finger_width_cm=finger_width_cm,
    )
    module.load_model(model_path)
    return module.detect_and_calibrate(
        segmented_dir=segmented_dir,
        allow_low_confidence=allow_low_confidence,
    )