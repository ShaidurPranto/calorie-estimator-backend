# 🍽 Calorie Estimator API

A FastAPI-based service that estimates the calorie and nutrient content of a meal from two photos (a **top view** and a **side view**). The pipeline runs the images through segmentation, thumbnail generation, food classification, and volume estimation, then maps the results against an internal nutrition knowledge base to produce a full nutrition report.

---

## How it works (pipeline overview)

```
top.jpg  ─┐
           ├─► /process ─► segmentation ─► thumbnailing ─► classification ─► volume estimation ─► nutrition report
side.jpg ─┘
```

---

## Project structure

```
app/
├── main.py
├── routes.py
├── helpers.py
├── working/
│   ├── input_images/               # Uploaded top/side images live here (persisted across runs)
│   ├── segmentation-outputs/
│   │   └── masks/
│   │       ├── top/                # .npy segmentation masks for the top view
│   │       └── side/               # .npy segmentation masks for the side view
│   ├── categorized_top_npy/        # .npy files grouped by predicted food category (top view)
│   └── categorized_side_npy/       # .npy files grouped by predicted food category (side view)
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

Basic root endpoint confirming the server is up.

**Request**
```
GET /
```

**Response** `200 OK`
```json
{
  "message": "server is running"
}
```

---

### `POST /upload/top`

Uploads the **top-view** image of the meal. The file is saved as `top<ext>` inside `app/working/input_images/`, overwriting any previous top image. The original file extension is preserved (falls back to `.jpg` if none is provided or if the extension is unrecognized).

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

Before running, all previous outputs under `app/working/` (except `input_images/`) are cleared via `clean_working_directory()`, so each call starts from a clean state.

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
| `500 Internal Server Error` | `final_nutrition_output.json` was not generated by the pipeline | `{"detail": "Processing failed: Expected output file missing at <path>"}` |

---

### `GET /result/segmentation/top`

Lists all `.npy` segmentation mask files generated for the **top view**, from `working/segmentation-outputs/masks/top`.

**Request**
```
GET /result/segmentation/top
```

```bash
curl "http://localhost:8000/result/segmentation/top"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "directory": "segmentation-outputs/masks/top",
  "count": 2,
  "files": ["mask_0.npy", "mask_1.npy"]
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | The `segmentation-outputs/masks/top` directory doesn't exist yet (i.e. `/process` hasn't been run) | `{"detail": "Directory not found: <path>"}` |

---

### `GET /result/segmentation/side`

Lists all `.npy` segmentation mask files generated for the **side view**, from `working/segmentation-outputs/masks/side`.

**Request**
```
GET /result/segmentation/side
```

```bash
curl "http://localhost:8000/result/segmentation/side"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "directory": "segmentation-outputs/masks/side",
  "count": 2,
  "files": ["mask_0.npy", "mask_1.npy"]
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | The `segmentation-outputs/masks/side` directory doesn't exist yet | `{"detail": "Directory not found: <path>"}` |

---

### `GET /result/segmentation/top/{filename}`

Downloads a specific `.npy` segmentation mask file for the **top view**.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `filename` | string | Must end in `.npy`, e.g. `mask_0.npy` |

```bash
curl -O "http://localhost:8000/result/segmentation/top/mask_0.npy"
```

**Response** `200 OK` — binary file (`application/octet-stream`)

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | File doesn't exist at `working/segmentation-outputs/masks/top/<filename>` | `{"detail": "File '<filename>' not found."}` |

---

### `GET /result/segmentation/side/{filename}`

Downloads a specific `.npy` segmentation mask file for the **side view**.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `filename` | string | Must end in `.npy`, e.g. `mask_0.npy` |

```bash
curl -O "http://localhost:8000/result/segmentation/side/mask_0.npy"
```

**Response** `200 OK` — binary file (`application/octet-stream`)

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | File doesn't exist at `working/segmentation-outputs/masks/side/<filename>` | `{"detail": "File '<filename>' not found."}` |

---

### `GET /result/classification/top`

Lists all category subfolders and their `.npy` files from `working/categorized_top_npy`. Each classified food crop is grouped into a subfolder named after its predicted category.

**Request**
```
GET /result/classification/top
```

```bash
curl "http://localhost:8000/result/classification/top"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "directory": "categorized_top_npy",
  "categories": {
    "biriyani": ["crop_0.npy"],
    "yogurt": ["crop_1.npy", "crop_2.npy"]
  }
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | The `categorized_top_npy` directory doesn't exist yet | `{"detail": "Directory not found: <path>"}` |

---

### `GET /result/classification/side`

Lists all category subfolders and their `.npy` files from `working/categorized_side_npy`.

**Request**
```
GET /result/classification/side
```

```bash
curl "http://localhost:8000/result/classification/side"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "directory": "categorized_side_npy",
  "categories": {
    "biriyani": ["crop_0.npy"],
    "yogurt": ["crop_1.npy", "crop_2.npy"]
  }
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | The `categorized_side_npy` directory doesn't exist yet | `{"detail": "Directory not found: <path>"}` |

---

### `GET /result/classification/top/{category}/{filename}`

Downloads a specific classified `.npy` file for the **top view** from a given category subfolder.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `category` | string | Category subfolder name, e.g. `biriyani` (see [Supported foods](#supported-foods)) |
| `filename` | string | Must end in `.npy`, e.g. `crop_0.npy` |

```bash
curl -O "http://localhost:8000/result/classification/top/biriyani/crop_0.npy"
```

**Response** `200 OK` — binary file (`application/octet-stream`)

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | File doesn't exist at `working/categorized_top_npy/<category>/<filename>` | `{"detail": "File '<filename>' not found in category '<category>'."}` |

---

### `GET /result/classification/side/{category}/{filename}`

Downloads a specific classified `.npy` file for the **side view** from a given category subfolder.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `category` | string | Category subfolder name, e.g. `biriyani` |
| `filename` | string | Must end in `.npy`, e.g. `crop_0.npy` |

```bash
curl -O "http://localhost:8000/result/classification/side/biriyani/crop_0.npy"
```

**Response** `200 OK` — binary file (`application/octet-stream`)

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | File doesn't exist at `working/categorized_side_npy/<category>/<filename>` | `{"detail": "File '<filename>' not found in category '<category>'."}` |

---

## Typical usage flow

```bash
# 1. Upload the top-view photo
curl -X POST "http://localhost:8000/upload/top" -F "file=@top.jpg"

# 2. Upload the side-view photo
curl -X POST "http://localhost:8000/upload/side" -F "file=@side.jpg"

# 3. Run the full processing pipeline
curl -X POST "http://localhost:8000/process"

# 4. (Optional) Inspect intermediate segmentation / classification outputs
curl "http://localhost:8000/result/segmentation/top"
curl "http://localhost:8000/result/classification/top"
curl -O "http://localhost:8000/result/segmentation/top/mask_0.npy"
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
- The `/result/segmentation/*` and `/result/classification/*` endpoints only return data after a successful `/process` run — they'll 404 on a fresh working directory.
- All `/result/.../{filename}` and `/result/.../{category}/{filename}` download endpoints strictly require a `.npy` extension; any other extension is rejected with `400`.
- The static UI mount (`/ui`) is present in code but currently commented out; uncomment it once a `ui/index.html` is available.
