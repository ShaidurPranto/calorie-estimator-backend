# 🍽 Calorie Estimator API

A FastAPI-based service that estimates the calorie and nutrient content of a meal from two photos (a **top view** and a **side view**). The pipeline runs the images through segmentation, thumbnail generation, food classification, and volume estimation, then maps the results against an internal nutrition knowledge base to produce a full nutrition report.

---

## How it works (pipeline overview)

`/process` no longer blocks until the whole pipeline finishes — it queues the
job in the background and responds immediately. There is no separate status
tracker: `GET /result/state` simply scans `working/progress/` for the
`*.json` marker files each stage writes when it finishes, and reports back
exactly what it finds.

```
top.jpg  ─┐
           ├─► POST /process  (returns immediately, work starts in background)
side.jpg ─┘         │
                     ▼
     segmentation ─► thumbnailing ─► classification ─► volume estimation
     (top + side)     (top + side)     (top + side)

     each stage writes working/progress/<stage>.json the moment it finishes

                     │
                     ▼
     GET /result/state          -> scans working/progress/*.json, reports what's done
     GET /volume-estimation     -> once "volume" is done, returns the report
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
│   ├── progress/                   # Stage marker files — one <stage>.json per finished stage, nothing else
│   │   ├── segmentation_top.json   # Written when top-view segmentation finishes
│   │   ├── segmentation_side.json  # Written when side-view segmentation finishes
│   │   ├── thumb_top.json          # Written when top-view thumbnailing finishes
│   │   ├── thumb_side.json         # Written when side-view thumbnailing finishes
│   │   ├── classification_top.json # Written when top-view classification finishes
│   │   ├── classification_side.json# Written when side-view classification finishes
│   │   └── volume.json             # Written when volume estimation finishes (the last stage)
│   ├── segmentation-outputs/
│   │   └── masks/
│   │       ├── top/                # .npy segmentation masks for the top view
│   │       └── side/               # .npy segmentation masks for the side view
│   ├── categorized_top_npy/        # .npy files grouped by predicted food category (top view)
│   └── categorized_side_npy/       # .npy files grouped by predicted food category (side view)
├── models/
│   ├── classifier/                 # Input models for the classification workflow (from notebook)
│   ├── segmentation/                # Input models for the segmentation workflow (from notebook)
│   └── thumb/                      # Input models for the thumbnail workflow (from notebook)
└── workflows/
    ├── segmentation_workflow.py    # seg_main()
    ├── thumb_workflow.py           # thumb_main()
    ├── classification_workflow.py  # class_main()
    └── volume_workflow.py          # vol_main()
```

> **Note:** Model weights/artifacts referenced by the notebooks need to be placed under `app/models/classifier`, `app/models/segmentation`, and `app/models/thumb` respectively before running `/process`.

> **Note:** Each workflow module (`seg_main`, `thumb_main`, `class_main`, `vol_main`) is responsible for writing its own `working/progress/<stage>.json` marker file the moment it finishes (e.g. `seg_main()` writes both `segmentation_top.json` and `segmentation_side.json` once each view is done). `GET /result/state` and every `/result/*` endpoint only ever look at whether that file exists — a stage that doesn't write its marker will look permanently "not completed" to the API.

A minimal `ui/index.html` is included purely to exercise the API endpoints manually — it is **not** a production frontend. It uploads both images, calls `POST /process`, waits a fixed delay, then polls `GET /result/state` on a fixed interval and reacts the moment each stage shows up, in order: fetch + draw the top masks once `segmentation_top` is done, then the side masks once `segmentation_side` is done, then label the already-fetched top masks once `classification_top` is done, then the side ones once `classification_side` is done, then fetch the report from `GET /volume-estimation` once `volume` is done.

---

## Getting started

### Requirements
- Python 3.9+
- `fastapi`, `uvicorn`, `python-multipart`, `Pillow`, `matplotlib` (for the debug view), `numpy`, plus whatever your workflow scripts depend on (e.g. `torch`, `opencv-python`, etc.)

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

**Queues** the full pipeline (segmentation → thumbnailing → classification → volume estimation → nutrition analysis) against the currently uploaded `top.*` and `side.*` images and **returns immediately** — it does not wait for the pipeline to finish. The pipeline runs in a background task on the server.

Before queuing, all previous outputs under `app/working/` (except `input_images/`) are cleared via `clean_working_directory()`, so each call starts from a clean state — this also clears out any `working/progress/*.json` markers left over from a prior run.

