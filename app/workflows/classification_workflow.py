from pathlib import Path
from app.modules.classification_module import FoodClassifier
import json
import os


def create_json_file(directory_path, file_name):
    """Creates an empty .json file with the given name in the specified directory."""
    # Ensure the file name ends with .json
    if not file_name.endswith(".json"):
        file_name += ".json"

    # Combine the directory path and file name safely
    file_path = os.path.join(directory_path, file_name)

    # Optional: Create the directory if it doesn't exist yet
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    # Write an empty JSON object ({}) to the file
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump({}, json_file)

    print(f"Successfully created: {file_path}")
    

def class_main():
    print("Initializing Food Classifier...")
    classifier = FoodClassifier()
    print("✓ Classifier initialized successfully")

    BASE_DIR = Path(__file__).resolve().parents[1]
    DIRECTORY_PATH = BASE_DIR / "working"

    # classifier.classify_and_display_folder(DIRECTORY_PATH / "top_segments/")
    # classifier.classify_and_display_folder(DIRECTORY_PATH / "side_segments/")

    valid_labels = classifier.classify_and_copy_folder(DIRECTORY_PATH / "top_segments/", DIRECTORY_PATH / "categorized_top", 0.8)

    # progresss tracking code block
    progress_dir = os.path.join(DIRECTORY_PATH, "progress")
    create_json_file(progress_dir, f"classification_top.json")
    print(f"file created: classification_top.json")

    classifier.classify_and_copy_folder_with_label_filter(DIRECTORY_PATH / "side_segments/", DIRECTORY_PATH / "categorized_side", valid_labels, 0.6)

    # progress tracking code block
    progress_dir = os.path.join(DIRECTORY_PATH, "progress")
    create_json_file(progress_dir, f"classification_side.json")
    print(f"file created: classification_side.json")