# Run the backend test suite with the project venv and enforce tool-layer coverage.
# Usage (from repo root):  powershell -ExecutionPolicy Bypass -File scripts\test.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Venv not found at $python. Create it and run: pip install -r backend\requirements.txt pytest-cov==4.1.0"
}

Push-Location (Join-Path $root "backend")
try {
    & $python -m pytest -q --cov=tools --cov-report=term-missing --cov-fail-under=90
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
