import os
from pathlib import Path
import shutil
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import timm

BASE_DIR = Path(__file__).resolve().parents[1]

class FoodClassifier:
    """
    A classifier module for food image classification using Vision Transformer.
    """

    def __init__(self):
        """
        Initialize the FoodClassifier.
        """
        self.model_path = BASE_DIR / "models" / "classifier" / "v2" / "model_1_vit_segment_aware.pth"
        self.labels_path = BASE_DIR / "models" / "classifier" / "v2" / "labels.txt"
        # self.num_classes = 19  # this is for v1
        self.num_classes = 7   # this is for v2
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load labels
        self.labels = self._load_labels()

        # Define image transformation pipeline
        self.transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ])

        # Load the model
        self.model = self._load_model()
        self.model.to(self.device)
        self.model.eval()

    def _load_labels(self):
        """
        Load the class labels from the labels file.

        Returns:
            list: List of class names.
        """
        if not os.path.exists(self.labels_path):
            raise FileNotFoundError(f"Labels file not found at {self.labels_path}")
            
        with open(self.labels_path, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f if line.strip()]
            
        if len(labels) != self.num_classes:
            print(f"Warning: Expected {self.num_classes} labels, found {len(labels)}")
            
        return labels

    def _load_model(self):
        """
        Load the model from checkpoint.

        Returns:
            torch.nn.Module: Loaded model
        """
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at {self.model_path}")

        checkpoint = torch.load(self.model_path, map_location=self.device)

        # Create model architecture
        model = timm.create_model(
            "vit_base_patch16_224_in21k", # this is for v2
            # "vit_small_patch16_224", # this is for v1
            pretrained=False,
            num_classes=self.num_classes
        )

        # Load state dict
        if "model_state_dict" in checkpoint:
            model.load_state_dict(checkpoint["model_state_dict"])
        else:
            model.load_state_dict(checkpoint)

        return model

    def classify_by_image(self, image):
        """
        Classify a food image directly from PIL Image object.

        Args:
            image (PIL.Image): PIL Image object

        Returns:
            dict: Dictionary containing:
                  - 'class_index': Predicted class index
                  - 'class_name': Predicted class name
                  - 'confidence': Confidence score (softmax probability)
        """
        if not isinstance(image, Image.Image):
            raise TypeError("Input must be a PIL Image object")

        # Apply transforms
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)

        # Perform inference
        with torch.no_grad():
            outputs = self.model(image_tensor)
            probabilities = torch.softmax(outputs, dim=1)
            class_index = outputs.argmax(dim=1).item()
            confidence = probabilities[0, class_index].item()
            
        class_name = self.labels[class_index] if class_index < len(self.labels) else f"Unknown ({class_index})"

        return {
            'class_index': class_index,
            'class_name': class_name,
            'confidence': confidence
        }

    def classify_by_path(self, image_path):
        """
        Classify a food image from file path.

        Args:
            image_path (str): Path to the image file

        Returns:
            dict: Dictionary containing:
                  - 'class_index': Predicted class index
                  - 'class_name': Predicted class name
                  - 'confidence': Confidence score (softmax probability)
                  - 'image_path': Original image path
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found at {image_path}")

        # Open image
        try:
            image = Image.open(image_path)

            if image.mode in ("RGBA", "P"):
                image = image.convert("RGBA")
                # Create a white background to paste transparent pixels over
                background = Image.new("RGB", image.size, (255, 255, 255)) 
                background.paste(image, mask=image.split()[3]) # 3 is the alpha channel
                img = background
            else:
                img = image.convert("RGB")
        except Exception as e:
            raise ValueError(f"Failed to open image: {e}")

        # Classify using image
        result = self.classify_by_image(img)
        result['image_path'] = image_path

        return result

    def classify_and_display_subfolders(self, root_folder_path: str):
        """
        Classifies and displays all images within subfolders of the given root folder.
        
        Args:
            root_folder_path (str): Path to the root folder containing subfolders with images.
        """
        if not os.path.exists(root_folder_path):
            raise FileNotFoundError(f"Root folder not found at {root_folder_path}")
            
        import matplotlib.pyplot as plt
        
        valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        
        subfolders = [f for f in os.listdir(root_folder_path) 
                      if os.path.isdir(os.path.join(root_folder_path, f))]
        subfolders = sorted(subfolders)
        
        for subfolder in subfolders:
            subfolder_path = os.path.join(root_folder_path, subfolder)
            print(f"\n--- Processing subfolder: {subfolder} ---")
            
            image_files = [f for f in os.listdir(subfolder_path) if f.lower().endswith(valid_extensions)]
            image_files = sorted(image_files)
            
            if not image_files:
                print(f"No images found in {subfolder}")
                continue
                
            for img_name in image_files:
                img_path = os.path.join(subfolder_path, img_name)
                try:
                    result = self.classify_by_path(img_path)
                    
                    # Display the image with its prediction
                    img = Image.open(img_path)
                    plt.figure(figsize=(6, 6))
                    plt.imshow(img)
                    plt.title(f"File: {img_name}\nClass: {result['class_name']} | Confidence: {result['confidence']:.4f}")
                    plt.axis('off')
                    plt.show()
                except Exception as e:
                    print(f"Failed to process {img_name}: {e}")


    def classify_and_display_folder(self, folder_path: str):
        """
        Classifies and displays all images within the given folder.
        
        Args:
            folder_path (str): Path to the folder containing images.
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found at {folder_path}")
            
        import matplotlib.pyplot as plt
        
        valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        
        print(f"\n--- Processing folder: {folder_path} ---")
        
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        image_files = sorted(image_files)
        
        if not image_files:
            print(f"No images found in {folder_path}")
            return
            
        for img_name in image_files:
            img_path = os.path.join(folder_path, img_name)
            try:
                result = self.classify_by_path(img_path)
                
                # Display the image with its prediction
                img = Image.open(img_path)
                plt.figure(figsize=(6, 6))
                plt.imshow(img)
                plt.title(f"File: {img_name}\nClass: {result['class_name']} | Confidence: {result['confidence']:.4f}")
                plt.axis('off')
                plt.show()
            except Exception as e:
                print(f"Failed to process {img_name}: {e}")



    def classify_and_copy_folder(self, folder_path: str, output_dir: str, threshold: float = 0.0):
        """
        Classify all images in a folder and copy confident predictions into label folders.

        Args:
            folder_path (str): Path to the folder containing images.
            output_dir (str): Directory where label folders will be created.
            threshold (float): Minimum confidence required to copy an image.

        Returns:
            list[str]: Unique label names inferred from images in the folder.
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found at {folder_path}")

        os.makedirs(output_dir, exist_ok=True)

        valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        image_files = sorted(image_files)

        created_labels = []
        seen_labels = set()

        for img_name in image_files:
            img_path = os.path.join(folder_path, img_name)

            try:
                result = self.classify_by_path(img_path)
                if result['confidence'] < threshold:
                    continue

                label_name = result['class_name']
                label_dir = os.path.join(output_dir, label_name)

                if label_name not in seen_labels:
                    created_labels.append(label_name)
                    seen_labels.add(label_name)

                if not os.path.exists(label_dir):
                    os.makedirs(label_dir, exist_ok=True)

                destination_path = os.path.join(label_dir, img_name)
                shutil.copy2(img_path, destination_path)

            except Exception as e:
                print(f"Failed to process {img_name}: {e}")

        return created_labels


    def _classify_image_with_allowed_labels(self, image, allowed_labels):
        """
        Classify an image by selecting the highest-confidence label from an allowed list.

        Args:
            image (PIL.Image): PIL image to classify.
            allowed_labels (list[str]): Labels that are eligible for selection.

        Returns:
            dict | None: Prediction details, or None if none of the allowed labels exist.
        """
        if not isinstance(image, Image.Image):
            raise TypeError("Input must be a PIL Image object")

        allowed_label_set = {str(label).strip() for label in allowed_labels if str(label).strip()}
        if not allowed_label_set:
            raise ValueError("allowed_labels must contain at least one non-empty label")

        image_tensor = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(image_tensor)
            probabilities = torch.softmax(outputs, dim=1)[0]

        eligible_predictions = [
            (index, label, probabilities[index].item())
            for index, label in enumerate(self.labels)
            if label in allowed_label_set
        ]

        if not eligible_predictions:
            return None

        class_index, class_name, confidence = max(eligible_predictions, key=lambda item: item[2])

        return {
            'class_index': class_index,
            'class_name': class_name,
            'confidence': confidence
        }

    def classify_and_copy_folder_with_label_filter(self, folder_path: str, output_dir: str, allowed_labels: list[str], threshold: float = 0.0):
        """
        Classify all images in a folder using only the provided labels, then copy confident results.

        Args:
            folder_path (str): Path to the folder containing images.
            output_dir (str): Directory where label folders will be created.
            allowed_labels (list[str]): Labels that are allowed to be considered for each image.
            threshold (float): Minimum confidence required to copy an image.

        Returns:
            list[str]: Label names for which new folders were created in the output directory.
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found at {folder_path}")

        os.makedirs(output_dir, exist_ok=True)

        valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)]
        image_files = sorted(image_files)

        created_labels = []
        created_label_set = set()

        for img_name in image_files:
            img_path = os.path.join(folder_path, img_name)

            try:
                image = Image.open(img_path)

                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGBA")
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])
                    img = background
                else:
                    img = image.convert("RGB")

                result = self._classify_image_with_allowed_labels(img, allowed_labels)
                if result is None or result['confidence'] < threshold:
                    continue

                label_name = result['class_name']
                label_dir = os.path.join(output_dir, label_name)

                if not os.path.exists(label_dir):
                    os.makedirs(label_dir, exist_ok=True)
                    if label_name not in created_label_set:
                        created_labels.append(label_name)
                        created_label_set.add(label_name)

                destination_path = os.path.join(label_dir, img_name)
                shutil.copy2(img_path, destination_path)

            except Exception as e:
                print(f"Failed to process {img_name}: {e}")

        return created_labels
