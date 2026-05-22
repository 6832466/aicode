$ErrorActionPreference = "Stop"

$pythonExe = $null
$pythonArgs = @()

$candidates = @(
    "E:\AiCode\eaglepy310\python.exe",
    "C:\Program Files\NVIDIA Corporation\Nsight Systems 2025.6.3\host-windows-x64\python\bin\python.exe",
    "C:\Program Files\NVIDIA Corporation\Nsight Compute 2026.1.0\host\target-windows-x64\python\bin\python.exe"
)
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $pythonExe = $python.Source
    } else {
        $py = Get-Command py -ErrorAction SilentlyContinue
        if ($py) {
            $pythonExe = $py.Source
            $pythonArgs = @("-3")
        }
    }
}

if (-not $pythonExe) {
    throw "Python was not found. Install Python 3.10+ first, then rerun this script."
}

$vendor = Join-Path $PSScriptRoot ".vendor"
$missing = & $pythonExe @pythonArgs -c "import importlib.util; missing=[m for m in ('PySide6','requests','PyInstaller') if importlib.util.find_spec(m) is None]; print(','.join(missing))"
if ($missing) {
    & $pythonExe @pythonArgs -m pip install --upgrade --target $vendor -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
    $env:PYTHONPATH = $vendor
}
& $pythonExe @pythonArgs .\generate_icon.py
if ($LASTEXITCODE -ne 0) {
    throw "Icon generation failed."
}
& $pythonExe @pythonArgs -m PyInstaller `
    --clean `
    --noconsole `
    --onefile `
    --name GoldMonitor `
    --icon .\gold_monitor.ico `
    --paths $vendor `
    --exclude-module qfluentwidgets `
    --exclude-module numpy `
    --exclude-module scipy `
    --exclude-module pandas `
    --exclude-module torch `
    --exclude-module torchvision `
    --exclude-module torchaudio `
    --exclude-module transformers `
    --exclude-module cv2 `
    --exclude-module matplotlib `
    --exclude-module PIL `
    --exclude-module onnxruntime `
    gold_monitor.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$desktop = [Environment]::GetFolderPath("Desktop")
Copy-Item -LiteralPath ".\dist\GoldMonitor.exe" -Destination (Join-Path $desktop "GoldMonitor.exe") -Force
Write-Host "Built and copied to: $(Join-Path $desktop 'GoldMonitor.exe')"
