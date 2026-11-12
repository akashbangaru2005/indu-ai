"""Route explicit commands to a fixed set of desktop apps and websites."""

import asyncio
import os
import re
import subprocess
import webbrowser
from pathlib import Path
from uuid import uuid4

from .contacts import ContactStore
from .whatsapp import WhatsAppService
from .reminders import ReminderStore
from .desktop import EXECUTABLES, SETTINGS, launch_registered, open_known_folder
from .live_info import LiveInformation
from ..deployment import is_cloud

URLS = {
    "youtube": "https://www.youtube.com", "instagram": "https://www.instagram.com",
    "snapchat": "https://www.snapchat.com", "snap": "https://www.snapchat.com",
    "whatsapp": "https://web.whatsapp.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "github": "https://github.com",
    "linkedin": "https://www.linkedin.com", "reddit": "https://www.reddit.com",
    "facebook": "https://www.facebook.com",
}

ALIASES = {
    "mail": "gmail", "email": "gmail", "snap": "snapchat",
    "visual studio code": "vscode", "vs code": "vscode", "vscode": "vscode",
    "windows settings": "settings", "file explorer": "explorer", "calculator": "calc",
    "microsoft word": "word", "microsoft excel": "excel", "microsoft powerpoint": "powerpoint",
    "google chrome": "chrome", "wifi settings": "wi-fi settings", "wifi": "wi-fi settings",
    "bluetooth": "bluetooth settings", "downloads folder": "downloads",
}
DESKTOP_APPS = {"explorer": "File Explorer", "calc": "Calculator", "notepad": "Notepad", "chrome": "Google Chrome",
                "word": "Microsoft Word", "excel": "Microsoft Excel", "powerpoint": "Microsoft PowerPoint"}
OPEN_PATTERN = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|go to|goto|navigate to)\s+(.+?)(?:\s+please)?[.!?]*$",
    re.IGNORECASE,
)
MESSAGE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.DOTALL) for pattern in (
        r"(?:please\s+)?send\s+(?:a\s+)?message\s+to\s+(\w+)\s+(.+)",
        r"(?:please\s+)?send\s+(\w+)\s+(?:a\s+)?message\s+(.+)",
        r"(?:please\s+)?message\s+(\w+)\s+(.+)",
        r"(?:please\s+)?whatsapp\s+(\w+)\s+(.+)",
    )
]


