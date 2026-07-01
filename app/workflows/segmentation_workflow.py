import os
import json
import math
import time
import sys
import gc
from pathlib import Path

import numpy as np
import torch

BASE_DIR = Path(__file__).resolve().parents[1]
MODULES_DIR = BASE_DIR / "modules"
WORK_DIR = BASE_DIR / "working"

if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from app.modules.segmentation_module import SegmentationModule


def seg_main():
    """
    Main function to run batch segmentation on all images in INPUT_DIR
    and display the results.
    """
    # =============================
    # CONFIGURATION
    # =============================
    INPUT_DIR  = str(WORK_DIR / "input_images")
    OUTPUT_DIR = str(WORK_DIR / "segmentation-outputs")

    CHECKPOINT   = str(BASE_DIR / "models" / "segmentation" / "checkpoints" / "sam2_hiera_large.pt")
    MODEL_CONFIG = "configs/sam2/sam2_hiera_l.yaml"
    DEVICE       = "cuda" if torch.cuda.is_available() else "cpu"

    SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png")

    coords_dir   = os.path.join(OUTPUT_DIR, "coordinates")
    masks_dir    = os.path.join(OUTPUT_DIR, "masks")
    segments_dir = os.path.join(OUTPUT_DIR, "segments")

    for d in [coords_dir, masks_dir, segments_dir]:
        os.makedirs(d, exist_ok=True)

    print(f"Input      : {INPUT_DIR}")
    print(f"Output     : {OUTPUT_DIR}")
    print(f"Device     : {DEVICE}")
    print(f"Checkpoint : {CHECKPOINT}")
    print(f"Exists     : {os.path.exists(CHECKPOINT)}")

    # =============================
    # INSTANTIATE
    # =============================
    print("\nInitializing SegmentationModule...")
    runtime_device = DEVICE

    def _create_segmenter(device_name: str) -> SegmentationModule:
        module = SegmentationModule(
            checkpoint=CHECKPOINT,
            model_config=MODEL_CONFIG,
            device=device_name,
        )
        module.min_area_ratio = 0.02
        module.min_mask_region_area = 100
        module.dedup_iou_threshold = 0.5
        return module

    seg = _create_segmenter(runtime_device)
    print("✓ Model loaded and ready.")

    # =============================
    # BATCH PROCESSING LOOP
    # =============================
    image_files = [
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(SUPPORTED_EXTENSIONS)
    ]
    print(f"\nFound {len(image_files)} images in {INPUT_DIR}\n")

    total_start = time.time()

    for filename in image_files:
        image_path = os.path.join(INPUT_DIR, filename)
        base_name  = os.path.splitext(filename)[0]

        print(f"Processing: {filename}")
        t0 = time.time()

        retried_on_cpu = False

        while True:
            try:
                img_coords_dir   = os.path.join(coords_dir,   base_name)
                img_masks_dir    = os.path.join(masks_dir,    base_name)
                img_segments_dir = os.path.join(segments_dir, base_name)
                for d in [img_coords_dir, img_masks_dir, img_segments_dir]:
                    os.makedirs(d, exist_ok=True)

                seg.set_image_from_path(image_path)

                # 1. COORDINATES → JSON
                coordinates = seg.get_coordinates()
                for coord in coordinates:
                    sid      = coord["segment_id"]
                    out_path = os.path.join(img_coords_dir, f"{base_name}_coord_{sid:03d}.json")
                    with open(out_path, "w") as f:
                        json.dump(coord, f, indent=4)
                print(f"  ✔ Coordinates saved  ({len(coordinates)} segments)")

                # 2. MASKS → NPY
                masks = seg.get_masks()
                for mask_data in masks:
                    sid      = mask_data["segment_id"]
                    out_path = os.path.join(img_masks_dir, f"{base_name}_mask_{sid:03d}.npy")
                    np.save(out_path, mask_data["mask"])
                print(f"  ✔ Masks saved        ({len(masks)} segments)")

                # 3. SEGMENTS → PNG
                segments = seg.get_segments()
                for segment in segments:
                    sid      = segment["segment_id"]
                    out_path = os.path.join(img_segments_dir, f"{base_name}_segment_{sid:03d}.png")
                    segment["image"].save(out_path)
                print(f"  ✔ Segments saved     ({len(segments)} segments)")
                break
            except torch.OutOfMemoryError:
                if runtime_device == "cuda" and not retried_on_cpu:
                    print("  ⚠ CUDA OOM encountered. Falling back to CPU and retrying this image...")
                    try:
                        seg.clear_cache()
                    except Exception:
                        pass
                    del seg
                    gc.collect()
                    torch.cuda.empty_cache()
                    runtime_device = "cpu"
                    seg = _create_segmenter(runtime_device)
                    retried_on_cpu = True
                    continue
                raise

        elapsed = time.time() - t0
        print(f"  ⏱  {elapsed:.2f}s\n")

        seg.clear_cache()

    total_elapsed = time.time() - total_start
    print(f"All done! Total time: {total_elapsed:.2f}s")
    print(f"Output written to: {OUTPUT_DIR}")

    # =============================
    # DISPLAY RESULTS
    # =============================
    if hasattr(seg, "display_all_segments"):
        seg.display_all_segments(INPUT_DIR, segments_dir)
