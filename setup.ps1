param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Укажите Python 3.12+: .\setup.ps1 -Python C:\путь\python.exe' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать виртуальное окружение.' }
}
& '.venv\Scripts\python.exe' -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости Python.' }
Push-Location -LiteralPath frontend
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости frontend.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать frontend.' }
} finally { Pop-Location }
Write-Host 'Установка завершена. Запуск: .\start.ps1'
