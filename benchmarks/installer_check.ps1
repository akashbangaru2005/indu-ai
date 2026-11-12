$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$installTarget = [IO.Path]::GetFullPath((Join-Path $projectRoot 'reports/installer-test/InduAI'))
if (!$installTarget.StartsWith((Join-Path $projectRoot 'reports/installer-test/'), [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($installTarget) -ne 'InduAI') { throw 'Invalid isolated installer-test path.' }
$installer = Join-Path $projectRoot 'release/InduAI-0.8.0-Setup.exe'
$installation = Start-Process -FilePath $installer -ArgumentList @('/S','/TEST=1',('/D=' + $installTarget)) -WindowStyle Hidden -PassThru
$installation.WaitForExit()
if ($installation.ExitCode -ne 0 -or !(Test-Path -LiteralPath (Join-Path $installTarget 'InduAI.exe'))) { throw "Installation check failed with exit $($installation.ExitCode) at $installTarget." }
$env:INDU_DATA_DIR = Join-Path $projectRoot 'reports/installer-test/data'
$env:INDU_DISABLE_CREDENTIAL_STORE = '1'
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
& (Join-Path $installTarget 'InduAI.exe') --smoke-test
if ($LASTEXITCODE) { throw 'Installed executable failed its startup check.' }
$uninstaller = Join-Path $installTarget 'Uninstall.exe'
# The full absolute installation target was checked against the dedicated test root.
$uninstallation = Start-Process -FilePath $uninstaller -ArgumentList @('/S','/TEST=1',('_?=' + $installTarget)) -WindowStyle Hidden -PassThru
$uninstallation.WaitForExit()
if ($uninstallation.ExitCode -ne 0 -or (Test-Path -LiteralPath (Join-Path $installTarget 'InduAI.exe'))) { throw 'Uninstall check failed.' }
$report = @{status='passed'; install=$true; installed_app_startup=$true; uninstall=$true; user_data_retained=(Test-Path -LiteralPath $env:INDU_DATA_DIR); scope='Dedicated workspace directory; account registry and Start menu changes skipped. No real Gemini key used.'}
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'reports/installer-check.json') -Encoding UTF8
Write-Output ($report | ConvertTo-Json -Compress)
