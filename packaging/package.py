"""Create an explicit, secret-free release payload using shared-read file handles."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
folder = root / "release/InduAI"
with zipfile.ZipFile(root / "release/InduAI-0.8.0-windows.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            archive.write(path, path.relative_to(folder.parent))
print("Windows release zip created")
