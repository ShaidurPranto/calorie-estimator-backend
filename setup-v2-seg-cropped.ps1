$ErrorActionPreference = "Stop"

$REPO_URL = "https://github.com/ShaidurPranto/calorie-estimator-backend.git"
$CLASSIFIER_URL = "https://www.kaggle.com/api/v1/datasets/download/ifty3110/food-classifier-models-v2-seg-cropped"
$SEGMENTATION_URL = "https://www.kaggle.com/api/v1/datasets/download/ifty3110/segmentation-module-checkpoints-config"
$THUMB_URL = "https://www.kaggle.com/api/v1/datasets/download/intesartahmidalam/finger-detector-and-calibration-files"
$VENV_NAME = "calorie-estimator-venv"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_DIR = ""
$VENV_DIR = ""
$TEMP_DIR = ""

function Fail([string]$Message) {
    Write-Error "Setup failed: $Message"
    exit 1
}

function Require-Command([string]$Command) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        Fail "Required command not found: $Command"
    }
}

function Download-And-Extract([string]$Name, [string]$Url) {
    $Archive = Join-Path $TEMP_DIR "$Name.zip"
    $ExtractDir = Join-Path $TEMP_DIR $Name

    Write-Host "Downloading $Name model archive..."

    try {
        Invoke-WebRequest `
            -Uri $Url `
            -OutFile $Archive `
            -UseBasicParsing
    }
    catch {
        Fail "Could not download $Name model archive: $($_.Exception.Message)"
    }

    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

    Require-Command "tar"
    try {
        tar -xf $Archive -C $ExtractDir
    }
    catch {
        Fail "Could not extract $Name model archive: $($_.Exception.Message)"
    }

    Write-Host "Downloaded and extracted $Name."
}

function Find-Required-File([string]$Root, [string]$FileName) {
    $Result = Get-ChildItem -Path $Root -Recurse -File -Filter $FileName |
        Select-Object -First 1

    if ($null -eq $Result) {
        Fail "Could not find $FileName in the downloaded archive"
    }

    return $Result.FullName
}

function Prepare-Repository {
    $RequirementsInScriptDir = Join-Path $SCRIPT_DIR "app\requirements.txt"

    if (Test-Path -LiteralPath $RequirementsInScriptDir -PathType Leaf) {
        $script:REPO_DIR = $SCRIPT_DIR
        return
    }

    if ($env:CALORIE_REPO_DIR) {
        $script:REPO_DIR = $env:CALORIE_REPO_DIR
    }
    else {
        $script:REPO_DIR = Join-Path (Get-Location) "calorie-estimator-backend"
    }

    if (Test-Path -LiteralPath $REPO_DIR) {
        $RequirementsFile = Join-Path $REPO_DIR "app\requirements.txt"

        if (-not (Test-Path -LiteralPath $RequirementsFile -PathType Leaf)) {
            Fail "CALORIE_REPO_DIR exists but is not a calorie-estimator backend checkout: $REPO_DIR"
        }

        return
    }

    Write-Host "Cloning backend repository into $REPO_DIR..."
    git clone $REPO_URL $REPO_DIR

    if ($LASTEXITCODE -ne 0) {
        Fail "Could not clone the backend repository"
    }
}

function Install-Classifier-Models {
    $ArchiveDir = Join-Path $TEMP_DIR "classifier"
    $TargetDir = Join-Path $REPO_DIR "app\models\classifier\v2-seg-cropped"

    $ModelFile = Find-Required-File $ArchiveDir "model_1_vit_segment_aware_v2_seg_cropped.pth"
    $LabelsFile = Find-Required-File $ArchiveDir "labels_v2_seg_cropped.txt"

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

    Copy-Item -Force $ModelFile $TargetDir
    Copy-Item -Force $LabelsFile $TargetDir
}

function Install-Segmentation-Models {
    $ArchiveDir = Join-Path $TEMP_DIR "segmentation"
    $TargetDir = Join-Path $REPO_DIR "app\models\segmentation"

    $CheckpointFile = Find-Required-File $ArchiveDir "sam2_hiera_large.pt"
    $ConfigFile = Find-Required-File $ArchiveDir "sam2_hiera_l.yaml"

    $Sam2BuildFile = Get-ChildItem -Path $ArchiveDir -Recurse -File -Filter "build_sam.py" |
        Where-Object { $_.FullName -match '[\\/]sam2[\\/]build_sam\.py$' } |
        Select-Object -First 1

    if ($null -eq $Sam2BuildFile) {
        Fail "Could not find the SAM2 Python package in the downloaded archive"
    }

    $Sam2SourceDir = $Sam2BuildFile.Directory.FullName

    New-Item -ItemType Directory -Force -Path `
        (Join-Path $TargetDir "checkpoints"), `
        (Join-Path $TargetDir "configs\sam2"), `
        (Join-Path $TargetDir "sam2") | Out-Null

    Copy-Item -Force $CheckpointFile (Join-Path $TargetDir "checkpoints")
    Copy-Item -Force $ConfigFile (Join-Path $TargetDir "configs\sam2")

    # Equivalent to: cp -a "$sam2_source_dir/." "$target_dir/sam2/"
    Copy-Item -Path (Join-Path $Sam2SourceDir "*") `
        -Destination (Join-Path $TargetDir "sam2") `
        -Recurse -Force
}

function Install-Thumb-Models {
    $ArchiveDir = Join-Path $TEMP_DIR "thumb"
    $TargetDir = Join-Path $REPO_DIR "app\models\thumb"

    $DetectorFile = Find-Required-File $ArchiveDir "finger_detector.joblib"

    $CalibrationFile = Get-ChildItem -Path $ArchiveDir -Recurse -File -Filter "calibration.py" |
        Where-Object { $_.FullName -match '[\\/]calibration[\\/]calibration\.py$' } |
        Select-Object -First 1

    if ($null -eq $CalibrationFile) {
        Fail "Could not find the calibration Python package in the downloaded archive"
    }

    $CalibrationSourceDir = $CalibrationFile.Directory.FullName

    New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "calibration") | Out-Null

    Copy-Item -Force $DetectorFile (Join-Path $TargetDir "calibration")

    # Equivalent to: cp -a "$calibration_source_dir/." "$target_dir/calibration/"
    Copy-Item -Path (Join-Path $CalibrationSourceDir "*") `
        -Destination (Join-Path $TargetDir "calibration") `
        -Recurse -Force
}

