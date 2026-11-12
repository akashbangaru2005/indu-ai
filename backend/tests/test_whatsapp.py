import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from backend.tools.contacts import ContactStore
from backend.tools.whatsapp import WhatsAppService


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ContactStore(Path(self.directory.name) / "contacts.db")

    def test_contacts_persist_with_normalized_phone_and_alias(self):
        contact = self.store.save("Deva Kumar", "9000000001", ["Brother"])
        reopened = ContactStore(self.store.database)
        self.assertEqual(reopened.resolve(" BROTHER ")["phone"], "919000000001")
        self.assertEqual(reopened.resolve("deva kumar")["id"], contact["id"])

    def test_duplicate_alias_rejected_and_edit_and_delete_work(self):
        contact = self.store.save("Deva", "+919000000001", ["Brother"])
        with self.assertRaises(ValueError):
            self.store.save("Akash", "+919000000002", ["brother"])
        self.store.save("Deva Kumar", "+919000000003", [], contact["id"])
        self.assertIsNone(self.store.resolve("Brother"))
        self.store.delete(contact["id"])
        self.assertEqual(self.store.list(), [])

    def test_invalid_numbers_and_empty_names_are_rejected(self):
        for name, phone in [("", "9000000001"), ("Name", "not a number"), ("Name", "+00000000")]:
            with self.subTest(name=name, phone=phone), self.assertRaises(ValueError):
                self.store.save(name, phone)

    def test_ambiguous_legacy_names_are_rejected(self):
        self.store.save("First", "+919000000001", ["Friend"])
        with self.store.connect() as connection:
            connection.execute("INSERT INTO contacts VALUES ('legacy','Second','919000000002','[\"Friend\"]')")
        with self.assertRaisesRegex(ValueError, "More than one"):
            self.store.resolve("Friend")


class SendTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.contacts = ContactStore(Path(self.directory.name) / "contacts.db")
        self.contact = self.contacts.save("Deva", "+919000000001")
        self.service = WhatsAppService(self.contacts)
        self.service._state["state"] = "connected"

    async def test_prepare_never_opens_browser_and_confirmation_opens_once(self):
        with patch("webbrowser.open", return_value=True) as opener:
            first = await self.service.send_text("Deva", "Hello.", "one-request")
            self.assertEqual(first["status"], "awaiting_confirmation")
            opener.assert_not_called()
            token = first["confirmation"]["id"]
            confirmed = await self.service.confirm_preview(token)
            repeated = await self.service.confirm_preview(token)
        opener.assert_called_once()
        self.assertEqual(confirmed["status"], "draft_opened")
        self.assertTrue(repeated["success"])
        self.assertNotIn("Message sent", confirmed["response"])
        reopened = WhatsAppService(ContactStore(self.contacts.database))
        with patch("webbrowser.open") as opener:
            result = await reopened.send_text("Deva", "Hello.", "one-request")
        self.assertEqual(result["status"], "draft_opened")
        opener.assert_not_called()

    async def test_message_body_is_not_persisted(self):
        preview = await self.service.send_text("Deva", "Private message body.", "private-request")
        self.assertEqual(self.contacts.messages(), [])
        with patch("webbrowser.open", return_value=True):
            await self.service.confirm_preview(preview["confirmation"]["id"])
        record = self.contacts.get_send("private-request")
        self.assertTrue(record["message"].startswith("sha256:"))
        self.assertNotIn("Private message body", str(record))
        self.assertNotIn("message", self.contacts.messages()[0])

    async def test_cancelled_and_expired_previews_cannot_open_browser(self):
        preview = await self.service.send_text("Deva", "Hello", "cancel-request")
        token = preview["confirmation"]["id"]
        self.service.cancel_preview(token)
        with patch("webbrowser.open") as opener:
            with self.assertRaises(ValueError):
                await self.service.confirm_preview(token)
        opener.assert_not_called()
        preview = await self.service.send_text("Deva", "Hello", "expired-request")
        token = preview["confirmation"]["id"]
        self.service.previews[token]["expires"] = 0
        with self.assertRaises(ValueError):
            await self.service.confirm_preview(token)

    async def test_unknown_contact_and_incomplete_message_never_open_browser(self):
        with patch("webbrowser.open") as opener:
            self.assertFalse((await self.service.send_text("Unknown", "Hello"))["success"])
            self.assertEqual((await self.service.send_text("Deva", "  "))["status"], "failed")
        opener.assert_not_called()

    async def test_browser_failure_does_not_claim_message_was_sent(self):
        preview = await self.service.send_text("Deva", "Hello", "failure-request")
        with patch("webbrowser.open", return_value=False):
            result = await self.service.confirm_preview(preview["confirmation"]["id"])
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")

    async def test_conflicting_request_id_is_rejected(self):
        await self.service.send_text("Deva", "First", "unique-request")
        with self.assertRaises(ValueError):
            await self.service.send_text("Deva", "Different", "unique-request")
