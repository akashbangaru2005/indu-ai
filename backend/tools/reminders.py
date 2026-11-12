"""Durable reminders: due items remain visible until explicitly dismissed."""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class ReminderStore:
    def __init__(self, contacts):
        self.store = contacts
        with self.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL)""")

    def create(self, title, due_at, now=None):
        now = now or datetime.now(timezone.utc)
        if due_at.tzinfo is None:
            raise ValueError("Choose a date, time and timezone.")
        due_at = due_at.astimezone(timezone.utc)
        if not title.strip() or len(title) > 250:
            raise ValueError("Use a reminder title of 1–250 characters.")
        if due_at <= now:
            raise ValueError("Choose a time in the future.")
        row = {"id": uuid4().hex, "title": title.strip(), "due_at": due_at.isoformat(),
               "status": "scheduled", "created_at": now.isoformat()}
        with self.store.connect() as db:
            db.execute("INSERT INTO reminders VALUES (:id,:title,:due_at,:status,:created_at)", row)
        return row

    def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.store.connect() as db:
            db.execute("UPDATE reminders SET status='due' WHERE status='scheduled' AND due_at<=?", (now.isoformat(),))

    def list(self):
        self.tick()
        with self.store.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM reminders ORDER BY CASE status WHEN 'due' THEN 0 WHEN 'scheduled' THEN 1 ELSE 2 END, due_at LIMIT 500")]

    def update(self, identifier, status):
        if status not in {"cancelled", "dismissed"}:
            raise ValueError("Invalid reminder status.")
        with self.store.connect() as db:
            result = db.execute("UPDATE reminders SET status=? WHERE id=? AND status IN ('scheduled','due')", (status, identifier))
            if not result.rowcount:
                raise ValueError("That reminder is missing or already completed.")

    @staticmethod
    def recognizes(command):
        return bool(re.match(r"^(?:(?:please )?(?:set (?:a |an )?(?:timer|alarm)|remind me)|(?:show|list|cancel|dismiss) (?:my |a |the )?reminders?)\b", command, re.I))

    def execute(self, command):
        text = command.strip().rstrip(".!?")
        numbers = {"one":1, "two":2, "three":3, "four":4, "five":5, "six":6, "seven":7, "eight":8, "nine":9, "ten":10, "fifteen":15, "twenty":20, "thirty":30, "forty":40, "sixty":60}
        text = re.sub(r"\b(" + "|".join(numbers) + r")\s+(?=seconds?\b|minutes?\b|hours?\b)", lambda match:str(numbers[match[1].lower()]) + " ", text, flags=re.I)
        if re.fullmatch(r"(?:show|list) (?:my )?reminders", text, re.I):
            pending = [row for row in self.list() if row["status"] in {"scheduled", "due"}]
            return "No active reminders." if not pending else "\n".join(f"{row['title']} — {datetime.fromisoformat(row['due_at']).astimezone().strftime('%d %b, %I:%M %p')} ({row['status']})" for row in pending)
        if re.match(r"^(?:cancel|dismiss) ", text, re.I):
            name = re.sub(r"^(?:cancel|dismiss) (?:my |the |a )?reminder\s*", "", text, flags=re.I).strip()
            matches = [row for row in self.list() if row["status"] in {"scheduled", "due"} and (row["title"].casefold() == name.casefold() or row["id"] == name)]
            if len(matches) != 1:
                return "Choose the exact reminder in Reminders to cancel it. No reminder was changed."
            self.update(matches[0]["id"], "cancelled")
            return f"Cancelled {matches[0]['title']}."
        duration = re.search(r"\b(?:for|in) (\d+)\s*(seconds?|minutes?|hours?)\b", text, re.I)
        now = datetime.now().astimezone()
        if duration:
            count = int(duration[1])
            if not 1 <= count <= 100000:
                raise ValueError("Choose a positive timer duration up to 100000 units.")
            seconds = count * (3600 if duration[2].lower().startswith("hour") else 60 if duration[2].lower().startswith("minute") else 1)
            due = now + timedelta(seconds=seconds)
            title = re.split(r"\bto\b", text, maxsplit=1, flags=re.I)[-1].strip() if re.search(r"\bto\b", text, re.I) else f"{count} {duration[2]} timer"
        else:
            clock = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.I)
            tomorrow = bool(re.search(r"\btomorrow\b", text, re.I))
            if not clock:
                return "Choose an exact time in Reminders, or say ‘Remind me tomorrow at 9 AM to call Deva.’"
            hour, minute = int(clock[1]), int(clock[2] or 0)
            if minute > 59 or (clock[3] and not 1 <= hour <= 12) or (not clock[3] and hour > 23):
                raise ValueError("Use a valid clock time.")
            if clock[3]:
                hour = hour % 12 + (12 if clock[3].lower() == "pm" else 0)
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=int(tomorrow))
            if due <= now:
                due += timedelta(days=1)
            title = re.split(r"\bto\b", text, maxsplit=1, flags=re.I)[-1].strip() if re.search(r"\bto\b", text, re.I) else "Alarm"
        row = self.create(title, due)
        return f"Reminder set: {row['title']} — {due.strftime('%d %b, %I:%M:%S %p %Z')}. Keep Indu running; overdue reminders appear when it next starts."
