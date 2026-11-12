Unicode True
!include "MUI2.nsh"
!include "FileFunc.nsh"
Name "Indu AI"
OutFile "..\release\InduAI-0.8.0-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\InduAI"
RequestExecutionLevel user
SetCompressor /SOLID lzma
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Var TestInstall

Function .onInit
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/TEST=" $TestInstall
FunctionEnd

Function .onVerifyInstDir
  ${GetFileName} "$INSTDIR" $0
  StrCmp $0 "InduAI" valid
  Abort "Choose a folder named InduAI."
  valid:
FunctionEnd

Section "Indu AI"
  ${GetFileName} "$INSTDIR" $0
  StrCmp $0 "InduAI" +2
  Abort "Choose a folder named InduAI."
  CreateDirectory "$INSTDIR"
  GetFullPathName $INSTDIR "$INSTDIR"
  IfErrors 0 +2
  Abort "Cannot create the installation directory."
  SetOutPath "$INSTDIR"
  File /r "..\release\InduAI\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  StrCmp $TestInstall "1" install_done
  CreateShortcut "$SMPROGRAMS\Indu AI.lnk" "$INSTDIR\InduAI.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI" "DisplayName" "Indu AI"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI" "DisplayVersion" "0.8.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI" "Publisher" "Akash Bangaru"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  install_done:
SectionEnd

Section "Uninstall"
  GetFullPathName $INSTDIR "$INSTDIR"
  ${GetFileName} "$INSTDIR" $0
  StrCmp $0 "InduAI" +2
  Abort "Invalid installation folder."
  IfFileExists "$INSTDIR\InduAI.exe" +2
  Abort "The application was not found."
  Delete "$INSTDIR\InduAI.exe"
  IfFileExists "$INSTDIR\InduAI.exe" 0 +2
  Abort "Close Indu AI before uninstalling."
  ${GetParameters} $0
  ${GetOptions} $0 "/TEST=" $TestInstall
  StrCmp $TestInstall "1" skip_account_entries
  Delete "$SMPROGRAMS\Indu AI.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\InduAI"
  skip_account_entries:
  ; The absolute installation root was checked above. User data is elsewhere.
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\PRIVACY.md"
  Delete "$INSTDIR\SECURITY.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
