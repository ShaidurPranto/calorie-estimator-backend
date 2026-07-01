"""Volume estimation utilities (extracted from the notebook's `module.py`).
"""
import os
import re
import shutil
from pathlib import Path
from typing import Tuple, Dict, Any, List

import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment


# ============================================================================
# NEW: Reorganize flat .npy masks into the classified folder structure
# ============================================================================

def organize_npy_files(source_folder, configuration_folder, output_folder):
    """
    Organizes .npy files from source_folder into output_folder
    following the folder structure of configuration_folder.
    """
    source_folder = Path(source_folder)
    configuration_folder = Path(configuration_folder)
    output_folder = Path(output_folder)

    # ---- Sanity checks on the input folders themselves --------------------
    if not source_folder.exists():
        print(f"❌ source_folder does not exist: {source_folder}")
        return
    if not configuration_folder.exists():
        print(f"❌ configuration_folder does not exist: {configuration_folder}")
        return

    all_npy_files = list(source_folder.glob("*.npy"))
    all_config_files = [f for f in configuration_folder.rglob("*") if f.is_file()]

    print(f"   source_folder        : {source_folder}  ({len(all_npy_files)} .npy files)")
    print(f"   configuration_folder : {configuration_folder}  ({len(all_config_files)} files)")

    if not all_npy_files:
        print(f"❌ No .npy files found in {source_folder} — nothing to organize.")
        return
    if not all_config_files:
        print(f"❌ No files found in {configuration_folder} — nothing to match against.")
        return

    # Lookup table: stem (lowercased) -> actual npy path, for exact matching
    npy_by_stem = {p.stem.lower(): p for p in all_npy_files}

    # Lookup table: trailing numeric index -> npy path(s), for filenames like
    # "..._mask_000.npy" that need to match "..._segment_000.png" — same
    # number, different middle word.
    npy_by_number: dict = {}
    for p in all_npy_files:
        m = re.search(r"(\d+)$", p.stem)
        if m:
            num = int(m.group(1))
            npy_by_number.setdefault(num, []).append(p)

    # Create output folder if it does not exist
    output_folder.mkdir(parents=True, exist_ok=True)

    matched = 0
    unmatched_config_stems = []

    # Traverse all files in configuration folder
    for config_file in all_config_files:

        # Relative path from configuration root (e.g. "porota")
        relative_dir = config_file.parent.relative_to(configuration_folder)
        config_stem = config_file.stem

        # 1) Exact stem match (case-insensitive)
        source_npy = npy_by_stem.get(config_stem.lower())

        # 2) Fallback: fuzzy match — handles classifier suffixes like
        #    "_crop", "_mask", "_resized" etc. added to the image filename,
        #    or the npy having an extra suffix the image doesn't.
        if source_npy is None:
            config_lower = config_stem.lower()
            candidates = [
                p for stem, p in npy_by_stem.items()
                if stem.startswith(config_lower) or config_lower.startswith(stem)
            ]
            if len(candidates) == 1:
                source_npy = candidates[0]
                print(f"   ℹ️  Fuzzy-matched '{config_file.name}' -> '{source_npy.name}'")
            elif len(candidates) > 1:
                print(f"⚠️  Ambiguous match for '{config_file.name}': "
                      f"{[c.name for c in candidates]} — skipping.")

        # 3) Fallback: match by trailing number (e.g. "..._segment_003"
        #    <-> "..._mask_003") — works when index numbering lines up
        #    1:1 between the mask and image sets for this view.
        if source_npy is None:
            m = re.search(r"(\d+)$", config_stem)
            if m:
                num = int(m.group(1))
                num_candidates = npy_by_number.get(num, [])
                if len(num_candidates) == 1:
                    source_npy = num_candidates[0]
                    print(f"   ℹ️  Number-matched '{config_file.name}' -> '{source_npy.name}' (index {num})")
                elif len(num_candidates) > 1:
                    print(f"⚠️  Ambiguous number match for '{config_file.name}' "
                          f"(index {num}): {[c.name for c in num_candidates]} — skipping.")

        if source_npy is None:
            unmatched_config_stems.append(config_file.name)
            continue

        # Create matching output directory
        target_dir = output_folder / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy npy file, keeping the SAME stem as the classified image so
        # downstream folder scans line up 1:1 with the classification result.
        dest_name = config_stem + ".npy"
        shutil.copy2(source_npy, target_dir / dest_name)
        matched += 1

    print(f"\n   Matched & copied : {matched}/{len(all_config_files)} file(s)")

    if unmatched_config_stems:
        print(f"   ⚠️  Could NOT find a matching .npy for {len(unmatched_config_stems)} file(s):")
        for name in unmatched_config_stems[:10]:
            print(f"        - {name}")
        if len(unmatched_config_stems) > 10:
            print(f"        ... and {len(unmatched_config_stems) - 10} more")
        print("   -> Check that the filenames in the classified image folder "
              "share a base name with the corresponding .npy mask file.")

    if matched == 0:
        print("   ❌ Nothing was copied. Sample filenames for comparison:")
        print(f"        .npy files   : {[p.name for p in all_npy_files[:5]]}")
        print(f"        image files  : {[f.name for f in all_config_files[:5]]}")

    print("Finished organizing files.")


