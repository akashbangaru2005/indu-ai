"""Cloud startup, policy and multi-turn voice checks without credentials or hardware."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import importlib.abc
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BLOCKED = {"pygame", "sounddevice", "pyautogui", "keyring", "faster_whisper", "playwright", "winreg", "pyttsx3"}


class NoDesktopImports(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempts = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in BLOCKED:
            self.attempts.append(fullname)
            raise ImportError("Desktop dependency blocked by cloud check")


def run_http_server(checks):
    import httpx
    from websockets.sync.client import connect
    with socket.socket() as socket_probe:
        socket_probe.bind(("127.0.0.1", 0))
        port = socket_probe.getsockname()[1]
    address = f"http://127.0.0.1:{port}"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # Capture logs outside stdout to avoid deadlocks while the server runs.
    with TemporaryDirectory(prefix="indu-uvicorn-") as folder:
        with (Path(folder) / "server.log").open("w+") as logs:
            # A stdin stop signal permits clean shutdown on Windows as well as Linux;
            # terminating a Windows venv redirector can otherwise orphan its child.
            server_code = ("import sys, threading, uvicorn; "
                           f"server=uvicorn.Server(uvicorn.Config('backend.main:app',host='127.0.0.1',port={port},log_level='warning')); "
                           "threading.Thread(target=lambda:(sys.stdin.readline(),setattr(server,'should_exit',True)),daemon=True).start(); "
                           "server.run()")
            process = subprocess.Popen([sys.executable, "-c", server_code],
                                       cwd=ROOT, env=dict(os.environ), stdin=subprocess.PIPE,
                                       stdout=logs, stderr=logs, creationflags=flags)
            try:
                with httpx.Client(trust_env=False, timeout=1) as client:
                    for _ in range(150):
                        if process.poll() is not None:
                            logs.seek(0)
                            raise AssertionError("Cloud server exited: " + logs.read())
                        try:
                            response = client.get(address + "/health")
                            if response.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise AssertionError("Cloud Uvicorn health check timed out")
                    assert response.json()["deployment_mode"] == "cloud"
                    for path in ("/", "/health"):
                        assert client.get(address + path, headers={"Host":"indu-ai.onrender.com"}).status_code == 200
                connection = socket.create_connection(("127.0.0.1", port), timeout=5)
                with connect(f"ws://indu-ai.onrender.com:{port}/ws/voice", sock=connection, origin="https://frontend.example", proxy=None, open_timeout=5) as websocket:
                    assert json.loads(websocket.recv())["type"] == "error"  # key intentionally absent
                checks.append("Real Uvicorn serves root/health and accepts a voice WebSocket with the production Host header")
            finally:
                if process.poll() is None:
                    try:
                        process.stdin.write(b"stop\n")
                        process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        pass
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=ROOT / "reports/render-cloud-smoke.json")
    args = parser.parse_args()
    checks = []
    blocker = NoDesktopImports()
    sys.meta_path.insert(0, blocker)
    with TemporaryDirectory(prefix="indu-cloud-check-") as folder:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.update(INDU_DEPLOYMENT_MODE="cloud", INDU_DATA_DIR=folder,
                          INDU_DATABASE=str(Path(folder) / "test.db"), INDU_DESKTOP="1",
                          INDU_ALLOWED_ORIGINS="https://frontend.example", INDU_ALLOWED_HOSTS="api.example.test",
                          RENDER_EXTERNAL_HOSTNAME="indu-test.onrender.com")
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect
        import backend.main as main_api
        from backend.tools.desktop import launch_registered, open_known_folder
        assert main_api.genai is not None
        checks.append("backend.main imports with Google SDK present and local hardware/GUI imports blocked")
        forbidden = Mock(side_effect=AssertionError("Cloud attempted a desktop operation"))
        with patch.object(main_api.credentials, "load_key", forbidden), patch.object(main_api.credentials, "save_key", forbidden), patch.object(main_api.credentials, "delete_key", forbidden), patch("webbrowser.open", forbidden), patch("subprocess.Popen", forbidden), TestClient(main_api.app) as client:
            health = client.get("/health").json()
            assert health["deployment_mode"] == "cloud"
            assert health["capabilities"]["browser_audio_streaming"]
            assert not any(health["capabilities"][name] for name in ("desktop_control", "backend_microphone", "backend_audio_playback"))
            assert "gemini_live" in health["features"] and "continuous_voice" in health["features"]
            assert "desktop_launch" not in health["features"]
            assert client.get("/health", headers={"Host":"indu-test.onrender.com"}).status_code == 200
            assert client.get("/health", headers={"Host":"api.example.test"}).status_code == 200
            assert client.get("/health", headers={"Host":"attacker.example"}).status_code == 400
            assert client.get("/health", headers={"Origin":"https://attacker.example"}).status_code == 403
            preflight = client.options("/api/chat", headers={"Origin":"https://frontend.example", "Access-Control-Request-Method":"POST", "Access-Control-Request-Headers":"Content-Type"})
            assert preflight.status_code == 200 and preflight.headers["access-control-allow-origin"] == "https://frontend.example"
            checks.append("Cloud health, Render/custom host routing and explicit frontend CORS work")
            for hostname in ("indu-ai.onrender.com", "indu-ai.onrender.com:443", "localhost", "127.0.0.1"):
                for path in ("/", "/health"):
                    response = client.get(path, headers={"Host":hostname})
                    assert response.status_code == 200 and isinstance(response.json(), dict)
            for path in ("/", "/health"):
                assert client.get(path, headers={"Host":"indu-ai.onrender.com.attacker.example"}).status_code == 400
                assert client.get(path, headers={"Host":"attacker.example", "X-Forwarded-Host":"indu-ai.onrender.com"}).status_code == 400
                assert client.get(path, headers={"Host":"indu-ai.onrender.com", "X-Forwarded-Host":"attacker.example", "X-Forwarded-Proto":"https"}).status_code == 200
            checks.append("Root and health accept production/local hosts, reject untrusted/lookalike hosts and cannot be bypassed with X-Forwarded-Host")
            for target in ["YouTube", "Instagram", "Chrome", "Microsoft Word", "Excel", "PowerPoint", "Visual Studio Code", "Settings", "Calculator", "File Explorer", "Downloads", "Bluetooth settings", "Wi-Fi settings"]:
                response = client.post("/api/chat", json={"message":"Open " + target})
                assert response.status_code == 200 and response.json()["success"] is False
                assert "cloud" in response.json()["response"]
            assert not main_api.router.open_url("https://www.youtube.com")
            assert not main_api.router.open_windows_app("calc")
            assert not main_api.router.open_vscode()
            assert not main_api.router.open_settings()
            assert not launch_registered("word")
            assert not open_known_folder("downloads")
            assert client.post("/api/listen").status_code == 409
            assert main_api.stt is None
            assert client.post("/api/app/exit").status_code == 409
            assert not client.get("/api/app/status").json()["desktop"]
            assert client.put("/api/settings/gemini", json={"api_key":"cloud-fixture-not-a-real-key"}).status_code == 409
            assert client.delete("/api/settings/gemini").status_code == 409
            assert client.get("/api/settings/gemini").json()["credential_management"] == "environment"
            assert client.post("/api/whatsapp/connect").status_code == 503
            assert client.post("/api/whatsapp/preview/fixture/confirm").status_code == 409
            assert client.get("/api/whatsapp/status").json()["state"] == "disabled"
            checks.append("Desktop commands, server microphone/playback, OS credentials, WhatsApp browser launches and app shutdown are disabled before access")
            with patch.object(main_api.tts, "generate_audio", forbidden):
                assert main_api.tts.speak("Local playback must be disabled") is None
                assert main_api.tts._speak("Local playback must be disabled") is None
                assert main_api.tts.speak_async("No playback thread") is None
            mp3 = Path(folder) / "fixture.mp3"
            mp3.write_bytes(b"browser-mp3-fixture")
            with patch.object(main_api.tts, "generate_audio", return_value=mp3):
                response = client.post("/api/speak", json={"text":"Browser playback only"})
            assert response.status_code == 200 and response.content == b"browser-mp3-fixture"
            assert not mp3.exists()
            checks.append("Optional network MP3 generation still serves browser audio while all server playback paths stay disabled")
            created = client.post("/api/contacts", json={"name":"Cloud Fixture", "phone":"+919000000009"})
            assert created.status_code == 200 and len(client.get("/api/contacts").json()["contacts"]) == 1
            assert client.get("/api/reminders").status_code == 200
            checks.append("Cloud contacts and reminder storage remain available")

            class Provider:
                def __init__(self):
                    self.batches = asyncio.Queue()
                    self.frames = []
                    self.closed = False
                async def send_realtime_input(self, audio):
                    self.frames.append(audio["data"])
                    turn = len(self.frames)
                    await self.batches.put([
                        NS(input_transcription=NS(text=f"Explain cloud concept {turn}", finished=True)),
                        NS(output_transcription=NS(text=f"Answer {turn}"), model_turn=NS(parts=[NS(inline_data=NS(data=b"\x01\x00", mime_type="audio/pcm;rate=24000"))])),
                        NS(turn_complete=True),
                    ])
                async def receive(self):
                    for content in await self.batches.get():
                        yield NS(server_content=content)
            provider = Provider()
            calls = []
            @asynccontextmanager
            async def connect(**kwargs):
                calls.append(kwargs)
                try:
                    yield provider
                finally:
                    provider.closed = True
            fake = NS(aio=NS(live=NS(connect=connect)), close=Mock())
            with patch.object(main_api, "GEMINI_API_KEY", "cloud-fixture-not-a-real-key"), patch.object(main_api, "gemini_client", fake):
                with client.websocket_connect("/ws/voice", headers={"Host":"indu-ai.onrender.com", "Origin":"https://frontend.example"}) as websocket:
                    assert websocket.receive_json()["type"] == "ready"
                    for turn in range(5):
                        websocket.send_bytes(b"\x00\x00" * 32)
                        response_audio = []
                        while True:
                            event = websocket.receive()
                            if "bytes" in event:
                                response_audio.append(event["bytes"])
                            elif json.loads(event["text"])["type"] == "turn_complete":
                                break
                        assert response_audio == [b"\x01\x00"]
                    websocket.send_json({"type":"stop"})
                    assert websocket.receive()["type"] == "websocket.close"
            assert len(calls) == 1 and len(provider.frames) == 5 and provider.closed
            assert main_api.active_voice_sessions == 0
            checks.append("Cloud Gemini Live bridge streams browser PCM in and provider PCM out for five turns on one mocked session, then cleans up on stop")
            with client.websocket_connect("/ws/voice", headers={"Origin":"https://frontend.example"}) as websocket:
                assert websocket.receive_json()["type"] == "error"
            try:
                with client.websocket_connect("/ws/voice", headers={"Origin":"https://attacker.example"}):
                    raise AssertionError("Untrusted voice origin was accepted")
            except WebSocketDisconnect as failure:
                assert failure.code == 1008
            forbidden.assert_not_called()
        assert not blocker.attempts, blocker.attempts
        checks.append("No pygame, sounddevice, pyautogui, keyring, Whisper, Playwright, winreg or pyttsx3 import was attempted")
        run_http_server(checks)
    report = {"status":"passed", "platform":platform.system(), "python":platform.python_version(), "checks":checks,
              "scope":"Cloud policy, actual ASGI/Uvicorn startup and WebSocket upgrades; multi-turn Gemini responses are mocked. No real API key or hardware is used."}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
