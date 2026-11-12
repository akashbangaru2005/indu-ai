"""Repeatable local checks. External actions are mocked; model inference is opt-in."""

import argparse
import asyncio
import importlib.metadata
import json
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.tools.router import InduCommandRouter


def timing(samples):
    ordered = sorted(samples)
    return {"samples": len(samples), "p50_ms": round(statistics.median(samples), 4),
            "p95_ms": round(ordered[math.ceil(len(ordered) * .95) - 1], 4)}


async def routing(iterations):
    cases = json.loads((ROOT / "benchmarks/routing_cases.json").read_text())
    router = InduCommandRouter()
    results, samples = [], []
    with patch.object(router, "open_url", return_value=True), \
         patch.object(router, "open_windows_app", return_value=True), \
         patch.object(router, "open_vscode", return_value=True), \
         patch.object(router, "open_settings", return_value=True), \
         patch.object(router.messenger, "send_text", new=AsyncMock(return_value={"success": True, "status": "sent", "response": "Mocked send"})):
        for iteration in range(iterations):
            for case in cases:
                start = time.perf_counter()
                result = await router.execute(case["input"])
                samples.append((time.perf_counter() - start) * 1000)
                if iteration == 0:
                    results.append({**case, "actual": result["type"], "correct": result["type"] == case["expected"]})
    correct = sum(item["correct"] for item in results)
    return {"passed": correct, "total": len(cases), "accuracy_percent": 100 * correct / len(cases),
            "false_actions_on_chat": sum(item["expected"] == "chat" and item["actual"] != "chat" for item in results),
            "latency": timing(samples), "cases": results}


def api_benchmark(iterations):
    from fastapi.testclient import TestClient
    from backend.main import app, brain
    results = {}
    with TestClient(app) as client, patch.object(brain, "chat", return_value="Benchmark response"):
        for name, operation in [
            ("root", lambda: client.get("/")),
            ("chat_mocked_model", lambda: client.post("/api/chat", json={"message": "What is Python?"})),
        ]:
            operation()  # Warm-up.
            samples = []
            for _ in range(iterations):
                start = time.perf_counter()
                response = operation()
                if response.status_code != 200:
                    raise RuntimeError(f"{name}: unexpected HTTP {response.status_code}")
                samples.append((time.perf_counter() - start) * 1000)
            results[name] = timing(samples)
    return results


def gemini_benchmark():
    from backend.brain.llm import InduBrain, BrainError
    brain = InduBrain(max_history=0)
    if not brain.readiness()["configured"]:
        return {"status":"not_measured", "reason":"GEMINI_API_KEY or Google GenAI SDK is not configured."}
    results = []
    for prompt in ["What is 17 multiplied by 23? Answer briefly.",
                   "Explain Python dictionaries in two sentences.",
                   "Write one friendly greeting in Telugu."]:
        start = time.perf_counter()
        try:
            response = brain.chat(prompt, temperature=0)
        except BrainError as error:
            return {"status":"unavailable", "model":brain.model, "reason":str(error)}
        results.append({"prompt":prompt, "response":response,
                        "wall_ms":round((time.perf_counter()-start)*1000,2)})
    return {"status":"measured", "model":brain.model, "cases":results,
            "note":"Three real API smoke prompts. No quality score, throughput or first-token latency measurement."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--gemini", action="store_true", help="Run three real Gemini API prompts; API usage may incur charges")
    args = parser.parse_args()
    if args.iterations <= 0:
        parser.error("iterations must be positive")
    versions = {}
    for dependency in ["fastapi", "requests", "google-genai", "edge-tts", "faster-whisper", "httpx"]:
        try:
            versions[dependency] = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            versions[dependency] = None
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "processor": platform.processor(), "dependencies": versions},
        "scope": "Synthetic local routing and in-process FastAPI TestClient latency. All desktop/browser operations and API model responses mocked. Not end-to-end voice or model latency.",
        "routing": asyncio.run(routing(args.iterations)),
        "http_in_process": api_benchmark(args.iterations * 4),
        "gemini_text": gemini_benchmark() if args.gemini else {"status": "not_measured", "reason": "Pass --gemini to enable real API requests."},
        "gemini_voice": {"status": "not_measured", "reason": "Requires API credentials, network and real audio."},
        "speech_accuracy": {"status": "not_measured", "reason": "No labeled audio corpus is supplied."},
    }
    output = ROOT / "reports/benchmark-results.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = {"routing": {key: value for key, value in report["routing"].items() if key != "cases"},
               "http_in_process": report["http_in_process"], "gemini_text": report["gemini_text"]["status"]}
    print(json.dumps(summary, indent=2))
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
