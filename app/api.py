import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import shutil
import os
import glob

from app.workflows.thumb_workflow import thumb_main

app = FastAPI(title="Calorie Estimator - Upload API")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Working directory inside the app package where images should be saved
APP_DIR = Path(__file__).resolve().parent
WORKING_DIR = APP_DIR / "working" / "input_images"
WORKING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_extension(filename: str) -> str:
    """Return a safe extension (including leading dot) from the original filename.
    Falls back to `.jpg` when unknown.
    """
    ext = Path(filename).suffix
    if not ext:
        return ".jpg"
    # Keep only simple alphanumeric + dot extensions like .jpg, .png, .jpeg
    ext = ext.lower()
    if ext.startswith('.') and 1 < len(ext) <= 5:
        return ext
    return ".jpg"


async def _save_upload_file(upload: UploadFile, dest_path: Path) -> None:
    # Read and write in chunks to avoid large memory usage
    try:
        with dest_path.open("wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    finally:
        await upload.close()


def clean_working_directory():
    BASE_DIR = Path(__file__).resolve().parents[1]
    working_dir = BASE_DIR / "app" / "working"
    keep_dir = working_dir / "input_images"

    # Ensure the base directory exists before attempting to loop
    if not working_dir.exists():
        print(f"Directory {working_dir} does not exist.")
        return

    # Iterate over everything inside /working
    for item in working_dir.iterdir():
        # Skip the directory we want to keep
        if item == keep_dir:
            continue
            
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()  # Deletes files or symlinks
            elif item.is_dir():
                shutil.rmtree(item)  # Deletes directories and their contents
            print(f"Deleted: {item}")
        except Exception as e:
            print(f"Failed to delete {item}. Reason: {e}")


def analyze_food_volume(input_json_path, output_json_path="food_nutrition_report.json"):

    KCAL_PER_G = {"carbohydrates": 4, "protein": 4, "fat": 9, "fiber": 2}

    nutrition_kb = {
        "hilsha_fish":   {"carbohydrates":0.00,"fiber":0.00,"protein":0.22,"fat":0.19,"sodium_mg":0.55,"calcium_mg":0.18,"iron_mg":0.014,"vit_a_ug":0.6,"vit_c_mg":0.0,"vit_d_ug":0.8},
        "biriyani":      {"carbohydrates":0.32,"fiber":0.015,"protein":0.09,"fat":0.14,"sodium_mg":0.50,"calcium_mg":0.04,"iron_mg":0.008,"vit_a_ug":0.5,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "khichuri":      {"carbohydrates":0.22,"fiber":0.025,"protein":0.05,"fat":0.04,"sodium_mg":0.30,"calcium_mg":0.03,"iron_mg":0.010,"vit_a_ug":0.3,"vit_c_mg":0.1,"vit_d_ug":0.0},
        "morog_polao":   {"carbohydrates":0.28,"fiber":0.012,"protein":0.11,"fat":0.13,"sodium_mg":0.45,"calcium_mg":0.03,"iron_mg":0.007,"vit_a_ug":0.4,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "yogurt":        {"carbohydrates":0.05,"fiber":0.00,"protein":0.04,"fat":0.04,"sodium_mg":0.17,"calcium_mg":0.12,"iron_mg":0.001,"vit_a_ug":0.5,"vit_c_mg":0.5,"vit_d_ug":0.1},
        "roshgolla":     {"carbohydrates":0.38,"fiber":0.00,"protein":0.04,"fat":0.02,"sodium_mg":0.10,"calcium_mg":0.07,"iron_mg":0.002,"vit_a_ug":0.1,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "porota":        {"carbohydrates":0.35,"fiber":0.02,"protein":0.06,"fat":0.12,"sodium_mg":0.40,"calcium_mg":0.02,"iron_mg":0.006,"vit_a_ug":0.0,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "bakorkhani":    {"carbohydrates":0.45,"fiber":0.025,"protein":0.08,"fat":0.18,"sodium_mg":0.55,"calcium_mg":0.03,"iron_mg":0.007,"vit_a_ug":0.0,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "fuchka":        {"carbohydrates":0.20,"fiber":0.03,"protein":0.04,"fat":0.06,"sodium_mg":0.60,"calcium_mg":0.02,"iron_mg":0.012,"vit_a_ug":0.1,"vit_c_mg":1.5,"vit_d_ug":0.0},
        "roshmalai":     {"carbohydrates":0.42,"fiber":0.00,"protein":0.06,"fat":0.08,"sodium_mg":0.12,"calcium_mg":0.10,"iron_mg":0.002,"vit_a_ug":0.3,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "kacha_golla":   {"carbohydrates":0.40,"fiber":0.00,"protein":0.08,"fat":0.07,"sodium_mg":0.08,"calcium_mg":0.09,"iron_mg":0.002,"vit_a_ug":0.2,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "kala_bhuna":    {"carbohydrates":0.04,"fiber":0.005,"protein":0.24,"fat":0.22,"sodium_mg":0.80,"calcium_mg":0.02,"iron_mg":0.025,"vit_a_ug":0.2,"vit_c_mg":0.5,"vit_d_ug":0.0},
        "haleem":        {"carbohydrates":0.16,"fiber":0.035,"protein":0.09,"fat":0.07,"sodium_mg":0.55,"calcium_mg":0.04,"iron_mg":0.018,"vit_a_ug":0.1,"vit_c_mg":0.3,"vit_d_ug":0.0},
        "mashed_potato": {"carbohydrates":0.15,"fiber":0.02,"protein":0.02,"fat":0.03,"sodium_mg":0.25,"calcium_mg":0.01,"iron_mg":0.004,"vit_a_ug":0.0,"vit_c_mg":3.0,"vit_d_ug":0.0},
        "nehari":        {"carbohydrates":0.02,"fiber":0.00,"protein":0.12,"fat":0.15,"sodium_mg":0.70,"calcium_mg":0.04,"iron_mg":0.020,"vit_a_ug":0.1,"vit_c_mg":0.0,"vit_d_ug":0.0},
        "kabab":         {"carbohydrates":0.05,"fiber":0.01,"protein":0.20,"fat":0.14,"sodium_mg":0.60,"calcium_mg":0.02,"iron_mg":0.022,"vit_a_ug":0.1,"vit_c_mg":0.2,"vit_d_ug":0.0},
        "egg_omlete":    {"carbohydrates":0.01,"fiber":0.00,"protein":0.11,"fat":0.12,"sodium_mg":0.55,"calcium_mg":0.05,"iron_mg":0.015,"vit_a_ug":1.5,"vit_c_mg":0.0,"vit_d_ug":0.9},
        "beguni":        {"carbohydrates":0.18,"fiber":0.02,"protein":0.03,"fat":0.16,"sodium_mg":0.30,"calcium_mg":0.01,"iron_mg":0.005,"vit_a_ug":0.0,"vit_c_mg":0.8,"vit_d_ug":0.0},
        "chickpeas":     {"carbohydrates":0.24,"fiber":0.07,"protein":0.08,"fat":0.05,"sodium_mg":0.15,"calcium_mg":0.05,"iron_mg":0.025,"vit_a_ug":0.1,"vit_c_mg":0.5,"vit_d_ug":0.0},
    }

    def bar(val, total, width=20):
        filled = int((val / total) * width) if total else 0
        return "█" * filled + "░" * (width - filled)

    MACRO_MAX = {"carbs": 275, "protein": 50, "fat": 78, "fiber": 28}

    if not os.path.exists(input_json_path):
        print(f"Error: '{input_json_path}' does not exist.")
        return

    with open(input_json_path, 'r') as f:
        try:
            input_data = json.load(f)
        except json.JSONDecodeError:
            print("Error: Invalid JSON format.")
            return

    report = {}
    meal_totals = {k: 0.0 for k in ["calories_kcal","carbohydrates_g","fiber_g","protein_g","fat_g","sodium_mg","calcium_mg","iron_mg","vit_a_ug","vit_c_mg","vit_d_ug"]}

    print("\n" + "═" * 58)
    print(f"{'🍽  DIET NUTRITION REPORT':^58}")
    print("═" * 58)

    for food_name, volume in input_data.items():
        key = food_name.strip().lower()
        if key not in nutrition_kb:
            print(f"\n⚠  '{food_name}' not recognized — skipping.")
            continue

        d = nutrition_kb[key]
        carbs   = round(d["carbohydrates"] * volume, 2)
        fiber   = round(d["fiber"] * volume, 2)
        protein = round(d["protein"] * volume, 2)
        fat     = round(d["fat"] * volume, 2)
        sodium  = round(d["sodium_mg"] * volume, 1)
        calcium = round(d["calcium_mg"] * volume, 1)
        iron    = round(d["iron_mg"] * volume, 2)
        vit_a   = round(d["vit_a_ug"] * volume, 1)
        vit_c   = round(d["vit_c_mg"] * volume, 1)
        vit_d   = round(d["vit_d_ug"] * volume, 2)

        calories = round(
            carbs * KCAL_PER_G["carbohydrates"] +
            protein * KCAL_PER_G["protein"] +
            fat * KCAL_PER_G["fat"] +
            fiber * KCAL_PER_G["fiber"], 1
        )

        total_macro_g = carbs + protein + fat + fiber
        c_pct = round(carbs / total_macro_g * 100) if total_macro_g else 0
        p_pct = round(protein / total_macro_g * 100) if total_macro_g else 0
        f_pct = round(fat / total_macro_g * 100) if total_macro_g else 0

        for k, v in [("calories_kcal",calories),("carbohydrates_g",carbs),("fiber_g",fiber),
                     ("protein_g",protein),("fat_g",fat),("sodium_mg",sodium),
                     ("calcium_mg",calcium),("iron_mg",iron),("vit_a_ug",vit_a),
                     ("vit_c_mg",vit_c),("vit_d_ug",vit_d)]:
            meal_totals[k] = round(meal_totals[k] + v, 2)

        report[food_name] = {
            "volume_cm3": volume,
            "calories_kcal": calories,
            "macros": {"carbohydrates_g":carbs,"fiber_g":fiber,"protein_g":protein,"fat_g":fat},
            "macro_split_%": {"carbs":c_pct,"protein":p_pct,"fat":f_pct},
            "minerals": {"sodium_mg":sodium,"calcium_mg":calcium,"iron_mg":iron},
            "vitamins": {"vit_a_ug":vit_a,"vit_c_mg":vit_c,"vit_d_ug":vit_d},
        }

        print(f"\n┌─ {food_name.upper().replace('_',' ')} ({'%.0f' % volume} cm³)")
        print(f"│  🔥 Calories   : {calories} kcal")
        print(f"│")
        print(f"│  MACROS")
        print(f"│  🌾 Carbs      : {carbs}g ")
        print(f"│  🥩 Protein    : {protein}g ")
        print(f"│  🫙 Fat        : {fat}g ")
        print(f"│  🌿 Fiber      : {fiber}g ")
        print(f"│")
        print(f"│  MINERALS & VITAMINS")
        print(f"│  🧂 Sodium     : {sodium}mg   💪 Calcium: {calcium}mg   🩸 Iron: {iron}mg")
        print(f"│  🥕 Vit A      : {vit_a}µg    🍋 Vit C : {vit_c}mg    ☀  Vit D: {vit_d}µg")
        print(f"└{'─'*55}")

    # ── MEAL SUMMARY ───────────────────────────────────────────────────────────
    print(f"\n{'═'*58}")
    print(f"{'📋  TOTAL MEAL SUMMARY':^58}")
    print(f"{'═'*58}")
    print(f"  🔥 Total Calories  : {meal_totals['calories_kcal']} kcal")
    print(f"  🌾 Total Carbs     : {meal_totals['carbohydrates_g']}g")
    print(f"  🥩 Total Protein   : {meal_totals['protein_g']}g")
    print(f"  🫙 Total Fat       : {meal_totals['fat_g']}g")
    print(f"  🌿 Total Fiber     : {meal_totals['fiber_g']}g")
    print(f"  🧂 Total Sodium    : {meal_totals['sodium_mg']}mg")
    print(f"  💪 Total Calcium   : {meal_totals['calcium_mg']}mg")
    print(f"  🩸 Total Iron      : {meal_totals['iron_mg']}mg")
    print(f"  🥕 Total Vit A     : {meal_totals['vit_a_ug']}µg")
    print(f"  🍋 Total Vit C     : {meal_totals['vit_c_mg']}mg")
    print(f"  ☀  Total Vit D     : {meal_totals['vit_d_ug']}µg")
    print(f"{'═'*58}\n")

    final_output = {
        "per_food_breakdown": report,
        "meal_totals": meal_totals,
    }

    with open(output_json_path, 'w') as out:
        json.dump(final_output, out, indent=2)

    print(f"[✓] Report saved → {output_json_path}\n")


def display_food_views(folder_path):
    valid_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
    top_image_path = None
    side_image_path = None

    for file in os.listdir(folder_path):
        name, ext = os.path.splitext(file)
        if ext in valid_extensions:
            if name.lower() == 'top':
                top_image_path = os.path.join(folder_path, file)
            elif name.lower() == 'side':
                side_image_path = os.path.join(folder_path, file)

    if not top_image_path or not side_image_path:
        print("Error: Could not find both 'top' and 'side' images in the folder.")
        if top_image_path: print(f"Found top view: {top_image_path}")
        if side_image_path: print(f"Found side view: {side_image_path}")
        return

    try:
        top_img = Image.open(top_image_path)
        side_img = Image.open(side_image_path)

        fig, axes = plt.subplots(1, 2, figsize=(10, 5))
        axes[0].imshow(top_img)
        axes[0].set_title("Top View", fontsize=14, fontweight='bold')
        axes[0].axis('off')
        axes[1].imshow(side_img)
        axes[1].set_title("Side View", fontsize=14, fontweight='bold')
        axes[1].axis('off')
        plt.tight_layout()
        plt.show()

    except Exception as e:
        print(f"An error occurred while loading or displaying the images: {e}")


@app.get("/test")
async def test_api():
    """Test endpoint for API validation."""
    return JSONResponse({"ok": True, "message": "API is working correctly."})


@app.post("/upload/top")
async def upload_top(file: UploadFile = File(...)):
    """Upload the top view image and save as `top<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / f"top{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.post("/upload/side")
async def upload_side(file: UploadFile = File(...)):
    """Upload the side view image and save as `side<ext>` in `app/working/input_images`.

    The original file extension is preserved.
    """
    ext = _safe_extension(file.filename)
    dest = WORKING_DIR / f"side{ext}"
    await _save_upload_file(file, dest)
    return JSONResponse({"ok": True, "saved_as": str(dest)})


@app.get("/")
def root():
    """Redirect to the UI test page if present, otherwise return a short message."""
    index = UI_DIR / "index.html"
    if index.exists():
        return RedirectResponse(url="/ui/index.html")
    return {"message": "Upload API available at /upload/top and /upload/side"}


@app.post("/process")
async def process():
    """Check if both top and side images exist, then run full processing workflow.
    
    Returns:
        - {"ok": True, "message": "Processing completed"} on success
        - 400 error if either image is missing
        - 500 error if processing fails
    """
    # Check if both top and side images exist
    top_files = glob.glob(str(WORKING_DIR / "top.*"))
    side_files = glob.glob(str(WORKING_DIR / "side.*"))
    
    if not top_files:
        raise HTTPException(status_code=400, detail="Top image not found in input_images folder")
    if not side_files:
        raise HTTPException(status_code=400, detail="Side image not found in input_images folder")
    

    # clear outputs from previous processing
    # delete everything from /working except /working/input_images
    clean_working_directory()

    
    try:
        # Import and run the segmentation workflow
        from app.workflows.segmentation_workflow import seg_main
        seg_main()

        # Import and run thumb workflow
        from app.workflows.thumb_workflow import thumb_main
        thumb_main()

        # Import and run classifier workflow
        from app.workflows.classification_workflow import class_main
        class_main()

        # Import and run volume workflow
        from app.workflows.volume_workflow import vol_main
        vol_main()

        # Generate final output
        BASE_DIR = Path(__file__).resolve().parents[1]
        display_food_views(BASE_DIR / "app" / "working" / "input_images")
        final_output_path = BASE_DIR / "app" / "working" / "final_nutrition_output.json"
        analyze_food_volume(BASE_DIR / "app" / "working" / "food_volumes_summary.json", final_output_path)

        # Ensure the file exists before reading it
        if not final_output_path.exists():
            raise FileNotFoundError(f"Expected output file missing at {final_output_path}")

        # Read the generated JSON file
        with open(final_output_path, "r") as f:
            nutrition_data = json.load(f)

        # Return the success message along with the loaded JSON data
        return JSONResponse({
            "ok": True, 
            "message": "Processing completed successfully",
            "data": nutrition_data
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")



# Serve the simple frontend under /ui (ui/index.html)
# UI_DIR = Path(__file__).resolve().parent.parent / "ui"
# if UI_DIR.exists():
#     app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")

if __name__ == "__main__":
    # Simple launcher for manual tests
    import uvicorn
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)


# lt --port 8000 --subdomain calorie