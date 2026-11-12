import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from tempfile import TemporaryDirectory

from backend.tools.router import InduCommandRouter
from backend.tools.contacts import ContactStore


class RouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.contacts = ContactStore(Path(self.directory.name) / "contacts.db", defaults={"deva": "9000000001"})
        self.router = InduCommandRouter(self.contacts)

    async def test_routing_corpus(self):
        cases = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/routing_cases.json").read_text())
        router = self.router
        with patch.object(router, "open_url", return_value=True), \
             patch.object(router, "open_windows_app", return_value=True), \
             patch.object(router, "open_vscode", return_value=True), \
             patch.object(router, "open_settings", return_value=True), \
             patch.object(router.messenger, "send_text", new=AsyncMock(return_value={"success": True, "status": "sent", "response": "Sent"})):
            for case in cases:
                with self.subTest(text=case["input"]):
                    result = await router.execute(case["input"])
                    self.assertEqual(result["type"], case["expected"])

    async def test_browser_failure_is_not_reported_as_success(self):
        with patch("webbrowser.open", return_value=False):
            result = await InduCommandRouter().execute("open youtube")
        self.assertFalse(result["success"])

    async def test_direct_send_preserves_case_punctuation_and_request_id(self):
        with patch.object(self.router.messenger, "send_text", new=AsyncMock(return_value={"success": True, "status": "sent", "response": "Sent"})) as sender:
            result = await self.router.execute("send a message to deva Hello YouTube & INDIA.", request_id="specific-request")
        sender.assert_awaited_once_with("Deva", "Hello YouTube & INDIA.", request_id="specific-request")
        self.assertEqual(result["action"], "whatsapp_preview")

    async def test_unknown_contact_returns_failure_without_opening_browser(self):
        with patch("webbrowser.open") as opener:
            result = await self.router.execute("message unknown Hello")
        self.assertFalse(result["success"])
        opener.assert_not_called()

    async def test_multiword_names_aliases_and_saying_delimiters(self):
        self.contacts.save("Deva Kumar", "+919000000002", ["Brother"])
        for command, expected in [
            ("send a WhatsApp message to Deva Kumar saying I'll be there at six.", ("Deva Kumar", "I'll be there at six.")),
            ("send a message to Brother on WhatsApp saying Hello!", ("Brother", "Hello!")),
            ("message Deva Kumar: Keep Saying Yes", ("Deva Kumar", "Keep Saying Yes")),
            ("send Deva Kumar a message Hello", ("Deva Kumar", "Hello")),
            ("whatsapp Deva Meet me on WhatsApp", ("Deva", "Meet me on WhatsApp")),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.router.parse_whatsapp_message(command), expected)

    async def test_negated_and_quoted_messages_do_not_send(self):
        with patch.object(self.router.messenger, "send_text", new=AsyncMock()) as sender:
            for text in ["Do not send a message to Deva Hello", "Explain how to send a WhatsApp message to Deva saying Hello"]:
                self.assertEqual((await self.router.execute(text))["type"], "chat")
            sender.assert_not_awaited()

    async def test_polite_punctuation_and_no_shell_injection(self):
        router = InduCommandRouter()
        with patch.object(router, "open_url", return_value=True) as opener:
            result = await router.execute("Please open YouTube please!")
            self.assertTrue(result["success"])
            opener.reset_mock()
            result = await router.execute("open youtube & calc")
            self.assertEqual(result["type"], "chat")
            opener.assert_not_called()