# ============================================================================
# STEP 1: Load Image
# ============================================================================

def load_image_file(path: str) -> np.ndarray:
    """Load an image from disk and convert BGR -> RGB."""
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(f"Image not found: {path}")
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


# ============================================================================
# STEP 2: Load NPY Segmentation Mask
# ============================================================================

def load_npy_mask(path: str) -> np.ndarray:
    """
    Load a numpy segmentation mask from a .npy file and normalise it
    to a binary uint8 mask (0 = background, 255 = food).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Mask file not found: {path}")

    data = np.load(path, allow_pickle=True)
    mask = np.asarray(data)

    # Squeeze extra dimensions (e.g. (1, H, W) -> (H, W))
    if mask.ndim > 2:
        mask = np.squeeze(mask)

    # Normalise any dtype to binary uint8 (0 or 255)
    binary = (mask > 0).astype(np.uint8) * 255

    # Auto-correct inverted masks: food should be < 50% of the image.
    food_ratio = np.count_nonzero(binary) / max(binary.size, 1)
    if food_ratio > 0.50:
        binary = cv2.bitwise_not(binary)
        print(f"   ⚠️  Mask inverted ({food_ratio:.1%} marked) — auto-flipped")

    print(f"✅ Loaded mask: {path}")
    print(f"   Shape: {binary.shape}, Food pixels: {np.count_nonzero(binary):,}")
    return binary


def mask_to_yolo_polygon(
    mask: np.ndarray,
    image_width: int,
    image_height: int,
    epsilon_ratio: float = 0.002,
) -> list:
    """
    Convert a binary mask to normalised YOLO polygon coordinates.
    """
    if mask.shape[:2] != (image_height, image_width):
        mask = cv2.resize(mask, (image_width, image_height),
                           interpolation=cv2.INTER_NEAREST)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []

    largest = max(contours, key=cv2.contourArea)
    epsilon = epsilon_ratio * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)

    return [(pt[0][0] / image_width, pt[0][1] / image_height) for pt in approx]


def coordinates_to_mask(
    img_height: int,
    img_width: int,
    normalized_coords: list,
) -> np.ndarray:
    """
    Convert normalised YOLO polygon coordinates -> binary mask (uint8, 0/255).
    """
    mask = np.zeros((img_height, img_width), dtype=np.uint8)
    if not normalized_coords:
        return mask
    pixel_coords = np.array(
        [[int(x * img_width), int(y * img_height)] for x, y in normalized_coords],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, [pixel_coords], 255)
    return mask


# ============================================================================
# STEP 3: Convert NPY Mask -> Segment Dict
# ============================================================================

def parse_npy_segments(
    image: np.ndarray,
    npy_paths: list,
    class_ids: list = None,
) -> list:
    """
    Build the segment-dict list required by `calculate_volume_all_items()`
    directly from a list of `.npy` mask files — no YOLO `.txt` needed.
    """
    h, w = image.shape[:2]
    result = []

    for i, path in enumerate(npy_paths):
        if class_ids:
            cid = str(class_ids[i]) if i < len(class_ids) else str(class_ids[-1])
        else:
            cid = str(i)

        try:
            raw_mask = load_npy_mask(path)
        except FileNotFoundError as e:
            print(f"⚠️  Skipping mask {path}: {e}")
            continue

        if raw_mask.shape != (h, w):
            raw_mask = cv2.resize(raw_mask, (w, h), interpolation=cv2.INTER_NEAREST)

        clean = preprocess_mask(raw_mask)
        bbox = _bbox_from_mask(clean)

        result.append({
            "class_id": cid,
            "mask": clean,
            "bbox": bbox,
        })
        print(f"   [{cid}] bbox={bbox}, food_pixels={np.count_nonzero(clean):,}")

    print(f"\n✅ parse_npy_segments: {len(result)} item(s) ready")
    return result


# ============================================================================
# STEP 4: Visualise Segmentation Result
# ============================================================================

def visualize_mask_on_image(image: np.ndarray, mask: np.ndarray, title: str = 'Segmentation Visualization') -> None:
    """
    Display image with segmentation mask overlay and statistics.
    (Requires matplotlib; import is local so this module can be used headlessly.)
    """
    import matplotlib.pyplot as plt

    if image is None or mask is None:
        print("❌ Image or mask is None!")
        return

    mask = (mask > 0).astype(np.uint8) * 255

    h, w = image.shape[:2]
    if mask.shape != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(title, fontsize=16, fontweight='bold')

    axes[0, 0].imshow(image)
    axes[0, 0].set_title("1. Original Image", fontweight='bold')
    axes[0, 0].axis('off')

    axes[0, 1].imshow(mask, cmap='gray')
    axes[0, 1].set_title(f"2. Segmentation Mask\n({np.count_nonzero(mask)} pixels)", fontweight='bold')
    axes[0, 1].axis('off')

    masked_rgb = cv2.bitwise_and(image, image, mask=mask)
    axes[1, 0].imshow(masked_rgb)
    axes[1, 0].set_title("3. Food Region Only", fontweight='bold')
    axes[1, 0].axis('off')

    overlay = image.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 3)
    axes[1, 1].imshow(overlay)
    axes[1, 1].set_title("4. Overlay with Boundary", fontweight='bold')
    axes[1, 1].axis('off')

    plt.tight_layout()
    plt.show()


# ============================================================================
# Helpers for many segmentations in one image (YOLO compatibility kept)
# ============================================================================

def load_yolo_coordinates(label_path: str) -> List[dict]:
    """
    Parse a YOLO label file that may contain multiple detections.
    """
    detections = []
    if not os.path.exists(label_path):
        print(f"⚠️  Label file not found: {label_path}")
        return detections

    with open(label_path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            class_id = parts[0]
            coords_flat = list(map(float, parts[1:]))
            coords = [
                (coords_flat[i], coords_flat[i + 1])
                for i in range(0, len(coords_flat) - 1, 2)
            ]
            detections.append({
                "class_id": class_id,
                "normalized_coords": coords,
            })

    return detections


# ============================================================================
# Preprocessing
# ============================================================================

def preprocess_mask(mask: np.ndarray) -> np.ndarray:
    """
    Clean a raw segmentation mask:
      1. Binarise (Otsu threshold)
      2. Morphological closing  - fills small gaps
      3. Hole filling           - closes interior holes
      4. Keep largest region    - removes stray blobs
    """
    # 1. Binarise
    _, binary = cv2.threshold(mask, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 2. Morphological closing (fills small gaps / broken edges)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 3. Flood-fill holes from the border
    h, w = closed.shape
    flood = closed.copy()
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, flood_mask, (0, 0), 255)
    holes_filled = closed | cv2.bitwise_not(flood)

    # 4. Keep only significant connected components (removes thumb/noise).
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        holes_filled, connectivity=8
    )
    if num_labels <= 1:
        return holes_filled
    component_areas = stats[1:, cv2.CC_STAT_AREA]  # skip background label 0
    max_area = component_areas.max()
    min_area = max(max_area * 0.05, 100)           # at least 5% of main blob
    clean = np.zeros_like(holes_filled)
    for lbl_idx, area in enumerate(component_areas, start=1):
        if area >= min_area:
            clean[labels == lbl_idx] = 255

    return clean


# ============================================================================
# 3-D point cloud from two views
# ============================================================================

def build_point_cloud_two_views(
    img1: np.ndarray,
    img2: np.ndarray,
    mask1: np.ndarray,
    mask2: np.ndarray,
    pixel_length_mm: float,
    max_points: int = 5000,
) -> np.ndarray:
    """
    Estimate a 3-D point cloud from two views using SIFT feature matching
    + stereo triangulation. Falls back to a single-view flat-plane estimate
    when fewer than 8 good matches are found.

    Returns (N, 3) float32 array in mm.
    """
    gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY)
    h, w = gray1.shape

    # 1. SIFT keypoints inside the food mask
    try:
        sift = cv2.SIFT_create(nfeatures=2000)
    except AttributeError:
        sift = cv2.xfeatures2d.SIFT_create(nfeatures=2000)

    kp1, des1 = sift.detectAndCompute(gray1, mask1)
    kp2, des2 = sift.detectAndCompute(gray2, mask2)

    # 2. FLANN + Lowe ratio matching
    MIN_GOOD = 8
    if (
        des1 is not None and des2 is not None
        and len(kp1) >= MIN_GOOD
        and len(kp2) >= MIN_GOOD
    ):
        index_params = dict(algorithm=1, trees=5)
        search_params = dict(checks=50)
        flann = cv2.FlannBasedMatcher(index_params, search_params)
        raw = flann.knnMatch(des1, des2, k=2)
        good = [m for m, n in raw if m.distance < 0.75 * n.distance]
    else:
        good = []

    # 3 + 4. Pose estimation + triangulation (or fallback)
    if len(good) >= MIN_GOOD:
        pts1 = np.float32([kp1[m.queryIdx].pt for m in good])
        pts2 = np.float32([kp2[m.trainIdx].pt for m in good])

        focal = float(max(h, w))
        cx, cy = w / 2.0, h / 2.0
        K = np.array([[focal, 0, cx],
                      [0, focal, cy],
                      [0, 0, 1]], dtype=np.float64)

        E, inlier_mask = cv2.findEssentialMat(
            pts1, pts2, K, method=cv2.RANSAC, prob=0.999, threshold=1.0
        )
        _, R, t, pose_mask = cv2.recoverPose(E, pts1, pts2, K, mask=inlier_mask)

        inlier_pts1 = pts1[pose_mask.ravel() > 0]
        inlier_pts2 = pts2[pose_mask.ravel() > 0]

        P1 = K @ np.hstack([np.eye(3), np.zeros((3, 1))])
        P2 = K @ np.hstack([R, t])

        pts4d = cv2.triangulatePoints(P1, P2, inlier_pts1.T, inlier_pts2.T)
        pts3d = (pts4d[:3] / pts4d[3]).T

        valid = pts3d[:, 2] > 0
        pts3d = pts3d[valid]
        inlier_pts1 = inlier_pts1[valid]

        xi = np.clip(inlier_pts1[:, 0].astype(int), 0, w - 1)
        yi = np.clip(inlier_pts1[:, 1].astype(int), 0, h - 1)
        in_mask = mask1[yi, xi] > 0
        pts3d = pts3d[in_mask]
        inlier_pts1 = inlier_pts1[in_mask]

        # ── FIX: rescale reconstruction units -> pixel units ─────────────
        spread_3d = np.ptp(pts3d[:, :2], axis=0).mean() + 1e-9
        spread_2d = np.ptp(inlier_pts1, axis=0).mean() + 1e-9
        scale = spread_2d / spread_3d
        pts3d = pts3d * scale
        # ───────────────────────────────────────────────────────────────

        print(f"   ✅ Triangulated {len(pts3d):,} pts from {len(good)} matches (scale={scale:.4f})")

    else:
        print(f"   ⚠️  Only {len(good)} matches — single-view fallback")
        ys, xs = np.where(mask1 > 0)
        if len(xs) == 0:
            return np.zeros((0, 3), dtype=np.float32)
        depth_estimate = (ys.max() - ys.min()) * 0.5
        depths = np.full(len(xs), depth_estimate, dtype=np.float32)
        pts3d = np.column_stack([xs.astype(np.float32),
                                  ys.astype(np.float32),
                                  depths])

    # 5. Scale pixels -> mm, subsample
    pts3d_mm = pts3d.astype(np.float32) * pixel_length_mm
    if len(pts3d_mm) > max_points:
        idx = np.random.choice(len(pts3d_mm), max_points, replace=False)
        pts3d_mm = pts3d_mm[idx]

    return pts3d_mm


# ============================================================================
# Statistical outlier removal
# ============================================================================

def remove_outliers(
    points: np.ndarray,
    k: int = 20,
    std_ratio: float = 2.0,
) -> np.ndarray:
    """
    Remove statistical outliers from a point cloud using k-NN mean distance.
    Points beyond  mean + std_ratio * std  are discarded.
    """
    if len(points) < k + 1:
        return points

    diff = points[:, None, :] - points[None, :, :]
    dists = np.sqrt((diff ** 2).sum(axis=-1))
    dists.sort(axis=1)

    mean_k_dist = dists[:, 1:k + 1].mean(axis=1)
    threshold = mean_k_dist.mean() + std_ratio * mean_k_dist.std()
    mask = mean_k_dist <= threshold

    print(f"   Outlier removal: {points.shape[0]} -> {mask.sum()} pts kept")
    return points[mask]


# ============================================================================
# Voxelisation
# ============================================================================

def voxelize_point_cloud(
    points_mm: np.ndarray,
    voxel_size_mm: float,
) -> int:
    """
    Count occupied voxels in a uniform voxel grid.
    Each point is mapped to floor(coord / voxel_size); duplicates collapse.
    """
    if len(points_mm) == 0:
        return 0

    shifted = points_mm - points_mm.min(axis=0)
    indices = np.floor(shifted / voxel_size_mm).astype(np.int32)
    occupied = {(ix, iy, iz) for ix, iy, iz in indices}
    return len(occupied)


# ============================================================================
# Shape correction factors
# ============================================================================

SHAPE_CORRECTION = {
    "rice": 1.00,
    "soup": 1.00,
    "salad": 1.00,
    "apple": 0.52,
    "orange": 0.52,
    "egg": 0.50,
    "meatball": 0.52,
    "pizza": 0.25,
    "flatbread": 0.20,
    "naan": 0.20,
    "burger": 0.65,
    "sandwich": 0.60,
    "cake": 0.70,
    "default": 1.00,
}


def get_shape_correction(food_type: str) -> float:
    ft = food_type.lower() if food_type else ""
    for keyword, factor in SHAPE_CORRECTION.items():
        if keyword in ft:
            return factor
    return SHAPE_CORRECTION["default"]


# ============================================================================
# TOP-LEVEL single-item function for Voxel
# ============================================================================

def calculate_volume_voxel(
    img1: np.ndarray,
    img2: np.ndarray,
    mask1: np.ndarray,
    mask2: np.ndarray,
    pixel_length_mm: float,
    food_type: str = "",
    voxel_size_mm: float = 5.0,
) -> dict:
    """
    Full voxel-grid volume estimation pipeline for ONE food item.
    """
    print("\n" + "=" * 60)
    print(f"VOXEL-GRID VOLUME ESTIMATION  [{food_type or 'unknown'}]")
    print("=" * 60)

    # 1. Preprocess
    print("\n[1/5] Preprocessing masks...")
    clean1 = preprocess_mask(mask1)
    clean2 = preprocess_mask(mask2)
    pixel_count = int(np.count_nonzero(clean1))
    print(f"   Mask1 food pixels: {pixel_count:,}")
    print(f"   Mask2 food pixels: {np.count_nonzero(clean2):,}")

    # 2. Build point cloud
    print("\n[2/5] Building 3-D point cloud...")
    points_mm = build_point_cloud_two_views(
        img1, img2, clean1, clean2, pixel_length_mm
    )
    print(f"   Raw cloud: {len(points_mm):,} points")

    if len(points_mm) == 0:
        print("❌ Empty point cloud — check inputs")
        return {}

    # 3. Outlier removal
    print("\n[3/5] Removing outliers...")
    points_mm = remove_outliers(points_mm)

    # 4. Voxelise
    print(f"\n[4/5] Voxelising (voxel size = {voxel_size_mm} mm)...")
    num_voxels = voxelize_point_cloud(points_mm, voxel_size_mm)
    print(f"   Occupied voxels: {num_voxels:,}")

    # 5. Volume
    print("\n[5/5] Computing volume...")
    shape_factor = get_shape_correction(food_type)
    raw_vol_mm3 = num_voxels * (voxel_size_mm ** 3)
    volume_mm3 = raw_vol_mm3 * shape_factor

    result = {
        "pixel_count": pixel_count,
        "num_points": len(points_mm),
        "num_voxels": num_voxels,
        "voxel_size_mm": voxel_size_mm,
        "shape_correction": shape_factor,
        "volume_mm3": volume_mm3,
        "volume_cm3": volume_mm3 / 1_000,
        "volume_ml": volume_mm3 / 1_000,
        "volume_l": volume_mm3 / 1_000_000,
        "food_type": food_type or "unknown",
    }

    print(f"\n{'=' * 60}")
    print(f"  Food type        : {result['food_type']}")
    print(f"  Pixel count      : {result['pixel_count']:,}")
    print(f"  Point cloud size : {result['num_points']:,}")
    print(f"  Occupied voxels  : {result['num_voxels']:,}")
    print(f"  Voxel size       : {result['voxel_size_mm']} mm")
    print(f"  Shape correction : {result['shape_correction']}")
    print(f"  Volume           : {result['volume_mm3']:,.2f} mm³")
    print(f"                   : {result['volume_cm3']:,.4f} cm³  /  {result['volume_ml']:,.4f} mL")
    print("=" * 60)

    return result


# ============================================================================
# Helper for Many Item Voxelation
# ============================================================================

def _bbox_from_mask(mask: np.ndarray) -> Tuple[int, int, int, int]:
    """
    Compute the bounding box of the non-zero region of a mask.
    Returns (x, y, w, h) in pixels.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return (0, 0, 0, 0)
    x, y = int(xs.min()), int(ys.min())
    w, h = int(xs.max()) - x, int(ys.max()) - y
    return (x, y, w, h)


