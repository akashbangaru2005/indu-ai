"""Optional public-provider connectivity check, without fabricated fallbacks."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.tools.live_info import LiveInformation


async def main():
    provider = LiveInformation()
    async def check(command):
        try:
            value = await provider.execute(command)
            return {"question":command, "status":"passed", "response":value}
        except RuntimeError as failure:
            return {"question":command, "status":"unavailable", "reason":str(failure)}
    results = await asyncio.gather(*(check(command) for command in [
        "What is the Bitcoin price right now?", "What is today's weather in Hyderabad?",
        "What is the latest technology news?", "What is the current time in Paris?",
    ]))
    report = {"checks":results, "scope":"Real public provider connectivity; no prices or headlines are fabricated when an endpoint fails."}
    (ROOT / "reports/live-information-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"checks":[{"question":row["question"], "status":row["status"]} for row in results]}))


if __name__ == "__main__":
    asyncio.run(main())
