# Gera o programa para Windows (pasta dist\GNRE.Flow) e, se o Inno Setup estiver
# instalado, o instalador installer\Output\GNRE.Flow-Setup.exe.
#   Uso:  powershell -ExecutionPolicy Bypass -File build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install -r requirements.txt -r requirements-desktop.txt --quiet

python -m PyInstaller --noconfirm --clean --windowed `
  --name GNRE.Flow --icon installer\gnreflow.ico `
  --add-data "app\templates;app\templates" `
  --add-data "app\schemas;app\schemas" `
  --add-data "app\data\aliquotas_internas.json;app\data" `
  --collect-all zeep `
  --collect-all reportlab `
  --collect-submodules uvicorn `
  --hidden-import multipart --hidden-import python_multipart `
  --exclude-module psycopg2 --exclude-module pytest `
  launcher.py

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
  $cand = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ }
  if ($cand) { $iscc = $cand[0] }
}
if ($iscc) { & $iscc "installer\GNRE.Flow.iss" } else { Write-Host "Inno Setup nao encontrado: instalador nao gerado (pasta dist\GNRE.Flow esta pronta)." }
