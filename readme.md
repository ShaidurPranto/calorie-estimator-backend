Add necessary input models from notebook under
/app/models/classifer
/app/models/segmentation
/app/models/thumb


UI is made just to test the APIs


# Result APIs

## GET /result/segmentation/top

Returns all segmentation mask `.npy` files generated for the top-view image.

### Directory checked

```text
app/working/segmentation-outputs/masks/top
```

### Request

```http
GET /result/segmentation/top
```

### Success Response (200)

```json
{
  "ok": true,
  "directory": "working/segmentation-outputs/masks/top",
  "count": 3,
  "files": [
    "mask_1.npy",
    "mask_2.npy",
    "mask_3.npy"
  ]
}
```

### Error Response (404)

```json
{
  "detail": "Directory not found: ..."
}
```

---

## GET /result/classification/top

Returns all category folders and the `.npy` files contained in each category.

### Directory checked

```text
app/working/categorized_top_npy
```

### Request

```http
GET /result/classification/top
```

### Success Response (200)

```json
{
  "ok": true,
  "directory": "working/categorized_top_npy",
  "categories": {
    "biriyani": [
      "0.npy",
      "1.npy"
    ],
    "egg_omlete": [
      "0.npy"
    ],
    "fuchka": [
      "0.npy",
      "1.npy",
      "2.npy"
    ]
  }
}
```

### Error Response (404)

```json
{
  "detail": "Directory not found: ..."
}
```
