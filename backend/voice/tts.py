"""
INDU TEXT-TO-SPEECH ENGINE
==========================

Natural neural voice implementation for Indu.

Voices:
English : en-IN-NeerjaExpressiveNeural
Hindi   : hi-IN-SwaraNeural
Telugu  : te-IN-ShrutiNeural
"""

import asyncio
import threading
from uuid import uuid4
from pathlib import Path
from ..paths import data_directory
from ..deployment import is_cloud

try:
    import edge_tts  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    edge_tts = None

_PLAYBACK_LOCK = threading.Lock()


class InduTextToSpeech:

    def __init__(
        self,
        rate: int = 175,
        volume: float = 1.0,
    ):

        self.rate = rate
        self.volume = volume

        # Default Indu voice
        self.voice_name = (
            "en-IN-NeerjaExpressiveNeural"
        )

        self._lock = threading.Lock()

        # Audio folder
        self.audio_dir = (
            data_directory() / "audio"
        )

        self.audio_dir.mkdir(
            exist_ok=True, parents=True
        )

    @property
    def available(self):
        return edge_tts is not None

    @staticmethod
    def detect_voice(text):
        if any("\u0c00" <= char <= "\u0c7f" for char in text):
            return "te-IN-ShrutiNeural"
        if any("\u0900" <= char <= "\u097f" for char in text):
            return "hi-IN-SwaraNeural"
        return "en-IN-NeerjaExpressiveNeural"

    # ========================================================
    # GENERATE SPEECH
    # ========================================================

    async def _generate_speech(
        self,
        text: str,
        output_file: Path,
        voice: str,
    ):

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=f"{round((self.rate / 175 - 1) * 100):+d}%",
            volume=f"{round((self.volume - 1) * 100):+d}%",
        )

        await communicate.save(
            str(output_file)
        )

    # ========================================================
    # GENERATE AUDIO FILE
    # ========================================================

    def generate_audio(
        self,
        text: str,
        voice: str | None = None,
    ):

        if not text or not self.available:
            return None

        text = text.strip()

        if not text:
            return None

        selected_voice = (
            voice
            or self.detect_voice(text)
        )

        output_file = (
            self.audio_dir / f"indu_{uuid4().hex}.mp3"
        )

        with self._lock:

            try:

                asyncio.run(
                    self._generate_speech(
                        text,
                        output_file,
                        selected_voice,
                    )
                )

                print(
                    f"Indu voice generated: "
                    f"{selected_voice}"
                )

                print(
                    f"Audio: {output_file}"
                )

                return output_file

            except Exception as e:

                output_file.unlink(missing_ok=True)

                print(
                    f"TTS Error: {e}"
                )

                return None

    # ========================================================
    # SPEAK
    # ========================================================

    def speak(
        self,
        text: str,
        voice: str | None = None,
    ):
        if is_cloud():
            return None
        with _PLAYBACK_LOCK:
            return self._speak(text, voice)

    def _speak(self, text, voice=None):
        if is_cloud():
            return None

        output_file = self.generate_audio(
            text,
            voice,
        )

        if output_file is None:
            return None

        # Play generated audio
        try:

            import pygame

            pygame.mixer.init()

            pygame.mixer.music.load(
                str(output_file)
            )

            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():

                pygame.time.Clock().tick(10)

            pygame.mixer.music.stop()

            pygame.mixer.quit()

        except Exception as e:

            print(
                f"Audio playback error: {e}"
            )

        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            output_file.unlink(missing_ok=True)

        return output_file

    # ========================================================
    # ASYNC SPEAK
    # ========================================================

    def speak_async(
        self,
        text: str,
        voice: str | None = None,
    ):
        if is_cloud():
            return None
        thread = threading.Thread(
            target=self.speak,
            args=(text, voice),
            daemon=True,
        )

        thread.start()

        return thread

    # ========================================================
    # LANGUAGE HELPERS
    # ========================================================

    def speak_english(
        self,
        text: str,
    ):

        return self.speak(
            text,
            "en-IN-NeerjaExpressiveNeural",
        )

    def speak_hindi(
        self,
        text: str,
    ):

        return self.speak(
            text,
            "hi-IN-SwaraNeural",
        )

    def speak_telugu(
        self,
        text: str,
    ):

        return self.speak(
            text,
            "te-IN-ShrutiNeural",
        )
