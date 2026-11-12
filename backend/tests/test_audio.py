import asyncio
import contextlib
import io
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import numpy as np
from backend.voice.stt import InduSpeechToText
from backend.voice.tts import InduTextToSpeech
from backend.tools.browser import BrowserController
from backend.gemini_live import InduGeminiLive


class AudioTests(unittest.TestCase):
    def test_tts_uses_unique_files_and_selects_script_voice(self):
        async def save(text, output, voice):
            output.write_bytes(b"audio")
        with TemporaryDirectory() as directory:
            engine = InduTextToSpeech()
            engine.audio_dir = Path(directory)
            with patch.object(type(engine), "available", True), \
                 patch.object(engine, "_generate_speech", side_effect=save) as generate, \
                 contextlib.redirect_stdout(io.StringIO()):
                first = engine.generate_audio("Hello")
                second = engine.generate_audio("\u0c28\u0c2e\u0c38\u0c4d\u0c15\u0c3e\u0c30\u0c02")
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists() and second.exists())
            self.assertEqual(generate.call_args.args[2], "te-IN-ShrutiNeural")

    def test_failed_tts_cleans_up_partial_file(self):
        async def fail(text, output, voice):
            output.write_bytes(b"partial")
            raise RuntimeError("Network unavailable")
        with TemporaryDirectory() as directory:
            engine = InduTextToSpeech()
            engine.audio_dir = Path(directory)
            with patch.object(type(engine), "available", True), \
                 patch.object(engine, "_generate_speech", side_effect=fail), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(engine.generate_audio("Hello"))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_recording_files_are_unique_valid_mono_wavs(self):
        engine = InduSpeechToText.__new__(InduSpeechToText)
        paths = [Path(engine._save_wav(np.zeros(16000, dtype=np.float32))) for _ in range(2)]
        try:
            self.assertNotEqual(*paths)
            with wave.open(str(paths[0]), "rb") as recording:
                self.assertEqual(recording.getframerate(), 16000)
                self.assertEqual(recording.getnchannels(), 1)
                self.assertEqual(recording.getnframes(), 16000)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def test_stt_detects_language_and_surfaces_transcription_failure(self):
        engine = InduSpeechToText.__new__(InduSpeechToText)
        engine.language = None
        from unittest.mock import Mock
        engine.model = Mock()
        engine.model.transcribe.return_value = ([NS(text="hello")], NS(language="te"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(engine.transcribe("unused.wav"), ("hello", "te"))
            self.assertIsNone(engine.model.transcribe.call_args.kwargs["language"])
            engine.model.transcribe.side_effect = RuntimeError("broken")
            with self.assertRaises(RuntimeError):
                engine.transcribe("unused.wav")


class BrowserThreadTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_work_and_cleanup_stay_on_one_thread(self):
        import threading
        controller = BrowserController()
        ids = []
        def record(*args):
            ids.append(threading.get_ident())
            return "ok"
        with patch.object(controller, "_execute_sync", side_effect=record), \
             patch.object(controller, "_close_sync", side_effect=record):
            await asyncio.gather(controller.execute("one"), controller.execute("two"))
            await controller.close()
        self.assertEqual(len(set(ids)), 1)
        self.assertNotEqual(ids[0], threading.get_ident())


class DemoTests(unittest.IsolatedAsyncioTestCase):
    async def test_microphone_callback_schedules_queue_access_on_event_loop(self):
        from unittest.mock import Mock
        engine = InduGeminiLive.__new__(InduGeminiLive)
        engine.running = True
        engine.loop = Mock()
        engine.loop.is_closed.return_value = False
        engine.audio_queue = asyncio.Queue(maxsize=1)
        engine.microphone_callback(b"first", 0, None, None)
        self.assertTrue(engine.audio_queue.empty())
        callback, data = engine.loop.call_soon_threadsafe.call_args.args
        callback(data)
        engine._enqueue_audio(b"latest")
        self.assertEqual(await engine.audio_queue.get(), b"latest")

    async def test_demo_preserves_audio_chunk_order_across_turns(self):
        engine = InduGeminiLive.__new__(InduGeminiLive)
        engine.running = True
        engine.output_queue = asyncio.Queue()
        class Session:
            def __init__(self):
                self.calls = 0
            async def receive(self):
                self.calls += 1
                if self.calls > 2:
                    return
                audio = NS(data=bytes([self.calls, 0]), mime_type="audio/pcm;rate=24000")
                yield NS(server_content=NS(interrupted=False, model_turn=NS(parts=[NS(inline_data=audio)])))
        await engine.receive_response(Session())
        self.assertEqual(await engine.output_queue.get(), b"\x01\x00")
        self.assertEqual(await engine.output_queue.get(), b"\x02\x00")
