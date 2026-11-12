"""Summarize only executed checks and distinguish authenticated limitations."""
import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
reports = ROOT / "reports"


def contents(name):
    raw = (reports / name).read_bytes()
    return raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8-sig")


def result(name):
    return json.loads(contents(name))


backend = contents("continuous-voice-backend-tests.txt")
frontend = contents("continuous-voice-frontend-tests.txt")
assert re.search(r"\bOK\s*$", backend)
assert re.search(r"fail\s+0", frontend)
checks = {name:result(name) for name in ["browser-smoke.json", "packaged-browser-check.json", "installer-check.json", "credential-store-check.json"]}
assert all(item["status"] == "passed" for item in checks.values())
build = contents("windows-build.log")
assert "Windows installer created." in build
artifacts = []
for name in ["InduAI/InduAI.exe", "InduAI-0.8.0-windows.zip", "InduAI-0.8.0-Setup.exe"]:
    path = ROOT / "release" / name
    artifacts.append({"path":"release/" + name, "bytes":path.stat().st_size, "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
report = {
    "checked_at":datetime.now(timezone.utc).isoformat(),
    "status":"local_checks_passed_with_authenticated_text_unverified",
    "backend":{"status":"passed", "tests":int(re.search(r"Ran (\d+) tests", backend)[1]), "log":"continuous-voice-backend-tests.txt"},
    "frontend":{"status":"passed", "tests":int(re.search(r"tests\s+(\d+)", frontend)[1]), "log":"continuous-voice-frontend-tests.txt"},
    "browser":{"status":"passed", "checks":len(checks["browser-smoke.json"]["checks"]), "evidence":"browser-smoke.json"},
    "packaged_browser":{"status":"passed", "checks":len(checks["packaged-browser-check.json"]["checks"]), "evidence":"packaged-browser-check.json"},
    "installer":{"status":"passed", "evidence":"installer-check.json"},
    "os_credentials":{"status":"passed", "evidence":"credential-store-check.json"},
    "production_build":{"status":"passed", "log":"windows-build.log", "advisory":"Lazy Three.js chunk exceeds 500 kB; not a build failure."},
    "real_live_baseline":{"status":result("live-voice-check.json")["status"], "turns":len(result("live-voice-check.json")["turns"]), "evidence":"live-voice-check.json", "scope":"Previously running continuous-voice backend; newer native tools/persona configuration is not authenticated-provider validated."},
    "real_public_sources":{"evidence":"live-information-check.json", "checks":[{"question":row["question"], "status":row["status"]} for row in result("live-information-check.json")["checks"]]},
    "real_text_languages":{"status":"not_verified_on_updated_backend", "evidence":"language-check.json", "reason":"Older running backend returned errors and still lacked new settings routes after the restart confirmation. User then prohibited using the replacement key for tests."},
    "personalization":{"text":"Exact creator/guest replies verified by local API and frozen-app tests without a key.", "voice":"Same rule configured in Gemini instructions; no authenticated check with the replacement key."},
    "provided_key":{"saved_once":True, "storage":"OS credential service", "api_requests_made_by_agent":False, "evidence":"key-save-check.json"},
    "limitations":["Physical microphone/speaker quality and multilingual speech were not measured.", "Provider quotas/network/session limits remain; automatic session resumption is not implemented.", "WhatsApp requires the user's final Send in official Web.", "Reminders need the app/interface running for timely notifications.", "Installer is unsigned and has not been tested on other computers."],
    "artifacts":artifacts,
}
assert result("key-save-check.json")["status"] == "saved_without_api_request"
(reports / "continuous-voice-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"status":report["status"], "backend_tests":report["backend"]["tests"], "frontend_tests":report["frontend"]["tests"], "browser_checks":report["browser"]["checks"], "packaged_browser_checks":report["packaged_browser"]["checks"], "installer":"passed"}))
