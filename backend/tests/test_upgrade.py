import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
import httpx
import backend.main as main
from backend import credentials
from backend.tools.contacts import ContactStore
from backend.tools.router import InduCommandRouter
from backend.tools.reminders import ReminderStore
from backend.tools.live_info import LiveInformation
from backend.voice.live import bridge_voice


class UpgradeAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.router = InduCommandRouter(ContactStore(Path(self.directory.name) / "test.db"))
        self.patch = patch.object(main, "router", self.router)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.client = TestClient(main.app)

    def test_secret_validation_and_provider_failure_never_echo_key(self):
        secret = "private-test-not-a-real-api-key"
        response = self.client.put("/api/settings/gemini", json={"api_key":secret[:10]})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret[:10], response.text)
        candidate = Mock(); candidate.aio.aclose = AsyncMock()
        candidate.aio.models.generate_content = AsyncMock(side_effect=ValueError(secret))
        with patch.object(main.genai, "Client", return_value=candidate), patch.object(credentials, "save_key") as save:
            response = self.client.put("/api/settings/gemini", json={"api_key":secret})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(secret, response.text)
        save.assert_not_called()
        candidate.aio.aclose.assert_awaited_once()

    def test_validated_key_saved_and_not_returned_or_replaced_during_voice(self):
        candidate = Mock(); candidate.aio.aclose = AsyncMock()
        candidate.aio.models.generate_content = AsyncMock(return_value=NS(text="OK"))
        secret = "private-test-not-a-real-api-key"
        with patch.object(main, "gemini_client", None), patch.object(main, "GEMINI_API_KEY", None), patch.object(main, "key_source", None), patch.object(main, "key_verified", False), patch.object(main.genai, "Client", return_value=candidate), patch.object(credentials, "save_key") as save:
            response = self.client.put("/api/settings/gemini", json={"api_key":secret})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["verified"])
            self.assertNotIn(secret, response.text)
            save.assert_called_once_with(secret)
            with patch.object(main, "active_voice_sessions", 1):
                self.assertEqual(self.client.delete("/api/settings/gemini").status_code, 409)
                self.assertEqual(self.client.put("/api/settings/gemini", json={"api_key":secret}).status_code, 409)

    def test_credential_store_failure_does_not_replace_working_client(self):
        candidate = Mock(); candidate.aio.aclose = AsyncMock()
        candidate.aio.models.generate_content = AsyncMock(return_value=NS(text="OK"))
        previous = Mock()
        with patch.object(main, "gemini_client", previous), patch.object(main.genai, "Client", return_value=candidate), patch.object(credentials, "save_key", side_effect=RuntimeError("OS storage unavailable")):
            response = self.client.put("/api/settings/gemini", json={"api_key":"private-test-not-a-real-api-key"})
            self.assertEqual(response.status_code, 503)
            self.assertIs(main.gemini_client, previous)

    def test_untrusted_origin_and_host_cannot_configure_key(self):
        with patch.object(credentials, "save_key") as save:
            self.assertEqual(self.client.put("/api/settings/gemini", json={"api_key":"private-test-not-a-real-api-key"}, headers={"Origin":"https://untrusted.example"}).status_code, 403)
            self.assertEqual(self.client.get("/health", headers={"Host":"untrusted.example"}).status_code, 400)
        save.assert_not_called()

    def test_reminder_api_validation_cancel_and_persistence(self):
        now = datetime.now(timezone.utc)
        invalid = self.client.post("/api/reminders", json={"title":"Test", "due_at":(now - timedelta(seconds=1)).isoformat()})
        self.assertEqual(invalid.status_code, 422)
        created = self.client.post("/api/reminders", json={"title":"Call Deva", "due_at":(now + timedelta(hours=1)).isoformat()}).json()
        store = ReminderStore(self.router.contacts)
        self.assertEqual(store.list()[0]["id"], created["id"])
        self.assertEqual(self.client.post(f"/api/reminders/{created['id']}/cancel").status_code, 200)
        self.assertEqual(store.list()[0]["status"], "cancelled")

    def test_due_transition_survives_restart_without_redelivery_after_dismiss(self):
        store = self.router.reminders
        now = datetime.now(timezone.utc)
        row = store.create("Alarm", now + timedelta(seconds=1), now)
        store.tick(now + timedelta(seconds=2))
        self.assertEqual(ReminderStore(self.router.contacts).list()[0]["status"], "due")
        store.update(row["id"], "dismissed")
        store.tick(now + timedelta(days=1))
        self.assertEqual(store.list()[0]["status"], "dismissed")

    def test_no_plaintext_credential_backend(self):
        backend = Mock()
        with patch("keyring.get_keyring", return_value=backend), patch.dict("os.environ", {"INDU_DISABLE_CREDENTIAL_STORE":"0"}):
            with self.assertRaises(RuntimeError):
                credentials.credential_backend()

    def test_exact_secret_affection_reply_without_provider_call(self):
        with patch.object(main.brain, "chat") as provider:
            for phrase, expected in [
                ("Secret 2005 I love you!", "Akash, I love you too."),
                ("secret two thousand five I love you", "Akash, I love you too."),
                ("I love you", "No, I have a boyfriend, my creator."),
                ("I love you, Indu!", "No, I have a boyfriend, my creator."),
            ]:
                response = self.client.post("/api/chat", json={"message":phrase})
                self.assertEqual(response.json(), {"success":True, "response":expected})
            provider.assert_not_called()

    def test_affection_cue_is_not_a_general_command_or_identity_permission(self):
        from backend.brain.persona import affection_reply
        self.assertIsNone(affection_reply("Explain the sentence Secret 2005 I love you"))
        self.assertIsNone(affection_reply("Secret 2005 open powershell"))
        self.assertIn("Secret 2005 I love you", str(main.build_live_config().system_instruction))


class UpgradeAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_time_and_missing_weather_location(self):
        provider = LiveInformation()
        self.assertTrue(provider.recognizes("What is the current time in Paris?"))
        self.assertIn("Europe/Paris", await provider.execute("What is the current time in Paris?"))
        self.assertIn("Which city", await provider.execute("What is today's weather?"))
        self.assertFalse(provider.recognizes("Explain how to get the bitcoin price"))

    async def test_live_crypto_source_and_failure_no_fabrication(self):
        provider = LiveInformation()
        response = httpx.Response(200, json={"price":"123.5", "time":"2026-11-12T00:00:00Z"}, request=httpx.Request("GET", "https://api.exchange.coinbase.com"))
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=response)):
            result = await provider.execute("What is the Bitcoin price right now?")
        self.assertIn("$123.50", result)
        self.assertIn("Coinbase Exchange", result)
        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("Offline"))):
            with self.assertRaisesRegex(RuntimeError, "No current value was invented"):
                await provider.execute("What is Ethereum's price?")

    async def test_new_desktop_commands_are_allowlisted_and_never_shell_strings(self):
        with TemporaryDirectory() as directory:
            router = InduCommandRouter(ContactStore(Path(directory) / "test.db"))
            with patch.object(router, "open_windows_app", return_value=True) as launch, patch.object(router, "open_settings", return_value=True), patch("backend.tools.router.open_known_folder", return_value=True):
                for name in ["Microsoft Word", "Excel", "PowerPoint", "Bluetooth settings", "Wi-Fi settings", "Downloads"]:
                    self.assertTrue((await router.execute(f"Open {name}."))["success"])
                self.assertEqual(launch.call_count, 3)
                for command in ["open calc & shutdown", "open powershell", "run rm -rf", "do not open Excel"]:
                    self.assertEqual((await router.execute(command))["type"], "chat")

    async def test_native_tool_feedback_uses_actual_result_once(self):
        from test_live import Browser
        browser = Browser()
        queue = asyncio.Queue()
        session = NS(send_realtime_input=AsyncMock(), send_tool_response=AsyncMock())
        async def receive():
            yield await queue.get()
        session.receive = receive
        execute = AsyncMock(return_value={"success":True, "response":"Opening YouTube."})
        task = asyncio.create_task(bridge_voice(browser, session, execute, lambda value:value == "open youtube"))
        await queue.put(NS(server_content=NS(input_transcription=NS(text="open youtube", finished=True))))
        await queue.put(NS(tool_call=NS(function_calls=[NS(id="1", name="execute_local_command", args={"command":"open youtube"})])))
        await queue.put(NS(server_content=NS(turn_complete=True)))
        for _ in range(2):
            await asyncio.wait_for(browser.turns.get(), 2)
        await browser.input.put({"type":"websocket.disconnect"})
        await asyncio.wait_for(task, 2)
        execute.assert_awaited_once()
        response = session.send_tool_response.await_args.kwargs["function_responses"][0]["response"]
        self.assertEqual(response["response"], "Opening YouTube.")