def _bbox_center(bbox: Tuple[int, int, int, int]) -> np.ndarray:
    """Return the (cx, cy) centre of a bbox tuple (x, y, w, h)."""
    x, y, w, h = bbox
    return np.array([x + w / 2.0, y + h / 2.0])


def match_by_position(
    segs1: List[dict],
    segs2: List[dict],
) -> List[Tuple[dict, dict]]:
    """
    Strategy B — pair each segment in segs1 with the spatially nearest
    segment in segs2 using the Hungarian algorithm (optimal assignment).
    """
    if not segs1 or not segs2:
        return []

    cost = np.array([
        [np.linalg.norm(_bbox_center(s1["bbox"]) - _bbox_center(s2["bbox"]))
         for s2 in segs2]
        for s1 in segs1
    ])

    row_idx, col_idx = linear_sum_assignment(cost)
    return [(segs1[r], segs2[c]) for r, c in zip(row_idx, col_idx)]


# ============================================================================
# Parse a single YOLO label file into segment dicts (compatibility)
# ============================================================================

def parse_yolo_segments(
    image: np.ndarray,
    all_coords: List[dict],
) -> List[dict]:
    """
    Convert the output of load_yolo_coordinates() into a list of segment
    dicts that carry the mask AND its bounding box (needed by Strategy B).
    """
    h, w = image.shape[:2]
    result = []
    for coords in all_coords:
        mask = coordinates_to_mask(h, w, coords["normalized_coords"])
        bbox = _bbox_from_mask(mask)
        result.append({
            "class_id": coords["class_id"],
            "mask": mask,
            "bbox": bbox,
        })
    return result


