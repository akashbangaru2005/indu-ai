"""Standalone Gemini voice demo. Run: python -m backend.gemini_live"""

import asyncio
import os
from contextlib import suppress

try:
    import sounddevice as sd
except ImportError:
    sd = None
try:
    from google import genai
except ImportError:
    genai = None

MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
INPUT_BLOCK_SIZE = 640


class InduGeminiLive:
    def __init__(self):
        if genai is None or sd is None:
            raise RuntimeError("Install google-genai and sounddevice to use this demo.")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY before starting live voice.")
        self.client = genai.Client(api_key=key)
        self.running = False
        self.audio_queue = asyncio.Queue(maxsize=25)
        self.output_queue = asyncio.Queue(maxsize=100)
        self.loop = None
        self.input_stream = None
        self.output_stream = None

    def get_config(self):
        return {
            "response_modalities": ["AUDIO"],
            "output_audio_transcription": {}, "input_audio_transcription": {},
            "system_instruction": "You are Indu, created by Akash Bangaru. Be friendly and concise. Understand English, Telugu and Hindi and respond in the user's language.",
        }

    def microphone_callback(self, indata, frames, time_info, status):
        if self.running and self.loop and not self.loop.is_closed():
            # PortAudio invokes this callback on a different OS thread.
            self.loop.call_soon_threadsafe(self._enqueue_audio, bytes(indata))

    def _enqueue_audio(self, data):
        if not self.running:
            return
        if self.audio_queue.full():
            self.audio_queue.get_nowait()  # Bound latency if the network falls behind.
        self.audio_queue.put_nowait(data)

    def start_microphone(self):
        self.input_stream = sd.RawInputStream(
            samplerate=INPUT_SAMPLE_RATE, blocksize=INPUT_BLOCK_SIZE,
            dtype="int16", channels=1, callback=self.microphone_callback,
        )
        self.input_stream.start()

    def stop_microphone(self):
        if self.input_stream:
            self.input_stream.stop()
            self.input_stream.close()
            self.input_stream = None

    async def send_microphone_audio(self, session):
        while self.running:
            data = await self.audio_queue.get()
            await session.send_realtime_input(audio={"data": data, "mime_type": "audio/pcm;rate=16000"})

    async def play_audio(self):
        while self.running:
            data = await self.output_queue.get()
            # A persistent output stream preserves chunks; sd.play replaces playback.
            await asyncio.to_thread(self.output_stream.write, data)

    async def receive_response(self, session):
        while self.running:
            received = False
            async for response in session.receive():
                received = True
                content = response.server_content
                if not content:
                    continue
                for label, field in (("You", "input_transcription"), ("Indu", "output_transcription")):
                    transcript = getattr(content, field, None)
                    if transcript and transcript.text:
                        print(f"{label}: {transcript.text}")
                if content.interrupted:
                    while not self.output_queue.empty():
                        self.output_queue.get_nowait()
                if content.model_turn:
                    for part in content.model_turn.parts or []:
                        audio = part.inline_data
                        if audio and audio.data and (audio.mime_type or "").startswith("audio/pcm"):
                            await self.output_queue.put(audio.data)
            if not received:
                return

    async def run(self):
        self.running = True
        self.loop = asyncio.get_running_loop()
        tasks = []
        try:
            async with self.client.aio.live.connect(model=MODEL, config=self.get_config()) as session:
                self.output_stream = sd.RawOutputStream(samplerate=OUTPUT_SAMPLE_RATE, dtype="int16", channels=1)
                self.output_stream.start()
                self.start_microphone()
                print("Indu is listening. Press Ctrl+C to stop.")
                tasks = [asyncio.create_task(self.send_microphone_audio(session)),
                         asyncio.create_task(self.receive_response(session)),
                         asyncio.create_task(self.play_audio())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        finally:
            self.running = False
            self.stop_microphone()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
                self.output_stream = None
            await self.client.aio.aclose()
            self.client.close()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(InduGeminiLive().run())
