# 🍽 Calorie Estimator API

A FastAPI-based service that estimates the calorie and nutrient content of a meal from two photos (a **top view** and a **side view**). The pipeline runs the images through segmentation, thumbnail generation, food classification, and volume estimation, then maps the results against an internal nutrition knowledge base to produce a full nutrition report.

---

## How it works (pipeline overview)

```
top.jpg  ─┐
           ├─► /process ─► segmentation ─► thumbnailing ─► classification ─► volume estimation ─► nutrition report
side.jpg ─┘
```

1. **Upload** a top-view and a side-view image of the meal.
2. **Trigger processing** via `/process`, which runs, in order:
   - `segmentation_workflow.seg_main()` — segments food items from the images
   - `thumb_workflow.thumb_main()` — generates thumbnails/crops per segmented item
   - `classification_workflow.class_main()` — classifies each food item
   - `volume_workflow.vol_main()` — estimates the volume (cm³) of each food item
3. The estimated volumes are matched against a built-in **nutrition knowledge base** to compute calories, macros, minerals, and vitamins.
4. A JSON nutrition report is generated and returned.

---

## Project structure

```
app/
├── api.py                          # FastAPI app & route definitions (this file)
├── working/
│   └── input_images/               # Uploaded top/side images live here (persisted across runs)
├── models/
│   ├── classifier/                 # Input models for the classification workflow (from notebook)
│   ├── segmentation/               # Input models for the segmentation workflow (from notebook)
│   └── thumb/                      # Input models for the thumbnail workflow (from notebook)
└── workflows/
    ├── segmentation_workflow.py    # seg_main()
    ├── thumb_workflow.py           # thumb_main()
    ├── classification_workflow.py  # class_main()
    └── volume_workflow.py          # vol_main()
```

> **Note:** Model weights/artifacts referenced by the notebooks need to be placed under `app/models/classifier`, `app/models/segmentation`, and `app/models/thumb` respectively before running `/process`.

A minimal `ui/index.html` is included purely to exercise the API endpoints manually — it is **not** a production frontend.

---

## Getting started

### Requirements
- Python 3.9+
- `fastapi`, `uvicorn`, `python-multipart`, `Pillow`, `matplotlib` (for the debug view), plus whatever your workflow scripts depend on (e.g. `torch`, `opencv-python`, etc.)

### Run locally

```bash
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

### Expose it publicly (optional, dev only. localtunnel is required for this)

```bash
lt --port 8000 --subdomain calorie
```

---

## API Reference

Base URL: `http://localhost:8000`

### `GET /test`

Simple health check to confirm the API is running.

**Request**
```
GET /test
```

**Response** `200 OK`
```json
{
  "ok": true,
  "message": "API is working correctly."
}
```

---

### `GET /`

Redirects to the test UI (`/ui/index.html`) if it exists on disk; otherwise returns a plain informational message. (Note: the static UI mount is currently commented out in `api.py`.)

**Request**
```
GET /
```

**Response** `200 OK` (if no UI directory is mounted)
```json
{
  "message": "Upload API available at /upload/top and /upload/side"
}
```

**Response** `307 Temporary Redirect` → `/ui/index.html` (if the UI is present)

---

### `POST /upload/top`

Uploads the **top-view** image of the meal. The file is saved as `top<ext>` inside `app/working/input_images/`, overwriting any previous top image. The original file extension is preserved (falls back to `.jpg` if none is provided).

**Request**

`multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✅ | The top-view image (`.jpg`, `.jpeg`, `.png`, etc.) |

```bash
curl -X POST "http://localhost:8000/upload/top" \
  -F "file=@/path/to/top.jpg"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "saved_as": "/app/working/input_images/top.jpg"
}
```

---

### `POST /upload/side`

Uploads the **side-view** image of the meal. The file is saved as `side<ext>` inside `app/working/input_images/`, overwriting any previous side image.

**Request**

`multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | ✅ | The side-view image (`.jpg`, `.jpeg`, `.png`, etc.) |

