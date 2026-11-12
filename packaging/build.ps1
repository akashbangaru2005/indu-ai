param([string]$Python = "$PSScriptRoot\..\backend\venv\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
function Invoke-Native([string]$Executable, [string[]]$Parameters) {
    $savedPreference = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; & $Executable @Parameters; $result = $LASTEXITCODE }
    finally { $ErrorActionPreference = $savedPreference }
    if ($result) { throw "Build command failed with exit code $result" }
}
Push-Location $projectRoot
try {
    Push-Location frontend
    try { Invoke-Native 'node' @('node_modules/vite/bin/vite.js','build','--configLoader','native') }
    finally { Pop-Location }
    $frontendData = (Join-Path $projectRoot 'frontend/dist') + ':frontend/dist'
    Invoke-Native $Python @('-m','PyInstaller','--noconfirm','--clean','--onedir','--name','InduAI','--distpath','release','--workpath','build/desktop','--specpath','build','--add-data',$frontendData,'--hidden-import','keyring.backends.Windows','--collect-data','tzdata','--exclude-module','faster_whisper','--exclude-module','sounddevice','--exclude-module','pygame','--exclude-module','av','--exclude-module','numpy','--exclude-module','torch','--exclude-module','scipy','--exclude-module','playwright','desktop_launcher.py')
    Copy-Item -LiteralPath README.md,PRIVACY.md,SECURITY.md -Destination release/InduAI
    Invoke-Native $Python @('packaging/package.py')
    Copy-Item -LiteralPath packaging/install.ps1,packaging/uninstall.ps1 -Destination release
    & (Join-Path $PSScriptRoot 'create-installer.ps1') -Python $Python
    Write-Output 'Bundle and installer script are in release/. Run install.ps1 beside the zip.'
}
finally { Pop-Location }
