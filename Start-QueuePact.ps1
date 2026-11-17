param([int]$Port = 8080, [string]$Database = '')
$ErrorActionPreference = 'Stop'
$queuePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $queuePython)) { throw 'Virtual environment missing. Follow the README installation commands first.' }
if ($Database) {
    if (-not [System.IO.Path]::IsPathRooted($Database)) { throw 'Database must be an absolute path.' }
    $env:QUEUEPACT_DB = $Database
}
Push-Location $PSScriptRoot
try {
    & $queuePython -c 'import nicegui, simpy, plotly, queuepact'
    if ($LASTEXITCODE -ne 0) { throw 'Dependencies missing. Install requirements-tested.txt and the editable project first.' }
    Write-Host "QueuePact: http://127.0.0.1:$Port — Ctrl+C to stop. No packages are installed by this launcher."
    & $queuePython -m queuepact ui --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'QueuePact could not start. Check the error above; try another -Port if occupied.' }
} finally { Pop-Location }
