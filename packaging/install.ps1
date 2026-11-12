param([string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'Programs\InduAI'), [switch]$NoShortcuts, [switch]$NoRegistry)
$ErrorActionPreference = 'Stop'
$installTarget = [IO.Path]::GetFullPath($InstallDirectory).TrimEnd('\')
if ([IO.Path]::GetFileName($installTarget) -ne 'InduAI') { throw 'Installation directory must be named InduAI.' }
$payload = Join-Path $PSScriptRoot 'InduAI-0.8.0-windows.zip'
if (!(Test-Path -LiteralPath $payload)) { throw 'Place the Windows zip beside this installer.' }
New-Item -ItemType Directory -Path $installTarget -Force | Out-Null
Expand-Archive -LiteralPath $payload -DestinationPath ([IO.Path]::GetDirectoryName($installTarget)) -Force
$application = Join-Path $installTarget 'InduAI.exe'
if (!(Test-Path -LiteralPath $application)) { throw 'Installer payload is incomplete.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall.ps1') -Destination $installTarget
if (!$NoShortcuts) {
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Programs')) 'Indu AI.lnk'))
    $shortcut.TargetPath = $application
    $shortcut.WorkingDirectory = $installTarget
    $shortcut.Save()
}
if (!$NoRegistry) {
    $entry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI'
    New-Item -Path $entry -Force | Out-Null
    Set-ItemProperty -Path $entry -Name DisplayName -Value 'Indu AI'
    Set-ItemProperty -Path $entry -Name DisplayVersion -Value '0.8.0'
    Set-ItemProperty -Path $entry -Name Publisher -Value 'Akash Bangaru'
    Set-ItemProperty -Path $entry -Name InstallLocation -Value $installTarget
    Set-ItemProperty -Path $entry -Name UninstallString -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $installTarget 'uninstall.ps1') + '"')
}
Write-Output "Installed Indu AI to $installTarget. Run InduAI.exe to begin."
