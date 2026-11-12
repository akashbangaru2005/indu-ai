"""Optional authenticated text-language check through the running local backend."""
import json
from pathlib import Path
import httpx

checks = []
with httpx.Client(base_url="http://127.0.0.1:8000", timeout=55) as client:
    for language, prompt, start, end in [
        ("Telugu", "సూర్యుడు అంటే ఏమిటి? తెలుగులో ఒక్క వాక్యంలో చెప్పు.", "\u0c00", "\u0c7f"),
        ("Hindi", "सूर्य क्या है? हिंदी में एक वाक्य में बताओ।", "\u0900", "\u097f"),
        ("English", "What is the Sun? Answer in one English sentence.", "A", "z"),
    ]:
        response = client.post("/api/chat", json={"message":prompt})
        data = response.json()
        text = data.get("response", "")
        checks.append({"language":language, "status":"passed" if response.status_code == 200 and any(start <= char <= end for char in text) else "failed", "response":text or data.get("detail")})
report = {"checks":checks, "scope":"Real Gemini text API through the running local backend; script-range detection checks response language, not speech or translation quality. No API key was read. This adds three harmless turns to text history."}
(Path(__file__).resolve().parents[1] / "reports/language-check.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({"checks":[{"language":row["language"], "status":row["status"]} for row in checks]}))
