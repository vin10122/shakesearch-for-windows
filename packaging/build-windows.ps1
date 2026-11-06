$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $IsWindows -and $env:OS -ne 'Windows_NT') { throw 'Build on Windows x64.' }
python -m venv .venv-build
if ($LASTEXITCODE -ne 0) { throw 'Cannot create build environment' }
$python = Join-Path $PWD '.venv-build\Scripts\python.exe'
& $python -m pip install -r requirements.txt 'pyinstaller==6.16.0' pythonnet
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
$env:QT_QPA_PLATFORM = 'offscreen'
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& $python -m PyInstaller --noconfirm --clean packaging/ShakeSearch.spec
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
if (-not (Test-Path dist/ShakeSearch.exe -PathType Leaf)) { throw 'Single-file EXE not found' }
& ./dist/ShakeSearch.exe --self-test
if ($LASTEXITCODE -ne 0) { throw 'Single-file EXE smoke test failed' }
Get-FileHash dist/ShakeSearch.exe -Algorithm SHA256
