"""Only fixed executable names and known Windows settings URIs may launch."""
import os
import subprocess
from pathlib import Path
from ..deployment import is_cloud

EXECUTABLES = {"word": "WINWORD.EXE", "excel": "EXCEL.EXE", "powerpoint": "POWERPNT.EXE", "chrome": "chrome.exe"}
SETTINGS = {"settings": "ms-settings:", "bluetooth settings": "ms-settings:bluetooth", "wi-fi settings": "ms-settings:network-wifi"}


def launch_registered(name):
    if is_cloud() or os.name != "nt" or name not in EXECUTABLES:
        return False
    import winreg
    filename = EXECUTABLES[name]
    candidates = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{filename}", 0, winreg.KEY_READ | view) as key:
                    candidates.append(Path(winreg.QueryValueEx(key, "")[0].strip('"')))
            except OSError:
                pass
    if name == "chrome":
        for variable in ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / "Google/Chrome/Application/chrome.exe")
    else:
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            if os.environ.get(variable):
                candidates.append(Path(os.environ[variable]) / "Microsoft Office/root/Office16" / filename)
    for candidate in candidates:
        if candidate.name.casefold() == filename.casefold() and candidate.is_file():
            try:
                subprocess.Popen([str(candidate)], creationflags=subprocess.CREATE_NO_WINDOW)
                return True
            except OSError:
                continue
    return False


def open_known_folder(name):
    if is_cloud() or os.name != "nt" or name != "downloads":
        return False
    import winreg
    folder = Path.home() / "Downloads"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
            folder = Path(os.path.expandvars(winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0]))
        if folder.is_dir():
            os.startfile(str(folder))
            return True
    except OSError:
        pass
    return False
