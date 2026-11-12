"""Headless browser smoke checks using the installed Edge browser and fake audio."""

import json
import array
import math
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=.25):
                return
        except OSError:
            time.sleep(.1)
    raise RuntimeError(f"Server did not start: {url}")


def main():
    backend_port, frontend_port = port(), port()
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    backend_url = f"http://127.0.0.1:{backend_port}"
    environment = dict(os.environ)
    environment.pop("GEMINI_API_KEY", None)
    environment["INDU_DISABLE_CREDENTIAL_STORE"] = "1"
    environment["INDU_ALLOWED_ORIGINS"] = frontend_url
    environment["VITE_API_URL"] = backend_url
    temporary = TemporaryDirectory(prefix="indu-browser-test-")
    environment["INDU_DATABASE"] = str(Path(temporary.name) / "test.db")
    processes = []
    checks = []
    logs = open(ROOT / "reports/browser-smoke-server.log", "w", encoding="utf-8")
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        processes.append(subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=ROOT, env=environment, stdout=logs, stderr=logs, creationflags=flags))
        processes.append(subprocess.Popen(
            [shutil.which("node"), "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
            cwd=ROOT / "frontend", env=environment, stdout=logs, stderr=logs, creationflags=flags))
        wait_http(backend_url)
        wait_http(frontend_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True, args=[
                "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            ])
            context = browser.new_context(permissions=["microphone"], viewport={"width":1440,"height":1000})
            # Disable cloud wake recognition and observe synthetic microphone tracks.
            context.add_init_script("""
                window.testStreams = [];
                window.testPendingMicrophones = 0;
                window.testContexts = [];
                window.testVoiceSockets = [];
                window.testMicFrames = 0;
                window.testSourceStarts = 0;
                window.testSourceEnds = 0;
                window.testSourceStops = 0;
                window.testActiveSources = new Set();
                window.testWakeListeners = new Set();
                class FakeRecognition {
                  start() { window.testWakeListeners.add(this); this.onstart?.(); }
                  abort() { window.testWakeListeners.delete(this); this.onend?.(); }
                }
                window.SpeechRecognition = window.webkitSpeechRecognition = FakeRecognition;
                const originalMic = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia = async (...args) => {
                  window.testPendingMicrophones++;
                  try {
                    const stream = await originalMic(...args);
                    window.testStreams.push(stream);
                    return stream;
                  } finally { window.testPendingMicrophones--; }
                };
                const NativeSocket = window.WebSocket;
                window.WebSocket = class extends NativeSocket {
                  constructor(...args) {
                    super(...args);
                    if (this.url.includes('/ws/voice')) window.testVoiceSockets.push(this);
                  }
                  send(data) {
                    if (this.url.includes('/ws/voice') && typeof data !== 'string') window.testMicFrames++;
                    return super.send(data);
                  }
                };
                const NativeContext = window.AudioContext;
                window.AudioContext = class extends NativeContext {
                  constructor(...args) { super(...args); window.testContexts.push(this); }
                  createBufferSource() {
                    const source = super.createBufferSource();
                    const start = source.start.bind(source);
                    const stop = source.stop.bind(source);
                    source.start = (...args) => {
                      window.testSourceStarts++; window.testActiveSources.add(source);
                      return start(...args);
                    };
                    source.stop = (...args) => {
                      window.testSourceStops++; window.testActiveSources.delete(source);
                      return stop(...args);
                    };
                    source.addEventListener('ended', () => {
                      window.testSourceEnds++; window.testActiveSources.delete(source);
                    });
                    return source;
                  }
                };
            """)
            legacy_page = context.new_page()
            legacy_requests = []
            legacy_page.on("request", lambda request: legacy_requests.append(request.url))
            legacy_page.route(backend_url + "/", lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"name":"Indu", "version":"0.6.1"}),
                headers={"Access-Control-Allow-Origin":frontend_url}))
            legacy_page.goto(frontend_url)
            legacy_page.get_by_role("alert").filter(has_text="needs restarting").wait_for()
            assert legacy_page.get_by_role("button", name="Hey Indu", exact=False).is_disabled()
            assert not any("/api/contacts" in url or "/api/whatsapp/" in url for url in legacy_requests)
            legacy_page.close()
            checks.append("Old backend shows a restart message and does not request missing contacts or WhatsApp routes")
            page = context.new_page()
            errors = []
            clock_warnings = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: clock_warnings.append(message.text) if "THREE.Clock" in message.text else None)
            page.goto(frontend_url)
            page.get_by_role("heading", name="Welcome to Indu.", exact=True).wait_for()
            assert page.get_by_label("Gemini API key", exact=True).get_attribute("type") == "password"
            page.get_by_role("button", name="Continue without Gemini", exact=True).click()
            checks.append("First launch offers a masked Gemini key field with a local-only fallback")
            page.get_by_role("button", name="Hey Indu", exact=False).wait_for()
            page.locator('.assistant-scene[data-renderer="webgl"]').wait_for(timeout=15000)
            page.get_by_role("heading", name="Gemini AI", exact=True).wait_for()
            assert page.get_by_text("Ollama", exact=False).count() == 0
            page.screenshot(path=str(ROOT / "reports/frontend-3d-desktop.png"), full_page=True, animations="disabled")
            checks.append("3D WebGL core renders in the dashboard")
            checks.append("Interface loads with manual-start fallback")
            icon = page.request.get(frontend_url + "/favicon.svg")
            assert icon.status == 200
            assert page.locator('link[rel="icon"]').get_attribute("href") == "/favicon.svg"
            checks.append("Explicit favicon resolves without a missing-icon request")

            route_states = {}
            def resources_stopped():
                page.wait_for_function("""window.testPendingMicrophones === 0
                  && window.testStreams.every(s => s.getTracks().every(t => t.readyState === 'ended'))
                  && window.testContexts.every(c => c.state === 'closed')
                  && window.testVoiceSockets.every(s => s.readyState === WebSocket.CLOSED)
                  && window.testActiveSources.size === 0
                  && window.testWakeListeners.size === 0""")
                for _ in range(100):
                    if all(state["closed"] for state in route_states.values()): break
                    page.wait_for_timeout(20)
                assert all(state["closed"] for state in route_states.values()), "Voice socket did not close"

            page.get_by_role("button", name="Hey Indu", exact=False).click()
            page.get_by_role("alert").filter(has_text="GEMINI_API_KEY").wait_for()
            page.get_by_text("Voice connection error", exact=True).wait_for()
            page.get_by_role("button", name="Retry voice", exact=True).wait_for()
            page.get_by_role("button", name="Exit Indu", exact=True).click()
            resources_stopped()
            checks.append("Missing key shows an explicit error and Exit releases pending microphone resources")

            routes = []
            def capture_socket(route):
                routes.append(route)
                state = {"frames":0, "closed":False, "stop_received":False}
                route_states[id(route)] = state
                def message(data):
                    if isinstance(data, bytes): state["frames"] += 1
                    elif json.loads(data).get("type") == "stop": state["stop_received"] = True
                def closed(code, reason):
                    state["closed"] = True
                    route.close(code=code or 1000, reason=reason or "Closed")
                route.on_message(message)
                route.on_close(closed)
            page.route_web_socket("**/ws/voice", capture_socket)
            def start_voice(retry=False):
                before = len(routes)
                page.get_by_role("button", name="Retry voice" if retry else "Hey Indu", exact=retry).click()
                for _ in range(150):
                    if len(routes) > before:
                        break
                    page.wait_for_timeout(20)
                assert len(routes) == before + 1, "Expected one voice socket for activation"
                return routes[-1]

            route = start_voice()
            page.get_by_role("button", name="Exit Indu", exact=True).click()
            resources_stopped()
            checks.append("Exit during startup cancels the pending socket and microphone initialization")

            route = start_voice()
            route.send(json.dumps({"type":"ready"}))
            page.get_by_text("Listening...", exact=True).wait_for()
            page.wait_for_function("window.testStreams.some(s => s.getTracks().some(t => t.readyState === 'live'))")
            connection_count = len(routes)
            stream_count = page.evaluate("window.testStreams.length")
            context_count = page.evaluate("window.testContexts.length")

            def event(kind, **values):
                route.send(json.dumps({"type":kind, **values}))
            def pcm(duration=.3):
                samples = array.array('h', (int(math.sin(2 * math.pi * 220 * i / 24000) * 1200) for i in range(int(duration * 24000))))
                if sys.byteorder != 'little': samples.byteswap()
                route.send(samples.tobytes())
            def begin_question(question):
                event("user_turn_started")
                event("user_transcript", text=question)
                event("input_complete")
            def same_conversation():
                assert len(routes) == connection_count
                assert page.evaluate("window.testStreams.length") == stream_count
                assert page.evaluate("window.testContexts.length") == context_count
                assert not route_states[id(route)]["closed"]
                assert page.evaluate("window.testStreams.filter(s => s.getTracks().some(t => t.readyState === 'live')).length") == 1
                page.get_by_role("button", name="Exit Indu", exact=True).wait_for()

            questions = ["What is Python?", "What are its applications?", "Give me a real-world example.",
                         "Explain the exit code in Python.", "How can I stop a timer?"]
            starts_before = page.evaluate("window.testSourceStarts")
            ends_before = page.evaluate("window.testSourceEnds")
            for index, question in enumerate(questions):
                frames_before = route_states[id(route)]["frames"]
                begin_question(question)
                page.get_by_text("Thinking...", exact=True).wait_for()
                event("indu_transcript", text=f"Synthetic answer {index+1}.")
                pcm()
                page.get_by_text("Indu is speaking...", exact=True).wait_for()
                event("turn_complete")
                page.get_by_text("Listening...", exact=True).wait_for()
                page.wait_for_function("window.testActiveSources.size === 0")
                for _ in range(100):
                    if route_states[id(route)]["frames"] > frames_before: break
                    page.wait_for_timeout(20)
                assert route_states[id(route)]["frames"] > frames_before, "Microphone stopped forwarding frames"
                same_conversation()
            assert page.evaluate("window.testSourceStarts") - starts_before == 5
            assert page.evaluate("window.testSourceEnds") - ends_before == 5
            for question in questions: page.get_by_text(question, exact=True).wait_for()
            checks.append("Five consecutive PCM responses finish playback and resume Listening on one socket, microphone and AudioContext")
            checks.append("Voice history and ordinary words such as exit or stop do not terminate the conversation")

            for command in ["open youtube", "open instagram"]:
                begin_question(command)
                event("command_started")
                page.get_by_text("Executing command...", exact=True).wait_for()
                event("command_result", response="Simulated command result.", success=True)
                event("turn_complete")
                page.get_by_text("Listening...", exact=True).wait_for()
                same_conversation()
            checks.append("Simulated local command results preserve the continuous session")

            begin_question("Tell me a long story.")
            event("indu_transcript", text="A longer answer begins.")
            pcm(2)
            page.get_by_text("Indu is speaking...", exact=True).wait_for()
            stopped_before = page.evaluate("window.testSourceStops")
            event("user_turn_started")
            event("interrupted")
            event("user_transcript", text="Actually, keep it short.")
            event("input_complete")
            event("indu_transcript", text="A shorter answer.")
            pcm()
            event("turn_complete")
            page.get_by_text("Listening...", exact=True).wait_for()
            assert page.evaluate("window.testSourceStops") > stopped_before
            same_conversation()
            checks.append("Interruption stops queued audio and accepts the next question without reconnecting")

            begin_question("Read a long explanation.")
            event("indu_transcript", text="Explanation in progress.")
            pcm(2)
            page.get_by_text("Indu is speaking...", exact=True).wait_for()
            page.get_by_role("button", name="Stop speaking", exact=True).click()
            page.get_by_text("Listening...", exact=True).wait_for()
            scheduled = page.evaluate("window.testSourceStarts")
            pcm()
            page.wait_for_timeout(100)
            assert page.evaluate("window.testSourceStarts") == scheduled
            event("turn_complete")
            same_conversation()
            checks.append("Stop speaking drops remaining response audio while leaving the microphone and socket active")

            begin_question("One more answer before exiting.")
            event("indu_transcript", text="This response remains visible after Exit.")
            pcm(2)
            event("turn_complete")
            page.get_by_text("Indu is speaking...", exact=True).wait_for()
            page.get_by_role("button", name="Exit Indu", exact=True).click()
            page.get_by_text("Indu is sleeping", exact=True).wait_for()
            resources_stopped()
            page.wait_for_timeout(650)
            resources_stopped()
            page.get_by_text("This response remains visible after Exit.", exact=True).wait_for()
            checks.append("Exit during playback closes audio contexts, stops tracks and sources, closes sockets and wake recognition, and preserves history")

            route = start_voice()
            event("ready")
            page.get_by_text("Listening...", exact=True).wait_for()
            begin_question("Exit Indu.")
            page.get_by_text("Indu is sleeping", exact=True).wait_for()
            resources_stopped()
            checks.append("The exact voice command Exit Indu performs the same complete cleanup")

            route = start_voice()
            event("ready")
            page.get_by_text("Listening...", exact=True).wait_for()
            event("error", message="Simulated network interruption.")
            page.get_by_text("Voice connection error", exact=True).wait_for()
            page.get_by_role("button", name="Retry voice", exact=True).wait_for()
            resources_stopped()
            route = start_voice(retry=True)
            event("ready")
            page.get_by_text("Listening...", exact=True).wait_for()
            page.get_by_role("button", name="Exit Indu", exact=True).click()
            resources_stopped()
            checks.append("Transport failure has a visible Error state and an explicit Retry action")

            route = start_voice()
            event("ready")
            page.get_by_text("Listening...", exact=True).wait_for()
            page.evaluate("window.testStreams.at(-1).getAudioTracks()[0].dispatchEvent(new Event('ended'))")
            page.get_by_text("Voice connection error", exact=True).wait_for()
            resources_stopped()
            page.get_by_role("button", name="Exit Indu", exact=True).click()
            checks.append("Unexpected microphone loss shows Error and releases voice resources")

            page.get_by_role("button", name="WhatsApp and contacts").click()
            page.get_by_role("tab", name="Contacts").click()
            page.get_by_label("Name", exact=True).fill("Smoke Contact")
            page.get_by_label("WhatsApp number").fill("+919000000009")
            page.get_by_role("button", name="Add contact", exact=True).click()
            page.get_by_text("Contact saved.", exact=False).wait_for()
            page.get_by_role("tab", name="Send a message").click()
            page.get_by_role("combobox", name="WhatsApp recipient").select_option(label="Smoke Contact · +919000000009")
            page.get_by_label("Message", exact=True).fill("Offline confirmation test. Do not transmit.")
            page.get_by_role("button", name="Preview WhatsApp message").click()
            page.get_by_role("region", name="Confirm WhatsApp message").wait_for()
            page.get_by_role("blockquote").filter(has_text="Offline confirmation test").wait_for()
            page.get_by_role("button", name="Cancel", exact=True).click()
            page.get_by_role("region", name="Confirm WhatsApp message").wait_for(state="hidden")
            page.get_by_role("button", name="Close WhatsApp").click()
            checks.append("Contacts persist through the local API and message preview requires explicit confirmation; cancel transmits nothing")

            # Exercise setup using an in-browser fake validation response. No actual
            # Gemini key or OS credential is written by this controlled UI test.
            page.get_by_role("button", name="Settings", exact=True).click()
            secret = "browser-fixture-not-a-real-api-key"
            key_input = page.get_by_label("Gemini API key", exact=True)
            key_input.fill(secret)
            page.get_by_role("button", name="Show key", exact=True).click()
            assert key_input.get_attribute("type") == "text"
            page.get_by_role("button", name="Hide key", exact=True).click()
            def fake_setup(route):
                if route.request.method == "PUT":
                    route.fulfill(json={"configured":True, "verified":True, "source":"os_credential_store"})
                elif route.request.method == "DELETE":
                    route.fulfill(json={"configured":False, "verified":False})
                else:
                    route.continue_()
            page.route("**/api/settings/gemini", fake_setup)
            page.get_by_role("button", name="Validate and save", exact=True).click()
            page.get_by_text("Gemini connection validated", exact=True).wait_for()
            assert key_input.input_value() == ""
            assert secret not in page.evaluate("JSON.stringify({...localStorage})")
            page.get_by_role("button", name="Disconnect Gemini", exact=True).click()
            page.get_by_text("Gemini is not connected", exact=True).wait_for()
            page.get_by_label("Microphone", exact=True).wait_for()
            page.get_by_label("Speaker", exact=True).wait_for()
            page.get_by_role("button", name="Close settings", exact=True).click()
            page.unroute("**/api/settings/gemini", fake_setup)
            checks.append("Settings masks and clears API input, avoids browser secret storage, exposes audio device controls and handles simulated validation/disconnect")

            composer = page.get_by_role("textbox", name="Message Indu", exact=True)
            composer.fill("Set a timer for 1 second")
            page.get_by_role("button", name="Send message to Indu", exact=True).click()
            page.get_by_role("button", name="Reminder due:", exact=False).wait_for(timeout=12000)
            page.get_by_role("button", name="Reminders", exact=False).click()
            page.get_by_role("button", name="Dismiss", exact=True).click()
            page.get_by_text("No active reminders.", exact=False).wait_for()
            page.get_by_role("button", name="Close reminders", exact=True).click()
            page.get_by_role("button", name="Reminder due:", exact=False).wait_for(state="hidden")
            checks.append("A natural-language timer becomes due through the real scheduler, displays an alert and stays dismissed")
            if errors:
                raise AssertionError(f"Browser runtime errors: {errors}")
            assert not clock_warnings, "Deprecated Three.js clock is still in use"
            checks.append("No uncaught browser runtime errors")
            def check_layout():
                return page.evaluate("""() => {
                  const panel = document.querySelector('.indu-container').getBoundingClientRect();
                  return panel.top + scrollY >= 0 && panel.left >= 0 && panel.right <= innerWidth + 1
                    && document.documentElement.scrollWidth <= innerWidth;
                }""")
            assert check_layout(), "Desktop panel is clipped or misaligned"
            page.screenshot(path=str(ROOT / "reports/frontend-smoke.png"), full_page=True, animations="disabled")
            page.set_viewport_size({"width": 390, "height": 640})
            assert check_layout(), "Mobile panel is clipped or horizontally overflows"
            page.screenshot(path=str(ROOT / "reports/frontend-3d-mobile.png"), full_page=True, animations="disabled")
            checks.append("Desktop and mobile layouts scroll without clipping or horizontal overflow")
            browser.close()
        report = {"status": "passed", "checks": checks,
                  "scope": "Installed headless Edge, real local API and temporary database, fake microphone, native WebAudio playback of synthetic PCM, and simulated Gemini messages. Five consecutive responses verified without reconnecting. No authenticated Gemini call or physical speech-quality test."}
        (ROOT / "reports/browser-smoke.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        for process in reversed(processes):
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        logs.close()
        temporary.cleanup()


if __name__ == "__main__":
    main()
