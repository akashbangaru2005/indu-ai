"""Check native vault persistence using a temporary, unrelated test credential."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.credentials import credential_backend

backend = credential_backend()
service = "InduAI.Validation." + uuid4().hex
account = "temporary-validation"
value = uuid4().hex  # Random fixture, not a provider key.
written = False
try:
    backend.set_password(service, account, value)
    written = True
    assert backend.get_password(service, account) == value
    report = {"status":"passed", "backend":type(backend).__module__, "write_read_delete":True,
              "scope":"Temporary test credential only; the user's Gemini credential was not read or changed."}
finally:
    if written:
        backend.delete_password(service, account)
assert backend.get_password(service, account) is None
(ROOT / "reports/credential-store-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
