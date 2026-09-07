$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Сначала выполните setup.ps1 с Python 3.12 или новее.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Сначала выполните npm run build в папке frontend.' }
Write-Host 'KANZLER Business Platform: http://127.0.0.1:8000'
& $taskPython -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
