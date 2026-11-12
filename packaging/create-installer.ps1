param([string]$Python = "$PSScriptRoot\..\backend\venv\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
& $Python (Join-Path $PSScriptRoot 'bootstrap_nsis.py')
if ($LASTEXITCODE) { throw 'NSIS compiler preparation failed.' }
& (Join-Path $projectRoot 'build/tools/nsis-3.13/makensis.exe') '/V2' (Join-Path $PSScriptRoot 'installer.nsi')
if ($LASTEXITCODE) { throw 'Windows installer compilation failed.' }
Write-Output 'Windows installer created.'
