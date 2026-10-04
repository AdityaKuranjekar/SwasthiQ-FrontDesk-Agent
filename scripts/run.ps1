# Start the backend API locally with the project venv.
# Usage (from repo root):  powershell -ExecutionPolicy Bypass -File scripts\run.ps1
# Optional: $env:PORT = "8000" (default 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Venv not found at $python. Create it and run: pip install -r backend\requirements.txt"
}

$port = if ($env:PORT) { $env:PORT } else { "8000" }
Push-Location (Join-Path $root "backend")
try {
    & $python -m uvicorn app.main:app --port $port
} finally {
    Pop-Location
}