class InduCommandRouter:
    def __init__(self, contacts=None, messenger=None):
        self.contacts = contacts or ContactStore()
        self.messenger = messenger or WhatsAppService(self.contacts)
        self.reminders = ReminderStore(self.contacts)
        self.live_information = LiveInformation()

    @staticmethod
    def _result(response: str, success: bool = True):
        return {"type": "browser", "success": success, "response": response}

    def open_url(self, url: str) -> bool:
        if is_cloud():
            return False
        return bool(webbrowser.open(url))

    def open_windows_app(self, app_name: str) -> bool:
        if is_cloud():
            return False
        if app_name in EXECUTABLES:
            return launch_registered(app_name)
        if os.name != "nt" or app_name not in DESKTOP_APPS:
            return False
        try:
            subprocess.Popen([f"{app_name}.exe"], creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except OSError:
            return False

    def open_vscode(self) -> bool:
        if is_cloud():
            return False
        locations = (("LOCALAPPDATA", "Programs/Microsoft VS Code"), ("ProgramFiles", "Microsoft VS Code"))
        for variable, folder in locations:
            base = os.environ.get(variable)
            if not base:
                continue
            executable = Path(base) / folder / "Code.exe"
            if executable.is_file():
                try:
                    subprocess.Popen([str(executable)])
                    return True
                except OSError:
                    continue
        return False

    def open_settings(self, name="settings") -> bool:
        if is_cloud() or os.name != "nt":
            return False
        try:
            os.startfile(SETTINGS[name])
            return True
        except OSError:
            return False

    def parse_whatsapp_message(self, command: str):
        command = command.strip()
        prefix = re.match(r"^(?:please\s+)?(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to|message|whatsapp)\s+(.+)$", command, re.IGNORECASE | re.DOTALL)
        if prefix:
            body = prefix[1].strip()
            names = [name for contact in self.contacts.list() for name in [contact["name"], *contact["aliases"]]]
            # Longest registered name first: 'Deva Kumar' must not resolve to 'Deva'.
            for name in sorted(names, key=len, reverse=True):
                match = re.match(r"^" + re.escape(name) + r"(?=\s|:|,|$)(.*)$", body, re.IGNORECASE | re.DOTALL)
                if match:
                    text = re.sub(r"^\s*(?:on\s+whatsapp\b\s*)?(?:saying\b|that\b|with\s+(?:the\s+)?message\b)?\s*[:,]?\s*", "", match[1], flags=re.IGNORECASE)
                    return name, text
            delimited = re.match(r"^(.+?)(?:\s+on\s+whatsapp)?\s+(?:saying|that)\s+(.+)$", body, re.IGNORECASE | re.DOTALL)
            if delimited:
                return delimited[1], delimited[2]
            number = re.match(r"^(\+?\d{8,15})\s+(.+)$", body, re.DOTALL)
            if number:
                return number[1], re.sub(r"^(?:saying|that)\s+", "", number[2], flags=re.IGNORECASE)
            parts = body.split(maxsplit=1)
            return parts[0], parts[1] if len(parts) == 2 else ""
        match = re.fullmatch(r"(?:please\s+)?send\s+(.+?)\s+(?:a\s+)?(?:whatsapp\s+)?message\s+(.+)", command, re.IGNORECASE | re.DOTALL)
        if match:
            return match[1], re.sub(r"^(?:saying|that)\s+", "", match[2], flags=re.IGNORECASE)
        return None

    async def send_whatsapp_message(self, contact: str, message: str, request_id=None):
        result = await self.messenger.send_text(contact, message, request_id=request_id or uuid4().hex)
        return {"type": "browser", "action": "whatsapp_preview", **result}

    def is_local_command(self, command):
        if self.live_information.recognizes(command):
            return True
        if self.reminders.recognizes(command):
            return True
        if self.parse_whatsapp_message(command):
            return True
        normalized = " ".join(command.lower().strip().split())
        match = OPEN_PATTERN.fullmatch(normalized)
        target = ALIASES.get(match[1] if match else normalized.rstrip(".!?"), match[1] if match else normalized.rstrip(".!?"))
        return target in {*URLS, *DESKTOP_APPS, *SETTINGS, "downloads", "vscode"}

    def _execute_sync(self, command: str):
        command = command.strip()
        normalized = " ".join(command.lower().split())
        match = OPEN_PATTERN.fullmatch(normalized)
        target = match[1] if match else normalized.rstrip(".!?")
        target = ALIASES.get(target, target)
        if is_cloud() and target in {*URLS, *DESKTOP_APPS, *SETTINGS, "downloads", "vscode"}:
            return self._result("Desktop and browser launch commands require Indu running locally on your computer. They are disabled on the cloud server.", False)
        if target in URLS:
            success, name = self.open_url(URLS[target]), target.title()
        elif target == "vscode":
            success, name = self.open_vscode(), "Visual Studio Code"
        elif target in SETTINGS:
            success, name = (self.open_settings() if target == "settings" else self.open_settings(target)), target.title()
        elif target == "downloads":
            success, name = open_known_folder(target), "Downloads"
        elif target in DESKTOP_APPS:
            success, name = self.open_windows_app(target), DESKTOP_APPS[target]
        else:
            return {"type": "chat", "response": None}
        return self._result(f"Opening {name}." if success else f"I could not open {name}.", success)

    async def execute(self, command: str, request_id=None):
        if self.live_information.recognizes(command):
            try:
                return self._result(await self.live_information.execute(command))
            except RuntimeError as failure:
                return self._result(str(failure), False)
        if self.reminders.recognizes(command):
            try:
                return self._result(await asyncio.to_thread(self.reminders.execute, command))
            except ValueError as failure:
                return self._result(str(failure), False)
        whatsapp = self.parse_whatsapp_message(command)
        if whatsapp:
            return await self.send_whatsapp_message(*whatsapp, request_id=request_id)
        # Launchers may block; keep the API event loop responsive.
        return await asyncio.to_thread(self._execute_sync, command)
