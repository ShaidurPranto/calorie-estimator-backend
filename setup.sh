#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_URL="https://github.com/ShaidurPranto/calorie-estimator-backend.git"
readonly CLASSIFIER_URL="https://www.kaggle.com/api/v1/datasets/download/ifty3110/food-classifier-models-v2-seg"
readonly SEGMENTATION_URL="https://www.kaggle.com/api/v1/datasets/download/ifty3110/segmentation-module-checkpoints-config"
readonly THUMB_URL="https://www.kaggle.com/api/v1/datasets/download/intesartahmidalam/finger-detector-and-calibration-files"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR=""
TEMP_DIR=""

cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf -- "$TEMP_DIR"
    fi
}

fail() {
    printf 'Setup failed: %s\n' "$1" >&2
    exit 1
}

trap cleanup EXIT

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

download_and_extract() {
    local name="$1"
    local url="$2"
    local archive="$TEMP_DIR/$name.zip"
    local extract_dir="$TEMP_DIR/$name"

    printf 'Downloading %s model archive...\n' "$name"
    curl --fail --location --show-error --silent \
        --retry 3 --retry-delay 2 --connect-timeout 30 \
        --output "$archive" "$url"

    mkdir -p "$extract_dir"
    unzip -q "$archive" -d "$extract_dir"
    printf 'Downloaded and extracted %s.\n' "$name"
}

find_required_file() {
    local root="$1"
    local filename="$2"
    local result

    result="$(find "$root" -type f -name "$filename" -print -quit)"
    [[ -n "$result" ]] || fail "Could not find $filename in the downloaded archive"
    printf '%s' "$result"
}

prepare_repository() {
    if [[ -f "$SCRIPT_DIR/app/requirements.txt" ]]; then
        REPO_DIR="$SCRIPT_DIR"
        return
    fi

    REPO_DIR="${CALORIE_REPO_DIR:-$PWD/calorie-estimator-backend}"
    if [[ -e "$REPO_DIR" ]]; then
        [[ -f "$REPO_DIR/app/requirements.txt" ]] || \
            fail "CALORIE_REPO_DIR exists but is not a calorie-estimator backend checkout: $REPO_DIR"
        return
    fi

    printf 'Cloning backend repository into %s...\n' "$REPO_DIR"
    git clone "$REPO_URL" "$REPO_DIR"
}

install_classifier_models() {
    local archive_dir="$TEMP_DIR/classifier"
    local target_dir="$REPO_DIR/app/models/classifier/v2-seg"
    local model_file
    local labels_file

    model_file="$(find_required_file "$archive_dir" "model_1_vit_segment_aware_v2_seg.pth")"
    labels_file="$(find_required_file "$archive_dir" "labels_v2_seg.txt")"
    mkdir -p "$target_dir"
    cp -f "$model_file" "$target_dir/"
    cp -f "$labels_file" "$target_dir/"
}

install_segmentation_models() {
    local archive_dir="$TEMP_DIR/segmentation"
    local target_dir="$REPO_DIR/app/models/segmentation"
    local checkpoint_file
    local config_file
    local sam2_build_file
    local sam2_source_dir

    checkpoint_file="$(find_required_file "$archive_dir" "sam2_hiera_large.pt")"
    config_file="$(find_required_file "$archive_dir" "sam2_hiera_l.yaml")"
    sam2_build_file="$(find "$archive_dir" -type f -path '*/sam2/build_sam.py' -print -quit)"
    [[ -n "$sam2_build_file" ]] || fail "Could not find the SAM2 Python package in the downloaded archive"
    sam2_source_dir="$(dirname "$sam2_build_file")"

    mkdir -p "$target_dir/checkpoints" "$target_dir/configs/sam2" "$target_dir/sam2"
    cp -f "$checkpoint_file" "$target_dir/checkpoints/"
    cp -f "$config_file" "$target_dir/configs/sam2/"
    cp -a "$sam2_source_dir/." "$target_dir/sam2/"
}

install_thumb_models() {
    local archive_dir="$TEMP_DIR/thumb"
    local target_dir="$REPO_DIR/app/models/thumb"
    local detector_file
    local calibration_file
    local calibration_source_dir

    detector_file="$(find_required_file "$archive_dir" "finger_detector.joblib")"
    calibration_file="$(find "$archive_dir" -type f -path '*/calibration/calibration.py' -print -quit)"
    [[ -n "$calibration_file" ]] || fail "Could not find the calibration Python package in the downloaded archive"
    calibration_source_dir="$(dirname "$calibration_file")"

    mkdir -p "$target_dir/calibration"
    cp -f "$detector_file" "$target_dir/calibration/"
    cp -a "$calibration_source_dir/." "$target_dir/calibration/"
}

validate_installation() {
    local app_dir="$REPO_DIR/app"

    [[ -f "$app_dir/models/classifier/v2-seg/model_1_vit_segment_aware_v2_seg.pth" ]] || fail "Classifier checkpoint is missing"
    [[ -f "$app_dir/models/classifier/v2-seg/labels_v2_seg.txt" ]] || fail "Classifier labels are missing"
    [[ -f "$app_dir/models/segmentation/checkpoints/sam2_hiera_large.pt" ]] || fail "Segmentation checkpoint is missing"
    [[ -f "$app_dir/models/segmentation/configs/sam2/sam2_hiera_l.yaml" ]] || fail "Segmentation config is missing"
    [[ -f "$app_dir/models/segmentation/sam2/build_sam.py" ]] || fail "SAM2 package is missing"
    [[ -f "$app_dir/models/thumb/calibration/finger_detector.joblib" ]] || fail "Thumb detector is missing"
    [[ -f "$app_dir/models/thumb/calibration/calibration.py" ]] || fail "Thumb calibration package is missing"

    printf 'Checking Python imports...\n'
    (
        cd "$REPO_DIR"
        PYTHONPATH="$app_dir" "$REPO_DIR/.venv/bin/python" -c \
            'import app.main; from app.modules.classification_module import FoodClassifier; from app.modules.segmentation_module import SegmentationModule; from app.modules.thumb_module import FingerDetectorAndCalibrator'
    )
}

main() {
    require_command curl
    require_command unzip
    require_command git
    require_command python3

    prepare_repository
    TEMP_DIR="$(mktemp -d)"

    if [[ ! -x "$REPO_DIR/.venv/bin/python" ]]; then
        printf 'Creating virtual environment...\n'
        python3 -m venv "$REPO_DIR/.venv" || \
            fail "Could not create a virtual environment. Install python3-venv and run the script again."
    fi

    printf 'Installing Python requirements...\n'
    "$REPO_DIR/.venv/bin/python" -m pip install --upgrade pip
    "$REPO_DIR/.venv/bin/python" -m pip install -r "$REPO_DIR/app/requirements.txt"

    download_and_extract "classifier" "$CLASSIFIER_URL"
    download_and_extract "segmentation" "$SEGMENTATION_URL"
    download_and_extract "thumb" "$THUMB_URL"

    install_classifier_models
    install_segmentation_models
    install_thumb_models
    validate_installation

    cd "$REPO_DIR"
    printf 'Setup complete. Starting the API at http://localhost:8000\n'
    exec "$REPO_DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
}

main "$@"