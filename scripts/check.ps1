# Everything that must pass before a commit. Never touches AutoCAD.
#   powershell -File scripts\check.ps1   (or run the five commands below by hand)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
Push-Location $root
try {
    Write-Host '== ruff'; & $python -m ruff check .; if ($LASTEXITCODE) { throw 'ruff failed' }
    Write-Host '== pytest (offline)'; & $python -m pytest -q; if ($LASTEXITCODE) { throw 'tests failed' }
    Write-Host '== tool reference'; & $python scripts\gen_tool_docs.py --check; if ($LASTEXITCODE) { throw 'tool reference out of date' }
    Write-Host '== vault links'; & $python scripts\check_links.py; if ($LASTEXITCODE) { throw 'broken vault links' }
    Write-Host '== stdio handshake'; & $python scripts\stdio_smoke.py; if ($LASTEXITCODE) { throw 'stdio smoke failed' }
    Write-Host 'All checks passed.' -ForegroundColor Green
} finally {
    Pop-Location
}
