"""Verify the frozen app and same-origin UI without using saved credentials."""
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix="indu-package-test-") as folder:
        folder = Path(folder)
        environment = dict(os.environ)
        environment.pop("GEMINI_API_KEY", None)
        environment["INDU_DISABLE_CREDENTIAL_STORE"] = "1"
        environment["INDU_DATA_DIR"] = str(folder / "data")
        ready = folder / "ready.json"
        with (folder / "server.log").open("w") as logs:
            process = subprocess.Popen([str(ROOT / "release/InduAI/InduAI.exe"), "--no-browser", "--ready-file", str(ready)],
                                       env=environment, stdout=logs, stderr=logs, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for _ in range(200):
                    if ready.exists() or process.poll() is not None:
                        break
                    time.sleep(.1)
                assert ready.exists(), "Frozen app did not start"
                url = json.loads(ready.read_text())["url"]
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(channel="msedge", headless=True)
                    context = browser.new_context()
                    context.add_init_script("window.SpeechRecognition = window.webkitSpeechRecognition = undefined")
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url)
                    page.get_by_role("heading", name="Welcome to Indu.").wait_for()
                    page.get_by_role("button", name="Continue without Gemini").click()
                    page.locator('.assistant-scene[data-renderer="webgl"]').wait_for()
                    page.get_by_text("System online", exact=True).wait_for()
                    assert page.request.get(url + "/mic-processor.js").status == 200
                    for message, expected in [("Secret 2005 I love you", "Akash, I love you too."), ("I love you", "No, I have a boyfriend, my creator.")]:
                        response = page.request.post(url + "/api/chat", data={"message":message})
                        assert response.ok and response.json().get("response") == expected, {"status":response.status, "data":response.json()}
                    page.get_by_role("button", name="Close Indu app", exact=True).click()
                    assert process.wait(timeout=15) == 0
                    assert not errors, errors
                    browser.close()
                report = {"status":"passed", "checks":["Frozen backend starts with temporary per-user data", "Bundled React UI and 3D WebGL load on the same origin", "First-launch setup and microphone worklet assets resolve", "Creator and guest affection replies work locally with no API key", "Close Indu app cleanly stops the frozen process"], "scope":"Installed Edge and frozen Windows bundle, no saved key or real microphone recording."}
                (ROOT / "reports/packaged-browser-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report))
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=5)


if __name__ == "__main__":
    main()
