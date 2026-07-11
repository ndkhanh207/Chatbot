param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
    $Python = "python"
}

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
