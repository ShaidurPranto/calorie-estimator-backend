import os
import cv2
import json
import math
import time
import torch
import numpy as np
from PIL import Image
from pathlib import Path
import matplotlib.pyplot as plt
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
SEGMENTATION_MODULE_DIR = BASE_DIR / "models" / "segmentation"

if str(SEGMENTATION_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(SEGMENTATION_MODULE_DIR))

from sam2.build_sam import build_sam2  # pyright: ignore[reportMissingImports]
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator  # pyright: ignore[reportMissingImports]


class SegmentationModule:
    """
    A segmentation module for food image segmentation using SAM2.
    """

    def __init__(self, checkpoint, model_config, device=None):
        """
        Initialize the SegmentationModule.

        Args:
            checkpoint   (str): Path to the SAM2 .pt checkpoint file.
            model_config (str): SAM2 config filename (e.g. 'sam2_hiera_l.yaml').
            device       (str): 'cuda' or 'cpu'. Auto-detected if None.
        """
        self.checkpoint   = checkpoint
        self.model_config = model_config
        self.device       = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # SAM2 mask-generator parameters
        # self.points_per_side        = 64
        # self.points_per_batch       = 32
        self.points_per_side        = 32
        self.points_per_batch       = 8
          
        self.pred_iou_thresh        = 0.8
        self.stability_score_thresh = 0.92
        self.box_nms_thresh         = 0.6
        self.min_mask_region_area   = 100
        self.dedup_iou_threshold    = 0.85
        self.min_area_ratio         = 0.02

        if self.device == "cuda":
            try:
                total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                if total_vram_gb < 6:
                    self.points_per_side = 32
                    self.points_per_batch = 16
                    print(
                        f"Low VRAM GPU detected ({total_vram_gb:.2f} GB). "
                        "Using memory-safe SAM2 parameters."
                    )
            except Exception:
                pass

        self.mask_generator = self._load_model()

    # ------------------------------------------------------------------
    # PRIVATE: Model loading
    # ------------------------------------------------------------------

    def _load_model(self):
        if not os.path.exists(self.checkpoint):
            raise FileNotFoundError(f"SAM2 checkpoint not found at {self.checkpoint}")

        if isinstance(self.model_config, str):
            config_value = self.model_config.strip()
            if config_value.endswith(".yaml") and "/" not in config_value:
                self.model_config = f"configs/sam2/{config_value}"

        print(f"Loading SAM2 on {self.device}...")
        sam2 = build_sam2(
            self.model_config, self.checkpoint,
            device=self.device, apply_postprocessing=True
        )
        return SAM2AutomaticMaskGenerator(
            model=sam2,
            points_per_side=self.points_per_side,
            points_per_batch=self.points_per_batch,
            pred_iou_thresh=self.pred_iou_thresh,
            stability_score_thresh=self.stability_score_thresh,
            box_nms_thresh=self.box_nms_thresh,
            min_mask_region_area=self.min_mask_region_area,
        )

    # ------------------------------------------------------------------
    # PRIVATE: Helpers
    # ------------------------------------------------------------------

    def _load_image_rgb(self, input):
        """
        Accept a file path (str) or a PIL Image and return an RGB numpy array.
        """
        if isinstance(input, str):
            if not os.path.exists(input):
                raise FileNotFoundError(f"Image not found at {input}")
            image = cv2.imdecode(np.fromfile(input, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Failed to read image: {input}")
            return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif isinstance(input, Image.Image):
            return np.array(input.convert("RGB"))
        else:
            raise TypeError("Input must be a file path (str) or a PIL.Image object")

    ## this is v1
    def _generate_masks(self, image_rgb):
        """Run SAM2 and apply area-based filtering + deduplication."""
        masks = self.mask_generator.generate(image_rgb)
        masks = self._deduplicate_masks(masks)
        if masks:
            max_area = max(m["area"] for m in masks)
            masks = [m for m in masks if m["area"] >= self.min_area_ratio * max_area]
        return masks
    ## 


    ## this is v2
    # def _generate_masks(self, image_rgb):
    #     masks = self.mask_generator.generate(image_rgb)
    #     masks = self._deduplicate_masks(masks)
    #     if masks:
    #         max_area = max(m["area"] for m in masks)
    #         masks = [m for m in masks if m["area"] >= self.min_area_ratio * max_area]

    #     # NEW — reject scattered/fragmented masks
    #     good = []
    #     for m in masks:
    #         seg = m["segmentation"]
    #         ys, xs = np.where(seg)
    #         if len(ys) == 0:
    #             continue
    #         bbox_area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
    #         if seg.sum() / bbox_area >= 0.30:
    #             good.append(m)
    #     return good
    ## 

    def _deduplicate_masks(self, masks):
        """Remove heavily overlapping masks, keeping the larger one."""
        masks = sorted(masks, key=lambda m: m["area"], reverse=True)
        kept = []
        for candidate in masks:
            c_mask = candidate["segmentation"]
            is_duplicate = False
            for kept_mask in kept:
                k_mask = kept_mask["segmentation"]
                intersection = np.logical_and(c_mask, k_mask).sum()
                union        = np.logical_or(c_mask,  k_mask).sum()
                if union > 0 and (intersection / union) > self.dedup_iou_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept.append(candidate)
        return kept

    # ------------------------------------------------------------------
    # PRIVATE: Visualization helpers
    # ------------------------------------------------------------------

    def _read_disp(self, path_str):
        """Read an image from disk and return (array, cmap) ready for imshow."""
        img = cv2.imread(str(path_str), cv2.IMREAD_UNCHANGED)
        if img is None:
            return None, None
        if img.ndim == 2:
            return img, 'gray'
        if img.shape[2] == 4:
            return cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA), None
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), None

    def _style_ax(self, ax, title):
        """Apply uniform axis styling: title, no ticks, black border."""
        ax.set_title(title, fontsize=8, pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(True); sp.set_color('black'); sp.set_linewidth(2)

    # ------------------------------------------------------------------
    # PUBLIC: Input methods
    # ------------------------------------------------------------------

    def set_image_from_path(self, image_path):
        """Load and cache an image from a file path."""
        self._cached_image_rgb = self._load_image_rgb(image_path)
        self._cached_masks = None

    def set_image(self, image):
        """Load and cache a PIL Image."""
        self._cached_image_rgb = self._load_image_rgb(image)
        self._cached_masks = None

    def _get_cached_masks(self, input=None):
        """Return cached masks, generating them if not yet computed."""
        if input is not None:
            image_rgb = self._load_image_rgb(input)
            return image_rgb, self._generate_masks(image_rgb)

        if not hasattr(self, "_cached_image_rgb") or self._cached_image_rgb is None:
            raise RuntimeError(
                "No image loaded. Call set_image() or set_image_from_path() first, "
                "or pass an image directly to the method."
            )
        if self._cached_masks is None:
            self._cached_masks = self._generate_masks(self._cached_image_rgb)
        return self._cached_image_rgb, self._cached_masks

    # ------------------------------------------------------------------
    # PUBLIC: Output methods
    # ------------------------------------------------------------------

    def get_coordinates(self, input=None):
        """
        Return bounding-box coordinates for each detected segment.

        Returns list of dicts with keys:
            segment_id, bbox, area, predicted_iou, stability_score
        """
        _, masks = self._get_cached_masks(input)
        return [
            {
                "segment_id":      i,
                "bbox":            mask["bbox"],
                "area":            mask["area"],
                "predicted_iou":   round(mask["predicted_iou"],   4),
                "stability_score": round(mask["stability_score"], 4),
            }
            for i, mask in enumerate(masks)
        ]

    def get_masks(self, input=None):
        """
        Return binary boolean masks for each detected segment.

        Returns list of dicts with keys:
            segment_id, mask (np.ndarray bool H×W), area
        """
        _, masks = self._get_cached_masks(input)
        return [
            {
                "segment_id": i,
                "mask":       mask["segmentation"].astype(bool),
                "area":       mask["area"],
            }
            for i, mask in enumerate(masks)
        ]

    def get_segments(self, input=None):
        """
        Return full-size RGBA PIL images for each detected segment.
        Background outside the mask is transparent.

        Returns list of dicts with keys:
            segment_id, image (PIL RGBA full size), bbox, area
        """
        image_rgb, masks = self._get_cached_masks(input)
        results = []
        for i, mask in enumerate(masks):
            mask_bool = mask["segmentation"].astype(bool)

            rgba = np.zeros((*image_rgb.shape[:2], 4), dtype=np.uint8)
            rgba[..., :3] = image_rgb
            rgba[..., 3]  = (mask_bool * 255).astype(np.uint8)

            ys, xs = np.where(mask_bool)
            x0, x1 = xs.min(), xs.max() + 1
            y0, y1 = ys.min(), ys.max() + 1
            cropped = rgba[y0:y1, x0:x1]

            results.append({
                "segment_id": i,
                "image":      Image.fromarray(cropped, mode="RGBA"),
                "bbox":       mask["bbox"],
                "area":       mask["area"],
            })
        return results

    def clear_cache(self):
        """Release cached image, masks, and free GPU memory aggressively."""
        self._cached_image_rgb = None
        self._cached_masks = None
        
        # Clear SAM2's internal image encoder state if it exists
        if hasattr(self.mask_generator, 'predictor'):
            predictor = self.mask_generator.predictor
            if hasattr(predictor, '_features'):
                predictor._features = None
            if hasattr(predictor, '_orig_hw'):
                predictor._orig_hw = None
        
        import gc
        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        print(f"GPU memory after clear: {torch.cuda.memory_allocated()/1e9:.2f}GB allocated")


    def display_segments(self, input_image_path, segments_dir, seg_cols=3):
        """
        Display an input image alongside all its saved segment PNGs in a grid.

        Args:
            input_image_path (str): Path to the original input image.
            segments_dir     (str): Path to the folder containing segment PNGs
                                    for this image (e.g. .../segments/image_name/).
            seg_cols         (int): Number of columns in the segments grid.
        """
        valid_ext = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
        input_path = Path(input_image_path)

        seg_paths = sorted([
            p for p in Path(segments_dir).iterdir()
            if p.is_file() and p.suffix.lower() in valid_ext
        ])

        if not seg_paths:
            print(f"⚠️  No segments found in '{segments_dir}'")
            return

        seg_rows   = math.ceil(len(seg_paths) / seg_cols)
        total_rows = 1 + seg_rows

        fig = plt.figure(
            figsize=(seg_cols * 4, 4 + seg_rows * 3.5),
            facecolor='white'
        )
        plt.suptitle(
            f"Segmentation results for  '{input_path.stem}'",
            fontsize=11, fontweight='bold', y=1.01
        )

        # Row 0: input image (full width)
        ax_input = plt.subplot2grid((total_rows, seg_cols), (0, 0), colspan=seg_cols)
        inp_disp, inp_cmap = self._read_disp(str(input_path))
        if inp_disp is not None:
            ax_input.imshow(inp_disp, cmap=inp_cmap)
        self._style_ax(ax_input, f"INPUT  —  {input_path.name}")

        # Rows 1..N: segments
        for idx, seg_path in enumerate(seg_paths):
            row = 1 + idx // seg_cols
            col = idx  % seg_cols
            ax  = plt.subplot2grid((total_rows, seg_cols), (row, col))
            disp, cmap = self._read_disp(seg_path)
            if disp is not None:
                ax.imshow(disp, cmap=cmap)
            self._style_ax(ax, seg_path.name)

        # Hide leftover empty axes
        remainder = len(seg_paths) % seg_cols
        if remainder:
            for empty_col in range(remainder, seg_cols):
                ax_empty = plt.subplot2grid(
                    (total_rows, seg_cols), (total_rows - 1, empty_col)
                )
                ax_empty.set_visible(False)

        plt.tight_layout()
        plt.show()
        print(f"✔ '{input_path.stem}' — {len(seg_paths)} segments shown\n")


    def display_all_segments(self, input_dir, segments_root_dir, seg_cols=3):
        """
        Display segmentation results for every image in input_dir.

        Args:
            input_dir         (str): Folder containing the original input images.
            segments_root_dir (str): Root segments folder (contains one sub-folder
                                     per image, named after the image stem).
            seg_cols          (int): Number of columns in each segments grid.
        """
        valid_ext = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

        all_input_images = sorted([
            p for p in Path(input_dir).iterdir()
            if p.is_file() and p.suffix.lower() in valid_ext
        ])

        for input_path in all_input_images:
            segments_subdir = os.path.join(segments_root_dir, input_path.stem)

            if not os.path.isdir(segments_subdir):
                print(f"⚠️  Skipping '{input_path.stem}' — no segments folder found.")
                continue

            self.display_segments(str(input_path), segments_subdir, seg_cols=seg_cols)