Use `GET /result/state` to see what's finished, and `GET /volume-estimation` once the `volume` marker exists to fetch the report — this replaces the report payload `/process` used to return directly.

**Request**
```
POST /process
```
_No body required — the images must already have been uploaded via `/upload/top` and `/upload/side`._

```bash
curl -X POST "http://localhost:8000/process"
```

**Response** `200 OK` — returned as soon as the job is queued, not when it finishes
```json
{
    "ok": true,
    "message": "Processing has been started in the background.",
    "check_state_at": "/result/state",
    "result_at": "/volume-estimation"
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | No `top.*` image found in `input_images/` | `{"detail": "Top image not found in input_images folder"}` |
| `400 Bad Request` | No `side.*` image found in `input_images/` | `{"detail": "Side image not found in input_images folder"}` |

---

### `GET /result/state`

Scans `working/progress/` for `*.json` marker files and reports back exactly what it finds — no separate status is tracked or computed. Poll this after `POST /process` to know what's finished so far.

**Request**
```
GET /result/state
```

```bash
curl "http://localhost:8000/result/state"
```

**Response** `200 OK`
```json
{
    "ok": true,
    "completed_stages": ["segmentation_side", "segmentation_top", "thumb_side", "thumb_top"],
    "stages": {
        "segmentation_top": true,
        "segmentation_side": true,
        "thumb_top": true,
        "thumb_side": true,
        "classification_top": false,
        "classification_side": false,
        "volume": false
    }
}
```

`completed_stages` is simply the list of `.json` filenames (minus extension) currently present in `working/progress/`, sorted alphabetically. `stages` is the same information reshaped as a fixed set of booleans, one per known stage, for convenience.

---

### `GET /volume-estimation`

Returns the final nutrition report — the same payload shape `/process` used to return directly before processing became asynchronous.

- If `working/progress/volume.json` exists, it reads `final_nutrition_output.json` and returns it.
- If not, it responds `202 Accepted` with the current `completed_stages` list instead of an error, so callers can distinguish "still working" from a real failure.

**Request**
```
GET /volume-estimation
```

```bash
curl "http://localhost:8000/volume-estimation"
```

**Response** `200 OK` — once volume estimation has completed
```json
{
    "ok": true,
    "message": "Processing completed successfully",
    "data": {
        "per_food_breakdown": {
            "porota": {
                "volume_cm3": 80.0,
                "calories_kcal": 220.8,
                "macros": {
                    "carbohydrates_g": 28.0,
                    "fiber_g": 1.6,
                    "protein_g": 4.8,
                    "fat_g": 9.6
                },
                "macro_split_%": {
                    "carbs": 64,
                    "protein": 11,
                    "fat": 22
                },
                "minerals": {
                    "sodium_mg": 32.0,
                    "calcium_mg": 1.6,
                    "iron_mg": 0.48
                },
                "vitamins": {
                    "vit_a_ug": 0.0,
                    "vit_c_mg": 0.0,
                    "vit_d_ug": 0.0
                }
            },
            "yogurt": {
                "volume_cm3": 24.0,
                "calories_kcal": 17.3,
                "macros": {
                    "carbohydrates_g": 1.2,
                    "fiber_g": 0.0,
                    "protein_g": 0.96,
                    "fat_g": 0.96
                },
                "macro_split_%": {
                    "carbs": 38,
                    "protein": 31,
                    "fat": 31
                },
                "minerals": {
                    "sodium_mg": 4.1,
                    "calcium_mg": 2.9,
                    "iron_mg": 0.02
                },
                "vitamins": {
                    "vit_a_ug": 12.0,
                    "vit_c_mg": 12.0,
                    "vit_d_ug": 2.4
                }
            }
        },
        "meal_totals": {
            "calories_kcal": 238.1,
            "carbohydrates_g": 29.2,
            "fiber_g": 1.6,
            "protein_g": 5.76,
            "fat_g": 10.56,
            "sodium_mg": 36.1,
            "calcium_mg": 4.5,
            "iron_mg": 0.5,
            "vit_a_ug": 12.0,
            "vit_c_mg": 12.0,
            "vit_d_ug": 2.4
        }
    }
}
```

**Response** `202 Accepted` — volume estimation hasn't completed yet
```json
{
    "ok": false,
    "message": "Volume estimation has not completed yet.",
    "completed_stages": ["segmentation_side", "segmentation_top", "thumb_side", "thumb_top"]
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `500 Internal Server Error` | `volume.json` marker exists but `final_nutrition_output.json` is missing | `{"detail": "volume.json marker exists but expected output file missing at <path>"}` |

---

### `GET /result/segmentation/top`

Lists all `.npy` segmentation mask files generated for the **top view**, from `working/segmentation-outputs/masks/top`. Gated on `working/progress/segmentation_top.json` existing.

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
| `404 Not Found` | `working/progress/segmentation_top.json` doesn't exist yet | `{"detail": "Top segmentation has not completed yet."}` |

---

### `GET /result/segmentation/side`

Lists all `.npy` segmentation mask files generated for the **side view**, from `working/segmentation-outputs/masks/side`. Gated on `working/progress/segmentation_side.json` existing.

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
| `404 Not Found` | `working/progress/segmentation_side.json` doesn't exist yet | `{"detail": "Side segmentation has not completed yet."}` |

---

### `GET /result/segmentation/top/content/{filename}`

Loads a specific `.npy` segmentation mask file for the **top view** and returns its contents inline as JSON, instead of as a binary download. The array is read with `numpy.load(..., allow_pickle=False)` and converted to a nested Python list via `.tolist()`. Gated on `working/progress/segmentation_top.json` existing.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `filename` | string | Must end in `.npy`, e.g. `mask_0.npy` |

```
GET /result/segmentation/top/content/{filename}
```

```bash
curl "http://localhost:8000/result/segmentation/top/content/mask_0.npy"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "filename": "mask_0.npy",
  "mask": [[0, 0, 1], [0, 1, 1], [1, 1, 1]]
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | `working/progress/segmentation_top.json` doesn't exist yet | `{"detail": "Top segmentation has not completed yet."}` |
| `404 Not Found` | File doesn't exist at `working/segmentation-outputs/masks/top/<filename>` | `{"detail": "File '<filename>' not found."}` |
| `500 Internal Server Error` | The file exists but couldn't be loaded/parsed as a numpy array | `{"detail": "Error reading or parsing the segmentation file: <error message>"}` |

---

### `GET /result/segmentation/side/content/{filename}`

Loads a specific `.npy` segmentation mask file for the **side view** and returns its contents inline as JSON, instead of as a binary download. Gated on `working/progress/segmentation_side.json` existing.

**Request**

| Path param | Type | Description |
|------------|------|-------------|
| `filename` | string | Must end in `.npy`, e.g. `mask_0.npy` |

```
GET /result/segmentation/side/content/{filename}
```

```bash
curl "http://localhost:8000/result/segmentation/side/content/mask_0.npy"
```

**Response** `200 OK`
```json
{
  "ok": true,
  "filename": "mask_0.npy",
  "mask": [[0, 0, 1], [0, 1, 1], [1, 1, 1]]
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `400 Bad Request` | `filename` doesn't end in `.npy` | `{"detail": "Only .npy files are allowed."}` |
| `404 Not Found` | `working/progress/segmentation_side.json` doesn't exist yet | `{"detail": "Side segmentation has not completed yet."}` |
| `404 Not Found` | File doesn't exist at `working/segmentation-outputs/masks/side/<filename>` | `{"detail": "File '<filename>' not found."}` |
| `500 Internal Server Error` | The file exists but couldn't be loaded/parsed as a numpy array | `{"detail": "Error reading the segmentation file: <error message>"}` |

---

### `GET /result/classification/top`

Lists all category subfolders and their `.npy` filenames from `working/categorized_top_npy` — this is a **listing endpoint only**. There is no separate "fetch classification file content" endpoint: every filename it lists is one of the files `/result/segmentation/top/content/{filename}` already served, so the client uses this purely to look up which already-fetched mask belongs to which category (masks that don't appear in any category here simply have no label). Gated on `working/progress/classification_top.json` existing.

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
    "biriyani": ["mask_0.npy"],
    "yogurt": ["mask_1.npy", "mask_2.npy"]
  }
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | `working/progress/classification_top.json` doesn't exist yet | `{"detail": "Top classification has not completed yet."}` |

---

### `GET /result/classification/side`

Lists all category subfolders and their `.npy` filenames from `working/categorized_side_npy` — same listing-only behavior as `/result/classification/top`. Gated on `working/progress/classification_side.json` existing.

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
    "biriyani": ["mask_0.npy"],
    "yogurt": ["mask_2.npy"]
  }
}
```

**Error responses**

| Status | Condition | Body |
|--------|-----------|------|
| `404 Not Found` | `working/progress/classification_side.json` doesn't exist yet | `{"detail": "Side classification has not completed yet."}` |
