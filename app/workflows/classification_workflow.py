from app.modules.classification_module import FoodClassifier


def class_main():
    print("Initializing Food Classifier...")
    classifier = FoodClassifier()
    print("✓ Classifier initialized successfully")

    DIRECTORY_PATH = "/kaggle/working/"

    classifier.classify_and_display_folder(DIRECTORY_PATH + "top_segments/")
    classifier.classify_and_display_folder(DIRECTORY_PATH + "side_segments/")

    valid_labels = classifier.classify_and_copy_folder(DIRECTORY_PATH + "top_segments/","categorized_top", 0.8)
    classifier.classify_and_copy_folder_with_label_filter(DIRECTORY_PATH + "side_segments/","categorized_side", valid_labels, 0.8)


if __name__ == "__main__":
    class_main()
