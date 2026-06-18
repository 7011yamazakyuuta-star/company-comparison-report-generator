$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python310 = "C:\Users\7011y\AppData\Local\Programs\Python\Python310\python.exe"
if (-not (Test-Path $python310)) {
    $python310 = "py"
    $argsPrefix = @("-3.10")
} else {
    $argsPrefix = @()
}

$port = if ($env:STREAMLIT_PORT) { $env:STREAMLIT_PORT } else { "8501" }

Write-Host "Starting Streamlit with Python 3.10 on http://localhost:$port"
& $python310 @argsPrefix -m streamlit run app.py --server.port $port --server.headless true