function Classifier-Models-Ready {
    $TargetDir = Join-Path $REPO_DIR "app\models\classifier\v2-seg-cropped"

    return (
        (Test-Path (Join-Path $TargetDir "model_1_vit_segment_aware_v2_seg_cropped.pth") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "labels_v2_seg_cropped.txt") -PathType Leaf)
    )
}

function Segmentation-Models-Ready {
    $TargetDir = Join-Path $REPO_DIR "app\models\segmentation"

    return (
        (Test-Path (Join-Path $TargetDir "checkpoints\sam2_hiera_large.pt") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "configs\sam2\sam2_hiera_l.yaml") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "sam2\build_sam.py") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "sam2\automatic_mask_generator.py") -PathType Leaf)
    )
}

function Thumb-Models-Ready {
    $TargetDir = Join-Path $REPO_DIR "app\models\thumb"

    return (
        (Test-Path (Join-Path $TargetDir "calibration\finger_detector.joblib") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "calibration\calibration.py") -PathType Leaf) -and
        (Test-Path (Join-Path $TargetDir "calibration\modeling.py") -PathType Leaf)
    )
}

function Validate-Installation {
    $AppDir = Join-Path $REPO_DIR "app"

    if (-not (Test-Path (Join-Path $AppDir "models\classifier\v2-seg-cropped\model_1_vit_segment_aware_v2_seg_cropped.pth") -PathType Leaf)) {
        Fail "Classifier checkpoint is missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\classifier\v2-seg-cropped\labels_v2_seg_cropped.txt") -PathType Leaf)) {
        Fail "Classifier labels are missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\segmentation\checkpoints\sam2_hiera_large.pt") -PathType Leaf)) {
        Fail "Segmentation checkpoint is missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\segmentation\configs\sam2\sam2_hiera_l.yaml") -PathType Leaf)) {
        Fail "Segmentation config is missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\segmentation\sam2\build_sam.py") -PathType Leaf)) {
        Fail "SAM2 package is missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\thumb\calibration\finger_detector.joblib") -PathType Leaf)) {
        Fail "Thumb detector is missing"
    }

    if (-not (Test-Path (Join-Path $AppDir "models\thumb\calibration\calibration.py") -PathType Leaf)) {
        Fail "Thumb calibration package is missing"
    }

    Write-Host "Checking Python imports..."

    Push-Location $REPO_DIR
    try {
        $env:PYTHONPATH = $AppDir

        & (Join-Path $VENV_DIR "Scripts\python.exe") -c `
            "import app.main; from app.modules.classification_module import FoodClassifier; from app.modules.segmentation_module import SegmentationModule; from app.modules.thumb_module import FingerDetectorAndCalibrator"

        if ($LASTEXITCODE -ne 0) {
            Fail "Python import validation failed"
        }
    }
    finally {
        Pop-Location
    }
}

function Main {
    Require-Command "git"
    Require-Command "python"

    Prepare-Repository

    $script:VENV_DIR = Join-Path $REPO_DIR $VENV_NAME
    $script:TEMP_DIR = Join-Path ([System.IO.Path]::GetTempPath()) ("calorie-estimator-" + [Guid]::NewGuid().ToString())

    New-Item -ItemType Directory -Force -Path $TEMP_DIR | Out-Null

    try {
        $VenvPython = Join-Path $VENV_DIR "Scripts\python.exe"

        if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
            Write-Host "Creating virtual environment: $VENV_NAME"

            & python -m venv $VENV_DIR

            if ($LASTEXITCODE -ne 0) {
                Fail "Could not create a virtual environment. Make sure Python is installed correctly and run the script again."
            }
        }

        Write-Host "Installing Python requirements..."

        & $VenvPython -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) {
            Fail "Could not upgrade pip"
        }

        & $VenvPython -m pip install -r (Join-Path $REPO_DIR "app\requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            Fail "Could not install Python requirements"
        }

        if (Classifier-Models-Ready) {
            Write-Host "Classifier model is already installed; skipping download."
        }
        else {
            Download-And-Extract "classifier" $CLASSIFIER_URL
            Install-Classifier-Models
        }

        if (Segmentation-Models-Ready) {
            Write-Host "Segmentation model is already installed; skipping download."
        }
        else {
            Download-And-Extract "segmentation" $SEGMENTATION_URL
            Install-Segmentation-Models
        }

        if (Thumb-Models-Ready) {
            Write-Host "Thumb detection model is already installed; skipping download."
        }
        else {
            Download-And-Extract "thumb" $THUMB_URL
            Install-Thumb-Models
        }

        Validate-Installation

        Push-Location $REPO_DIR
        try {
            Write-Host "Setup complete. Starting the API at http://localhost:8000"

            & $VenvPython -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
        }
        finally {
            Pop-Location
        }
    }
    finally {
        if ($TEMP_DIR -and (Test-Path -LiteralPath $TEMP_DIR)) {
            Remove-Item -LiteralPath $TEMP_DIR -Recurse -Force
        }
    }
}

Main
