param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ollamaParallel = $env:OLLAMA_NUM_PARALLEL
$envFile = Join-Path $Root ".env"
if (Test-Path $envFile) {
    $parallelSetting = Get-Content $envFile |
        Where-Object { $_ -match '^\s*OLLAMA_NUM_PARALLEL\s*=' } |
        Select-Object -Last 1
    if ($parallelSetting) {
        $ollamaParallel = ($parallelSetting -replace '^\s*OLLAMA_NUM_PARALLEL\s*=\s*', '').Trim().Trim('"').Trim("'")
    }
}
if (-not $ollamaParallel) {
    $ollamaParallel = [Environment]::GetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "User")
}
if (-not $ollamaParallel) { $ollamaParallel = "2" }

Set-Location $Root

if (-not (Test-Path $Python)) {
    $Python = "python"
}

# --- Auto-Configure Ollama Environment Variables ---
$flashAttn = [Environment]::GetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "User")
$kvCache = [Environment]::GetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "User")
$currentParallel = [Environment]::GetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "User")

if ($flashAttn -ne "1" -or $kvCache -ne "q8_0" -or $currentParallel -ne $ollamaParallel) {
    Write-Host "Configuring Ollama environment variables (parallel=$ollamaParallel, flash attention, q8 KV cache)..." -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
    [Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
    [Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", $ollamaParallel, "User")
    
    Write-Host "Restarting Ollama background service to apply changes..." -ForegroundColor Yellow
    Stop-Process -Name "ollama app", "ollama" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    
    $ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $ollamaPath) {
        Start-Process $ollamaPath
        Write-Host "Ollama restarted successfully." -ForegroundColor Green
    } else {
        Write-Warning "Could not find Ollama at default path. Please restart Ollama manually."
    }
}
# ---------------------------------------------------

$ownPid = $PID

try {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $ownPid -and
            $_.CommandLine -match "uvicorn" -and
            $_.CommandLine -match "main:app"
        } |
        ForEach-Object {
            Write-Host "Stopping old uvicorn PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}
catch {
    Write-Warning "Could not scan old uvicorn processes: $($_.Exception.Message)"
}

try {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -ne $ownPid } |
        ForEach-Object {
            Write-Host "Stopping process on port $Port PID $_"
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}
catch {
    Write-Warning "Could not scan port ${Port}: $($_.Exception.Message)"
}

Write-Host "Starting server: $Python -m uvicorn main:app --host $HostAddress --port $Port"
& $Python -m uvicorn main:app --host $HostAddress --port $Port
