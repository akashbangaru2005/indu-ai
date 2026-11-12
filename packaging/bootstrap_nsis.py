"""Download the portable official NSIS release into ignored build tools."""
from pathlib import Path
import io
import zipfile
import requests

root = Path(__file__).resolve().parents[1]
tools = root / "build/tools"
target = tools / "nsis-3.13/makensis.exe"
if not target.exists():
    for host in ("master.dl.sourceforge.net", "netix.dl.sourceforge.net"):
        try:
            response = requests.get(f"https://{host}/project/nsis/NSIS%203/3.13/nsis-3.13.zip?viasf=1", timeout=30)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for info in archive.infolist():
                    destination = (tools / info.filename).resolve()
                    if not destination.is_relative_to(tools.resolve()):
                        raise ValueError("Invalid compiler archive path")
                archive.extractall(tools)
            break
        except (requests.RequestException, zipfile.BadZipFile):
            continue
    if not target.exists():
        raise RuntimeError("Download the portable NSIS 3.13 zip from the official NSIS project and extract it under build/tools.")
print("Portable NSIS compiler ready")
