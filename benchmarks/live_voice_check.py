"""Opt-in five-turn Live API check through the local backend; never reads its API key."""

import argparse
import asyncio
import io
import json
import sys
import time
import os
import subprocess
import tempfile
from pathlib import Path

import av
import httpx
from websockets.asyncio.client import connect

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [
    "Can you remember my test word mango?",
    "What test word did I ask you to remember?",
    "What is Python in one short sentence?",
    "Name one real world use of it.",
    "What is your date of birth? Answer briefly.",
]


def pcm_from_mp3(data):
    output = bytearray(6400)  # 200 ms leading silence at 16 kHz PCM16.
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    with av.open(io.BytesIO(data)) as source:
        for frame in source.decode(audio=0):
            for converted in resampler.resample(frame):
                output.extend(converted.to_ndarray().tobytes())
        for converted in resampler.resample(None):
            output.extend(converted.to_ndarray().tobytes())
    output.extend(bytes(32000))  # One second of silence lets automatic VAD close input.
    return bytes(output)


def windows_speech_clip(question):
    if os.name != "nt":
        raise RuntimeError("Speech generation is unavailable; no Windows speech fixture is available.")
    script = """
Add-Type -AssemblyName System.Speech
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $english = $speaker.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
  if ($english) { $speaker.SelectVoice($english.VoiceInfo.Name) }
  $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
  $speaker.SetOutputToWaveFile($payload.path, $format)
  $speaker.Speak($payload.text)
} finally { $speaker.Dispose() }
"""
    with tempfile.TemporaryDirectory(prefix="indu-speech-fixture-") as directory:
        output = Path(directory) / "question.wav"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                input=json.dumps({"path":str(output), "text":question}),
                                text=True, capture_output=True, timeout=25,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or not output.exists():
            raise RuntimeError("Windows speech synthesis fixture is unavailable.")
        return pcm_from_mp3(output.read_bytes())


async def run(base):
    clips = []
    speech_source = "edge_tts"
    async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=35) as client:
        info = (await client.get("/")).json()
        if "continuous_voice" not in info.get("features", []):
            raise RuntimeError("Restart the backend to load INDU 0.8 before this check.")
        health = (await client.get("/health")).json()
        if not health.get("gemini_live"):
            raise RuntimeError("Gemini Live is not configured in the backend terminal.")
        for index, question in enumerate(QUESTIONS, 1):
            if speech_source == "edge_tts":
                try:
                    response = await client.post("/api/speak", json={"text": question})
                    response.raise_for_status()
                    clip = pcm_from_mp3(response.content)
                except (httpx.HTTPError, av.AVError if hasattr(av, "AVError") else ValueError):
                    speech_source = "windows_offline_voice"
                    clip = await asyncio.to_thread(windows_speech_clip, question)
            else:
                clip = await asyncio.to_thread(windows_speech_clip, question)
            clips.append(clip)
            print(f"Prepared synthetic speech {index}/5", flush=True)

    websocket_url = base.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") + "/ws/voice"
    results = []
    completed = asyncio.Queue()
    ready = asyncio.Event()
    async with connect(websocket_url, origin="http://localhost:5173", proxy=None, max_size=2**23) as socket:
        async def receive():
            current = {"audio_bytes": 0, "user_transcript": "", "assistant_transcript": ""}
            async for message in socket:
                if isinstance(message, bytes):
                    current["audio_bytes"] += len(message)
                    continue
                event = json.loads(message)
                kind = event.get("type")
                if kind == "error":
                    raise RuntimeError(event.get("message", "Live voice failed"))
                if kind == "ready":
                    ready.set()
                elif kind == "user_transcript":
                    current["user_transcript"] += event.get("text", "")
                elif kind == "indu_transcript":
                    current["assistant_transcript"] += event.get("text", "")
                elif kind == "turn_complete":
                    await completed.put(current)
                    current = {"audio_bytes":0, "user_transcript":"", "assistant_transcript":""}

        receiver = asyncio.create_task(receive())
        try:
            readiness = asyncio.create_task(ready.wait())
            done, _ = await asyncio.wait([receiver, readiness], timeout=25, return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                receiver.result()
                raise RuntimeError("Gemini closed before readiness.")
            if not ready.is_set():
                readiness.cancel()
                await asyncio.gather(readiness, return_exceptions=True)
                raise RuntimeError("Gemini readiness timed out.")
            for index, clip in enumerate(clips):
                start = time.perf_counter()
                for offset in range(0, len(clip), 1280):
                    if receiver.done():
                        receiver.result()
                        raise RuntimeError("Gemini disconnected before five turns.")
                    await socket.send(clip[offset:offset+1280])
                    await asyncio.sleep(.04)
                turn = asyncio.create_task(completed.get())
                done, _ = await asyncio.wait([receiver, turn], timeout=45, return_when=asyncio.FIRST_COMPLETED)
                if receiver in done:
                    turn.cancel()
                    await asyncio.gather(turn, return_exceptions=True)
                    receiver.result()
                    raise RuntimeError("Gemini disconnected between turns.")
                if turn not in done:
                    turn.cancel()
                    await asyncio.gather(turn, return_exceptions=True)
                    raise RuntimeError("Timed out waiting for a complete Gemini audio response.")
                result = turn.result()
                if not result["audio_bytes"]:
                    raise RuntimeError("A turn completed without response audio.")
                results.append({"question":QUESTIONS[index], **result,
                                "wall_seconds":round(time.perf_counter()-start, 2)})
                print(f"Gemini audio response {index+1}/5 completed on the same socket", flush=True)
            await socket.send(json.dumps({"type":"stop"}))
            await asyncio.wait_for(socket.wait_closed(), 10)
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
    recalled = "mango" in results[1]["assistant_transcript"].casefold()
    return {"status":"passed" if recalled else "context_check_failed", "turns":results,
            "speech_fixture":speech_source,
            "same_frontend_websocket":True, "context_word_recalled":recalled,
            "explicit_stop_closed_websocket":True,
            "scope":"Real local backend and authenticated Gemini Live, synthesized speech input and returned PCM audio. No physical microphone recording or audible speaker-quality check. No desktop or WhatsApp actions."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.base_url))
    except Exception as error:
        # Only local test/action errors are returned; no credentials are read by this script.
        result = {"status":"unavailable", "reason":str(error),
                  "scope":"The real five-turn Gemini check could not be completed; this is not a pass."}
    output = ROOT / "reports/live-voice-check.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key:value for key,value in result.items() if key != "turns"}, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