```bash
curl -X POST "http://localhost:8000/upload/side" \
  -F "file=@/path/to/side.jpg"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "saved_as": "/app/working/input_images/side.jpg"
}
```

---

### `POST /process`

Runs the full pipeline (segmentation → thumbnailing → classification → volume estimation → nutrition analysis) against the currently uploaded `top.*` and `side.*` images, and returns the resulting nutrition report.

Before running, all previous outputs under `app/working/` (except `input_images/`) are cleared, so each call starts from a clean state.

**Request**
```
POST /process
```
_No body required — the images must already have been uploaded via `/upload/top` and `/upload/side`._

```bash
curl -X POST "http://localhost:8000/process"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "message": "Processing completed successfully",
  "data": {
    "per_food_breakdown": {
      "biriyani": {
        "volume_cm3": 350,
        "calories_kcal": 532.7,
        "macros": {
          "carbohydrates_g": 112.0,
          "fiber_g": 5.25,
          "protein_g": 31.5,
          "fat_g": 49.0
        },
        "macro_split_%": {
          "carbs": 56,
          "protein": 16,
          "fat": 25
        },
        "minerals": {
          "sodium_mg": 175.0,
          "calcium_mg": 14.0,
          "iron_mg": 2.8
        },
        "vitamins": {
          "vit_a_ug": 175.0,
          "vit_c_mg": 0.0,
          "vit_d_ug": 0.0
        }
      }
    },
    "meal_totals": {
      "calories_kcal": 532.7,
      "carbohydrates_g": 112.0,
      "fiber_g": 5.25,
      "protein_g": 31.5,
      "fat_g": 49.0,
      "sodium_mg": 175.0,
      "calcium_mg": 14.0,
      "iron_mg": 2.8,
      "vit_a_ug": 175.0,
      "vit_c_mg": 0.0,
      "vit_d_ug": 0.0
    }
  }
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | No `top.*` image found in `input_images/` | `{"detail": "Top image not found in input_images folder"}` |
| `400 Bad Request` | No `side.*` image found in `input_images/` | `{"detail": "Side image not found in input_images folder"}` |
| `500 Internal Server Error` | Any exception raised during segmentation, thumbnailing, classification, volume estimation, or report generation | `{"detail": "Processing failed: <error message>"}` |

---

## Typical usage flow

```bash
# 1. Upload the top-view photo
curl -X POST "http://localhost:8000/upload/top" -F "file=@top.jpg"

# 2. Upload the side-view photo
curl -X POST "http://localhost:8000/upload/side" -F "file=@side.jpg"

# 3. Run the full processing pipeline
curl -X POST "http://localhost:8000/process"
```

---

## Supported foods

The nutrition knowledge base currently covers the following food items (case-insensitive, underscore-separated keys):

`hilsha_fish`, `biriyani`, `khichuri`, `morog_polao`, `yogurt`, `roshgolla`, `porota`, `bakorkhani`, `fuchka`, `roshmalai`, `kacha_golla`, `kala_bhuna`, `haleem`, `mashed_potato`, `nehari`, `kabab`, `egg_omlete`, `beguni`, `chickpeas`

Any food classified outside this list is skipped in the nutrition report (with a warning logged to the console) but does not fail the request.

---

## Notes & caveats

- CORS is currently wide open (`allow_origins=["*"]`) — restrict this before deploying publicly.
- `/upload/top` and `/upload/side` overwrite the previous file of the same view; there's no per-session/user isolation, so concurrent uploads from different clients will collide.
- `/process` deletes all prior outputs in `app/working/` (except `input_images/`) on every call.
- Model artifacts referenced by the notebooks must be placed under `app/models/classifier`, `app/models/segmentation`, and `app/models/thumb` before `/process` will succeed.
- The static UI mount (`/ui`) is present in code but currently commented out; uncomment it once a `ui/index.html` is available.
