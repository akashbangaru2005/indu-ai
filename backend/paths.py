"""Writable per-user data, separate from installed application files."""
import os
from pathlib import Path


def data_directory():
    override = os.environ.get("INDU_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "InduAI"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "indu-ai"
