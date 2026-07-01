import os
import re
import json
import shutil
from pathlib import Path
from typing import Tuple, Dict, Any, List

import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment
from app.modules import volume_module as module


def find_image_with_keyword(folder: Path, keyword: str) -> str:
    exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.gif')
    candidates = [f for f in os.listdir(folder)
                  if keyword.lower() in f.lower() and f.lower().endswith(exts)]
    if not candidates:
        raise FileNotFoundError(f"No image containing '{keyword}' found in {folder}")
    return candidates[0]


def collect_class_npy_paths(npy_root: Path) -> Dict[str, List[str]]:
    """Gathers classified .npy mask paths matching the directory hierarchy."""
    classes = {}
    if not npy_root.exists():
        print(f"⚠️  {npy_root} does not exist")
        return classes

    for class_dir in sorted(p for p in npy_root.iterdir() if p.is_dir()):
        npy_files = sorted(class_dir.glob("*.npy"))
        if npy_files:
            classes[class_dir.name] = [str(p) for p in npy_files]
    return classes


def build_paths_and_labels(class_to_paths: dict) -> Tuple[List[str], List[str]]:
    """Flattens class mappings into list inputs for module.parse_npy_segments."""
    npy_paths = []
    class_ids = []
    for class_name, paths in class_to_paths.items():
        for p in paths:
            npy_paths.append(p)
            class_ids.append(class_name)
    return npy_paths, class_ids


def vol_main():
    # ==========================================================================
    # CONFIGURATION — Clean Backend Relative Paths
    # ==========================================================================
    BASE_DIR = Path(__file__).resolve().parents[1]
    INPUT_FOOD_DIR = BASE_DIR / "working"
    INPUT_IMAGE_DIR = BASE_DIR / "working" / "input_images"

    OUTPUT_ROOT = BASE_DIR / "working"
    MASKS_ROOT = INPUT_FOOD_DIR / "segmentation-outputs"

    IMAGE_SIDE_FILENAME = find_image_with_keyword(INPUT_IMAGE_DIR, "side")
    IMAGE_TOP_FILENAME = find_image_with_keyword(INPUT_IMAGE_DIR, "top")

    MASKS_SIDE_DIR = MASKS_ROOT / "masks" / "side"
    MASKS_TOP_DIR = MASKS_ROOT / "masks" / "top"

    FILTERED_SIDE_DIR = INPUT_FOOD_DIR / "categorized_side"
    FILTERED_TOP_DIR = INPUT_FOOD_DIR / "categorized_top"

    FILTERED_SIDE_NPY_DIR = OUTPUT_ROOT / "categorized_side_npy"
    FILTERED_TOP_NPY_DIR = OUTPUT_ROOT / "categorized_top_npy"

    CM_PER_PIXEL_PATH = BASE_DIR / "working" / "side_view_finger_image_cm_per_pixel.txt"

    if not CM_PER_PIXEL_PATH.exists():
        raise FileNotFoundError(f"Calibration file missing at {CM_PER_PIXEL_PATH}")

    with open(CM_PER_PIXEL_PATH, "r") as f:
        cm_per_pixel = float(f.read().strip())

    PIXEL_LENGTH_MM = cm_per_pixel * 10
    VOXEL_SIZE_MM = 20

    # ==========================================================================
    # NESTED HELPERS
    # ==========================================================================
    def preview_inputs():
        print("\n" + "=" * 60)
        print("PRE-FLIGHT CHECK: input folders")
        print("=" * 60)

        for label, folder in [
            ("MASKS_SIDE_DIR", MASKS_SIDE_DIR),
            ("MASKS_TOP_DIR", MASKS_TOP_DIR),
            ("FILTERED_SIDE_DIR", FILTERED_SIDE_DIR),
            ("FILTERED_TOP_DIR", FILTERED_TOP_DIR),
        ]:
            if not Path(folder).exists():
                print(f"❌ {label}: {folder}  <-- DOES NOT EXIST")
                continue
            if "MASKS" in label:
                files = sorted(Path(folder).glob("*.npy"))
            else:
                files = sorted(f for f in Path(folder).rglob("*") if f.is_file())
            print(f"✅ {label}: {folder}  ({len(files)} files)")
            for f in files[:5]:
                print(f"      - {f.name}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more")

    def reorganize_masks():
        print("\n" + "=" * 60)
        print("STEP 0: Reorganizing .npy masks into classified folders")
        print("=" * 60)

        print("\n-- Side view --")
        module.organize_npy_files(
            source_folder=MASKS_SIDE_DIR,
            configuration_folder=FILTERED_SIDE_DIR,
            output_folder=FILTERED_SIDE_NPY_DIR,
        )

        print("\n-- Top view --")
        module.organize_npy_files(
            source_folder=MASKS_TOP_DIR,
            configuration_folder=FILTERED_TOP_DIR,
            output_folder=FILTERED_TOP_NPY_DIR,
        )

    # ==========================================================================
    # MAIN PIPELINE FLOW
    # ==========================================================================
    preview_inputs()
    reorganize_masks()

    # Fixed: Removed the incorrect 'module.' prefixes here
    side_classes = collect_class_npy_paths(FILTERED_SIDE_NPY_DIR)
    top_classes = collect_class_npy_paths(FILTERED_TOP_NPY_DIR)

    print("\nClasses found (side):", list(side_classes.keys()))
    print("Classes found (top) :", list(top_classes.keys()))

    # Fixed: Removed the incorrect 'module.' prefixes here
    side_npy_paths, side_class_ids = build_paths_and_labels(side_classes)
    top_npy_paths, top_class_ids = build_paths_and_labels(top_classes)

    print("\nLoading images...")
    image_side = module.load_image_file(os.path.join(INPUT_IMAGE_DIR, IMAGE_SIDE_FILENAME))
    image_top = module.load_image_file(os.path.join(INPUT_IMAGE_DIR, IMAGE_TOP_FILENAME))

    print("\nParsing masks for SIDE view...")
    segments_side = module.parse_npy_segments(
        image=image_side,
        npy_paths=side_npy_paths,
        class_ids=side_class_ids,
    )

    print("\nParsing masks for TOP view...")
    segments_top = module.parse_npy_segments(
        image=image_top,
        npy_paths=top_npy_paths,
        class_ids=top_class_ids,
    )

    print(f"\nSide view: {len(segments_side)} segment(s) ready")
    print(f"Top view : {len(segments_top)} segment(s) ready")

    all_results = module.calculate_volume_all_items(
        img1=image_top,
        img2=image_side,
        segments1=segments_top,
        segments2=segments_side,
        pixel_length_mm=PIXEL_LENGTH_MM,
        voxel_size_mm=VOXEL_SIZE_MM,
    )

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    for food_label, result in all_results.items():
        if not result:
            continue
        print(f"food name: {food_label}")
        print(f"volume: {result['volume_cm3']:.4f} cm cube")
        print(f"  voxels             : {result['num_voxels']}")
        print(f"  points             : {result['num_points']}")
        print(f"  pixel count        : {result['pixel_count']}")
        print(f"  shape correction   : {result['shape_correction']}")
        print()

    merged_volumes = module.aggregate_volumes_by_class(all_results)

    output_json_path = OUTPUT_ROOT / "food_volumes_summary.json"
    with open(output_json_path, "w") as f:
        json.dump(merged_volumes, f, indent=2)

    print(f"\n✅ Saved merged classification volumes to: {output_json_path}")
    print(json.dumps(merged_volumes, indent=2))

    return all_results, merged_volumes