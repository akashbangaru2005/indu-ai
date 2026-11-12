"""Local contacts and a durable outbox for explicitly requested WhatsApp sends."""

import json
import hashlib
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from ..paths import data_directory
from ..deployment import is_cloud

DEFAULT_DATABASE = Path(os.environ.get("INDU_DATABASE", str(data_directory() / "indu.db")))


def message_fingerprint(message):
    return "sha256:" + hashlib.sha256(message.encode("utf-8")).hexdigest()


def normalize_name(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split()).strip(" .!?")


def normalize_phone(value):
    if re.search(r"[^\d\s()+.-]", value):
        raise ValueError("Use a phone number with its country code.")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and not value.strip().startswith("+"):
        digits = os.environ.get("WHATSAPP_COUNTRY_CODE", "91") + digits
    if not re.fullmatch(r"[1-9]\d{7,14}", digits):
        raise ValueError("Use a valid international phone number, such as +91 followed by 10 digits.")
    return digits


class ContactStore:
    def __init__(self, database=DEFAULT_DATABASE, defaults=None):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        legacy = Path(__file__).resolve().parents[1] / "database" / "indu.db"
        if not is_cloud() and database == DEFAULT_DATABASE and not os.environ.get("INDU_DATABASE") and not self.database.exists() and legacy.is_file():
            with sqlite3.connect(legacy) as source, sqlite3.connect(self.database) as destination:
                source.backup(destination)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
                    aliases TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS whatsapp_outbox (
                    request_id TEXT PRIMARY KEY, contact TEXT NOT NULL, phone TEXT NOT NULL,
                    message TEXT NOT NULL, status TEXT NOT NULL, message_id TEXT,
                    detail TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY);
            """)
            # Retain deduplication metadata without retaining private message bodies.
            for row in connection.execute("SELECT request_id,message FROM whatsapp_outbox"):
                if not row["message"].startswith("sha256:"):
                    connection.execute("UPDATE whatsapp_outbox SET message=? WHERE request_id=?",
                                       (message_fingerprint(row["message"]), row["request_id"]))
            migrated = connection.execute("SELECT 1 FROM app_migrations WHERE name='legacy_contacts'").fetchone()
            if defaults and not migrated:
                for name, phone in defaults.items():
                    connection.execute("INSERT INTO contacts VALUES (?, ?, ?, ?)",
                                       (uuid4().hex, name.title(), normalize_phone(phone), "[]"))
                connection.execute("INSERT INTO app_migrations VALUES ('legacy_contacts')")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _contact(row):
        return {**dict(row), "aliases": json.loads(row["aliases"])}

    def list(self):
        with self.connect() as connection:
            return [self._contact(row) for row in connection.execute("SELECT * FROM contacts ORDER BY name COLLATE NOCASE")]

    def resolve(self, name):
        key = normalize_name(name)
        matches = []
        for contact in self.list():
            if key in {normalize_name(contact["name"]), *(normalize_name(alias) for alias in contact["aliases"])}:
                matches.append(contact)
        if len(matches) > 1:
            raise ValueError("More than one contact matches that name. Choose a distinct full name in Contacts.")
        if matches:
            return matches[0]
        # Explicit numbers are accepted; arbitrary unresolved names never become recipients.
        if re.fullmatch(r"\+?[\d\s()-]{8,22}", name):
            phone = normalize_phone(name)
            return {"id": None, "name": "+" + phone, "phone": phone, "aliases": []}
        return None

    def save(self, name, phone, aliases=None, contact_id=None):
        name = " ".join(name.split()).strip()
        if not 1 <= len(name) <= 80:
            raise ValueError("Enter a contact name of 1 to 80 characters.")
        aliases = list(dict.fromkeys(" ".join(alias.split()).strip() for alias in (aliases or []) if alias.strip()))
        if len(aliases) > 10 or any(len(alias) > 80 for alias in aliases):
            raise ValueError("Use up to 10 short contact aliases.")
        keys = {normalize_name(name), *(normalize_name(alias) for alias in aliases)}
        if any(not any(char.isalnum() for char in key) for key in keys):
            raise ValueError("Contact names and aliases must contain letters or numbers.")
        phone = normalize_phone(phone)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM contacts").fetchall()
            if contact_id and not any(row["id"] == contact_id for row in rows):
                raise KeyError("Contact was not found.")
            for row in rows:
                other = self._contact(row)
                other_keys = {normalize_name(other["name"]), *(normalize_name(alias) for alias in other["aliases"])}
                if other["id"] != contact_id and keys & other_keys:
                    raise ValueError("That name or alias already belongs to another contact.")
            contact_id = contact_id or uuid4().hex
            connection.execute("INSERT OR REPLACE INTO contacts VALUES (?, ?, ?, ?)",
                               (contact_id, name, phone, json.dumps(aliases)))
        return {"id": contact_id, "name": name, "phone": phone, "aliases": aliases}

    def delete(self, contact_id):
        with self.connect() as connection:
            if not connection.execute("DELETE FROM contacts WHERE id=?", (contact_id,)).rowcount:
                raise KeyError("Contact was not found.")

    def claim_send(self, request_id, contact, message):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM whatsapp_outbox WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing["phone"] != contact["phone"] or existing["message"] != message_fingerprint(message):
                    raise ValueError("This request ID was already used for a different message.")
                return dict(existing), False
            connection.execute("INSERT INTO whatsapp_outbox VALUES (?, ?, ?, ?, 'sending', NULL, NULL, ?)",
                               (request_id, contact["name"], contact["phone"], message_fingerprint(message), datetime.now(timezone.utc).isoformat()))
        return self.get_send(request_id), True

    def get_send(self, request_id):
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM whatsapp_outbox WHERE request_id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def update_send(self, request_id, status, message_id=None, detail=None):
        with self.connect() as connection:
            connection.execute("UPDATE whatsapp_outbox SET status=?, message_id=COALESCE(?,message_id), detail=? WHERE request_id=?",
                               (status, message_id, detail, request_id))
        return self.get_send(request_id)

    def acknowledge(self, message_id, ack):
        status = {-1: "failed", 0: "pending", 1: "sent", 2: "delivered", 3: "read", 4: "read"}.get(ack)
        if status:
            with self.connect() as connection:
                ranks = {"sending": 0, "unknown": 0, "pending": 0, "failed": -1, "sent": 1, "delivered": 2, "read": 3}
                for row in connection.execute("SELECT request_id,status FROM whatsapp_outbox WHERE message_id=?", (message_id,)):
                    old_rank = ranks.get(row["status"], 0)
                    if ranks[status] >= old_rank or status == "failed" and old_rank == 0:
                        connection.execute("UPDATE whatsapp_outbox SET status=? WHERE request_id=?", (status, row["request_id"]))

    def messages(self):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT request_id,contact,status,message_id,detail,created_at FROM whatsapp_outbox ORDER BY created_at DESC LIMIT 30")]
