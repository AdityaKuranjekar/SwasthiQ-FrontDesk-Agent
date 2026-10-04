$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $root "venv\Scripts\python.exe"

# 1. Idempotent check
$portInUse = $false
try {
    $conn = [System.Net.Sockets.TcpClient]::new("127.0.0.1", 8000)
    $conn.Close()
    $portInUse = $true
} catch {
}

if ($portInUse) {
    Write-Error "Port 8000 is already in use. Please stop the existing server."
    exit 1
}

# 2. Start server
Write-Host "Starting server..."
$process = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" -WorkingDirectory $backend -PassThru -NoNewWindow
$procId = $process.Id

try {
    # 3. Wait for healthz
    Write-Host "Waiting for /healthz..."
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -Method Get -ErrorAction Stop
            if ($resp.status -eq "ok") {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    
    if (-not $ready) {
        Write-Error "Server did not become healthy within 20 seconds."
        exit 1
    }
    Write-Host "Server is healthy."

    # 4. Send cv_0001 and cv_0011
    $cv0001 = Get-Content (Join-Path $root "conversations\cv_0001.json") -Raw | ConvertFrom-Json
    $cv0011 = Get-Content (Join-Path $root "conversations\cv_0011.json") -Raw | ConvertFrom-Json

    $body0001 = @{
        conversation_id = $cv0001.id
        today = $cv0001.today
        turns = $cv0001.turns
    } | ConvertTo-Json
    
    $body0011 = @{
        conversation_id = $cv0011.id
        today = $cv0011.today
        turns = $cv0011.turns
    } | ConvertTo-Json

    Write-Host "Testing cv_0001..."
    $res0001 = Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/run" -Method Post -Body $body0001 -ContentType "application/json"
    Write-Host "cv_0001 terminal_state: $($res0001.terminal_state), escalation_reason: $($res0001.escalation_reason)"

    Write-Host "Testing cv_0011..."
    $res0011 = Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/run" -Method Post -Body $body0011 -ContentType "application/json"
    Write-Host "cv_0011 terminal_state: $($res0011.terminal_state), escalation_reason: $($res0011.escalation_reason)"

    if ($res0011.terminal_state -ne "escalated" -or $res0011.escalation_reason -ne "clinical_urgent") {
        Write-Error "cv_0011 did not escalate correctly! state: $($res0011.terminal_state) reason: $($res0011.escalation_reason)"
        exit 1
    }
    
    foreach ($call in $res0011.tool_calls) {
        if ($call.name -eq "book_appointment") {
            Write-Error "cv_0011 made a booking during a clinical emergency!"
            exit 1
        }
    }
    Write-Host "cv_0011 constraints passed."

    # 5. Run runner.py --repeat 3
    Write-Host "Running runner.py --repeat 3..."
    Push-Location $root
    try {
        $runnerOut = & $python runner.py --repeat 3 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Error "runner.py failed."
            exit $LASTEXITCODE
        }
        
        # Print last 3 lines
        $runnerOut | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
    } finally {
        Pop-Location
    }
    
} finally {
    Write-Host "Stopping server (PID: $procId)..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}
