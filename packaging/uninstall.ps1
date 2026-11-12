param([switch]$NoRegistry, [switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
$installTarget = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
if ([IO.Path]::GetFileName($installTarget) -ne 'InduAI' -or !(Test-Path -LiteralPath (Join-Path $installTarget 'InduAI.exe'))) { throw 'This is not a valid Indu AI installation.' }
if (Get-Process -Name InduAI -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq (Join-Path $installTarget 'InduAI.exe') }) { throw 'Close Indu AI before uninstalling.' }
if (!$NoShortcuts) {
    $shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Indu AI.lnk'
    if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut }
}
if (!$NoRegistry -and (Test-Path -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI')) { Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI' }
# The absolute target was validated above. Personal data and credentials are retained.
Remove-Item -LiteralPath $installTarget -Recurse -Force
Write-Output 'Indu AI was uninstalled. Local contacts, reminders and OS credentials were retained.'