# ============================================================================
# Calculate volume for all items
# ============================================================================

def calculate_volume_all_items(
    img1: np.ndarray,
    img2: np.ndarray,
    segments1: List[dict],
    segments2: List[dict],
    pixel_length_mm: float,
    voxel_size_mm: float = 5.0,
) -> Dict[str, dict]:
    """
    Run the full voxel-grid volume pipeline for ALL food items in both images.
    """
    print("\n" + "=" * 60)
    print("MULTI-ITEM VOLUME ESTIMATION  (Strategy B active)")
    print("=" * 60)
    print(f"  Segments in image 1 : {len(segments1)}")
    print(f"  Segments in image 2 : {len(segments2)}")

    def group_by_class(segs: List[dict]) -> Dict[str, List[dict]]:
        groups: Dict[str, List[dict]] = {}
        for s in segs:
            groups.setdefault(s["class_id"], []).append(s)
        return groups

    groups1 = group_by_class(segments1)
    groups2 = group_by_class(segments2)

    all_results: Dict[str, dict] = {}

    for class_id, segs1 in groups1.items():

        if class_id not in groups2:
            print(f"\n⚠️  '{class_id}' found in image 1 but NOT image 2 — skipping")
            continue

        segs2 = groups2[class_id]

        pairs = match_by_position(segs1, segs2)

        for i, (s1, s2) in enumerate(pairs):
            label = f"{class_id}_{i}" if len(pairs) > 1 else class_id

            print(f"\n▶  Processing item: {label}")

            result = calculate_volume_voxel(
                img1=img1,
                img2=img2,
                mask1=s1["mask"],
                mask2=s2["mask"],
                pixel_length_mm=pixel_length_mm,
                food_type=class_id,
                voxel_size_mm=voxel_size_mm,
            )
            all_results[label] = result

    print("\n" + "=" * 60)
    print("SUMMARY — all items")
    print("=" * 60)
    print(f"  {'Item':<20} {'Volume (mL)':>12}")
    print(f"  {'-' * 20} {'-' * 12}")
    for label, r in all_results.items():
        if r:
            print(f"  {label:<20} {r['volume_ml']:>12.2f}")
    print("=" * 60)

    return all_results


# ============================================================================
# NEW: Merge per-item volumes into ONE total volume per food classification
# ============================================================================

def aggregate_volumes_by_class(all_results: Dict[str, dict]) -> Dict[str, float]:
    """
    Merge individual item volumes into one total volume per food classification.
    """
    totals: Dict[str, float] = {}

    for label, result in all_results.items():
        if not result:
            continue
        class_name = result.get("food_type", label)
        totals[class_name] = totals.get(class_name, 0.0) + result["volume_cm3"]

    totals = {k: round(v, 4) for k, v in totals.items()}

    print("\n" + "=" * 60)
    print("MERGED VOLUME PER CLASSIFICATION")
    print("=" * 60)
    for class_name, total_vol in totals.items():
        print(f"  all {class_name} volume : {total_vol:.4f} cm³  /  {total_vol:.4f} mL")
    print("=" * 60)

    return totals
