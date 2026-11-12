import unittest
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import backend.main as main
from backend.brain.llm import BrainError
from backend.tools.contacts import ContactStore
from backend.tools.router import InduCommandRouter


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ContactStore(Path(self.directory.name) / "contacts.db")
        router_patch = patch.object(main, "router", InduCommandRouter(self.store))
        router_patch.start()
        self.addCleanup(router_patch.stop)
        self.client = TestClient(main.app)

    def test_contact_management_and_confirmation_boundary(self):
        created = self.client.post("/api/contacts", json={"name":"Test Contact", "phone":"+919000000001", "aliases":["Friend"]})
        self.assertEqual(created.status_code, 200)
        contact_id = created.json()["id"]
        with patch("webbrowser.open", return_value=True) as opener:
            prepared = self.client.post("/api/whatsapp/send", json={"recipient":"Friend", "message":"Hello INDIA.", "request_id":"api-request-001"})
            self.assertEqual(prepared.json()["status"], "awaiting_confirmation")
            opener.assert_not_called()
            token = prepared.json()["confirmation"]["id"]
            result = self.client.post(f"/api/whatsapp/preview/{token}/confirm")
            self.assertEqual(result.json()["status"], "draft_opened")
            self.client.post(f"/api/whatsapp/preview/{token}/confirm")
            opener.assert_called_once()
        self.assertNotIn("message", self.client.get("/api/whatsapp/messages").json()["messages"][0])
        self.assertEqual(self.client.delete(f"/api/contacts/{contact_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/contacts").json()["contacts"], [])

    def test_untrusted_origin_cannot_confirm_a_preview(self):
        self.store.save("Test", "+919000000001")
        preview = self.client.post("/api/whatsapp/send", json={"recipient":"Test", "message":"Hello", "request_id":"secure-request"}).json()
        with patch("webbrowser.open") as opener:
            response = self.client.post(f"/api/whatsapp/preview/{preview['confirmation']['id']}/confirm", headers={"Origin":"https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        opener.assert_not_called()

    def test_root_and_blank_input(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.post("/api/chat", json={"message": "  "}).status_code, 400)
        self.assertEqual(self.client.post("/api/chat", json={"message": ""}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"message": "x" * 10001}).status_code, 422)

    def test_backend_imports_without_optional_voice_packages(self):
        script = """
import importlib.abc, sys
class MissingOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'google.genai', 'edge_tts', 'numpy', 'sounddevice', 'faster_whisper'}:
            raise ImportError('Optional dependency disabled by regression test')
sys.meta_path.insert(0, MissingOptional())
import backend.main as main
assert main.genai is None
assert main.stt is None
assert not main.tts.available
assert main.root()['status'] == 'online'
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15,
                                cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_knowledge_question_uses_brain_without_browser_action(self):
        with patch.object(main.brain, "chat", return_value="A video service") as chat, \
             patch("webbrowser.open") as opener:
            response = self.client.post("/api/chat", json={"message": "What is YouTube?"})
        self.assertEqual(response.json(), {"success": True, "response": "A video service"})
        chat.assert_called_once()
        opener.assert_not_called()

    def test_upstream_error_status_is_propagated(self):
        with patch.object(main.brain, "chat", side_effect=BrainError("Offline", 503)):
            self.assertEqual(self.client.post("/api/chat", json={"message": "Hello"}).status_code, 503)

    def test_action_failure_is_visible(self):
        with patch("webbrowser.open", return_value=False):
            response = self.client.post("/api/chat", json={"message": "open youtube"})
        self.assertFalse(response.json()["success"])

    def test_untrusted_browser_origin_is_blocked_before_action(self):
        with patch("webbrowser.open") as opener:
            response = self.client.post("/api/chat", json={"message": "open youtube"}, headers={"Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        opener.assert_not_called()

    def test_untrusted_websocket_origin_is_rejected(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/voice", headers={"Origin": "https://untrusted.example"}):
                self.fail("Untrusted WebSocket was accepted")

    def test_health_reports_degraded_and_does_not_load_whisper(self):
        with patch.object(main.brain, "readiness", return_value={"configured": False, "model": "gemini-test"}):
            health = self.client.get("/health").json()
        self.assertEqual(health["status"], "degraded")
        self.assertFalse(health["brain"])
        self.assertIsNone(main.stt)

    def test_root_declares_the_new_routes_and_gemini_provider(self):
        info = self.client.get("/").json()
        self.assertEqual(info["api_contract"], 1)
        self.assertIn("gemini_text", info["features"])
        self.assertIn("whatsapp_previews", info["features"])
        self.assertIn("continuous_voice", info["features"])
        for path in ["/api/contacts", "/api/whatsapp/status", "/api/whatsapp/messages"]:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_text_chat_uses_the_configured_gemini_client(self):
        client = Mock()
        client.models.generate_content.return_value.text = "Hello from Gemini"
        with patch.object(main, "gemini_client", client), patch.object(main.brain, "history", []):
            response = self.client.post("/api/chat", json={"message":"Hello"})
        self.assertEqual(response.json(), {"success":True, "response":"Hello from Gemini"})
        client.models.generate_content.assert_called_once()

    def test_missing_gemini_configuration_is_actionable(self):
        with patch.object(main, "gemini_client", None):
            response = self.client.post("/api/chat", json={"message":"Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

    def test_missing_voice_configuration_returns_error_and_closes(self):
        with patch.object(main, "GEMINI_API_KEY", None):
            with self.client.websocket_connect("/ws/voice") as socket:
                self.assertEqual(socket.receive_json()["type"], "error")
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_json()

    def test_speech_response_deletes_generated_file(self):
        with TemporaryDirectory() as directory:
            audio = Path(directory) / "voice.mp3"
            audio.write_bytes(b"test audio")
            with patch.object(main.tts, "generate_audio", return_value=audio), \
                 patch.object(type(main.tts), "available", True):
                response = self.client.post("/api/speak", json={"text": "Hello"})
            self.assertEqual(response.content, b"test audio")
            self.assertFalse(audio.exists())

    @unittest.skipIf(main.types is None, "Google GenAI SDK is optional")
    def test_live_config_matches_installed_sdk(self):
        config = main.build_live_config()
        self.assertEqual(config.response_modalities[0], "AUDIO")
