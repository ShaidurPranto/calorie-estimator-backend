from pathlib import Path
from app.modules.classification_module import FoodClassifier


def class_main():
    print("Initializing Food Classifier...")
    classifier = FoodClassifier()
    print("✓ Classifier initialized successfully")

    BASE_DIR = Path(__file__).resolve().parents[1]
    DIRECTORY_PATH = BASE_DIR / "working"

    # classifier.classify_and_display_folder(DIRECTORY_PATH / "top_segments/")
    # classifier.classify_and_display_folder(DIRECTORY_PATH / "side_segments/")

    valid_labels = classifier.classify_and_copy_folder(DIRECTORY_PATH / "top_segments/", DIRECTORY_PATH / "categorized_top", 0.1)
    classifier.classify_and_copy_folder_with_label_filter(DIRECTORY_PATH / "side_segments/", DIRECTORY_PATH / "categorized_side", valid_labels, 0.1)