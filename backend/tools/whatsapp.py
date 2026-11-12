"""Personal WhatsApp via the official web interface and explicit message previews.

No automatic transmission, account scraping, or unsupported sending API is used.
"""

import asyncio
import time
import webbrowser
from urllib.parse import urlencode
from uuid import uuid4

from .contacts import message_fingerprint


class WhatsAppService:
    def __init__(self, contacts):
        self.contacts = contacts
        self.previews = {}
        self.confirmed = {}
        self._state = {"state": "disconnected", "qr": None, "account": None,
                       "detail": "Link your personal account in official WhatsApp Web."}

    def status(self):
        return {**self._state, "installed": True, "mode": "official_whatsapp_web",
                "account_connection_verified": False, "direct_sending": False}

    async def connect(self):
        if not await asyncio.to_thread(webbrowser.open, "https://web.whatsapp.com"):
            raise RuntimeError("Could not open WhatsApp Web. Open web.whatsapp.com in your browser.")
        self._state.update(state="web_opened", detail="Scan the QR code in WhatsApp Web. Indu cannot verify account connection or delivery.")
        return self.status()

    async def disconnect(self):
        self._state.update(state="disconnected", detail="Local connection indicator cleared. Unlink this device from WhatsApp's Linked devices if needed.")
        return self.status()

    async def close(self):
        self.previews.clear()
        self.confirmed.clear()

    @staticmethod
    def result(record):
        status, name = record["status"], record["contact"]
        confirmed = status in {"sent", "delivered", "read", "draft_opened"}
        response = (f"WhatsApp draft opened for {name}. Review it in WhatsApp and press Send. Sending and delivery are not verified." if status == "draft_opened" else
                    f"Message sent to {name} on WhatsApp." if status in {"sent", "delivered", "read"} else
                    f"Your message to {name} is queued; WhatsApp has not confirmed sending yet. Check the chat before resending." if status == "pending" else
                    f"Sending to {name} is still in progress. This request will not be sent twice." if status == "sending" else
                    record.get("detail") or f"WhatsApp could not confirm sending to {name}. Check the chat before trying again.")
        metadata = {key: value for key, value in record.items() if key not in {"message", "phone"}}
        return {"success": confirmed, "status": status, "response": response, "message": metadata}

    async def send_text(self, recipient, message, request_id=None):
        """Prepare a preview only. A separate explicit confirmation opens a draft."""
        try:
            contact = self.contacts.resolve(recipient)
        except ValueError as error:
            return {"success": False, "status": "needs_clarification", "response": str(error)}
        if not contact:
            return {"success": False, "status": "failed", "response": f"I couldn't find {recipient}. Add their name and WhatsApp number in Contacts first."}
        message = message.strip()
        if not message or len(message) > 4000:
            return {"success": False, "status": "failed", "response": "Include a message of 1–4000 characters."}
        now = time.monotonic()
        self.previews = {key: value for key, value in self.previews.items() if value["expires"] > now}
        request_id = request_id or uuid4().hex
        existing = self.contacts.get_send(request_id)
        if existing:
            if existing["phone"] != contact["phone"] or existing["message"] != message_fingerprint(message):
                raise ValueError("This request ID was already used for a different message.")
            return self.result(existing)
        for identifier, preview in self.previews.items():
            if preview["request_id"] == request_id:
                if preview["contact"]["phone"] != contact["phone"] or preview["message"] != message:
                    raise ValueError("This request ID was already used for a different message.")
                return self._preview_result(identifier, preview)
        if len(self.previews) >= 100:
            raise ValueError("Too many pending previews. Cancel an earlier preview first.")
        identifier = uuid4().hex
        preview = {"request_id": request_id, "contact": contact, "message": message, "expires": now + 600}
        self.previews[identifier] = preview
        return self._preview_result(identifier, preview)

    @staticmethod
    def _preview_result(identifier, preview):
        return {"success": False, "status": "awaiting_confirmation",
                "response": f"Please review the complete message for {preview['contact']['name']} before continuing.",
                "confirmation": {"id": identifier, "recipient": preview["contact"]["name"],
                                 "phone": preview["contact"]["phone"], "message": preview["message"],
                                 "mode": "whatsapp_web_draft"}}

    async def confirm_preview(self, identifier):
        if identifier in self.confirmed:
            return self.result(self.contacts.get_send(self.confirmed[identifier]))
        preview = self.previews.pop(identifier, None)
        if not preview or preview["expires"] <= time.monotonic():
            raise ValueError("This preview expired or was cancelled. Prepare the message again.")
        record, claimed = self.contacts.claim_send(preview["request_id"], preview["contact"], preview["message"])
        self.confirmed[identifier] = record["request_id"]
        if len(self.confirmed) > 200:
            self.confirmed.pop(next(iter(self.confirmed)))
        if claimed:
            url = "https://web.whatsapp.com/send?" + urlencode({"phone": preview["contact"]["phone"], "text": preview["message"]})
            try:
                opened = await asyncio.to_thread(webbrowser.open, url)
                record = self.contacts.update_send(record["request_id"], "draft_opened" if opened else "failed",
                    detail=None if opened else "Could not open WhatsApp. No message has been sent.")
            except (OSError, RuntimeError):
                record = self.contacts.update_send(record["request_id"], "failed", detail="Could not open WhatsApp. No message has been sent.")
        return self.result(record)

    def cancel_preview(self, identifier):
        self.previews.pop(identifier, None)
        return {"success": True, "status": "cancelled"}
