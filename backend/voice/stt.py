"""
INDU SPEECH-TO-TEXT ENGINE
==========================

Microphone:
    System default input device; configurable sample rate (48000 Hz by default)

Whisper:
    16000 Hz mono audio

Pipeline:
    Microphone 48 kHz
        ↓
    Record
        ↓
    Resample to 16 kHz
        ↓
    Faster-Whisper
        ↓
    Text
"""

import os
import tempfile
import time
import wave
from importlib import import_module
from pathlib import Path

import numpy as np


# ==========================================================
# OPTIONAL AUDIO LIBRARIES
# ==========================================================

try:
    sd = import_module("sounddevice")
except ImportError:
    sd = None


try:
    WhisperModel = import_module("faster_whisper").WhisperModel
except ImportError:
    WhisperModel = None


class InduSpeechToText:

    # ======================================================
    # AUDIO SETTINGS
    # ======================================================

    # Your microphone works at 48 kHz.
    MICROPHONE_SAMPLE_RATE = 48000

    # Whisper expects 16 kHz audio.
    WHISPER_SAMPLE_RATE = 16000

    CHANNELS = 1

    # Let sounddevice choose the system default microphone.
    DEFAULT_INPUT_DEVICE = None

    # Give the user time to prepare before recording.
    LEAD_IN_SECONDS = 0.6

    # Minimum expected audio peak.
    MIN_PEAK_AMPLITUDE = 0.005

    # Whisper settings.
    BEAM_SIZE = 5

    def __init__(
        self,
        model_size: str = "base",
        sample_rate: int = MICROPHONE_SAMPLE_RATE,
        channels: int = CHANNELS,
        input_device: int | None = DEFAULT_INPUT_DEVICE,
        language: str | None = None,
    ):

        self.model_size = model_size
        self.sample_rate = sample_rate
        self.channels = channels
        self.input_device = input_device
        self.language = language
        if sample_rate <= 0 or channels != 1:
            raise ValueError("STT requires a positive sample rate and mono audio")

        print()
        print("========================================")
        print("        INDU SPEECH ENGINE")
        print("========================================")
        print()

        print(f"Whisper model : {model_size}")
        print(f"Input device  : {input_device}")
        print(f"Mic rate      : {sample_rate} Hz")
        print(f"Whisper rate  : {self.WHISPER_SAMPLE_RATE} Hz")
        print()

        if WhisperModel is None:
            raise RuntimeError(
                "faster-whisper is not installed.\n"
                "Run:\n"
                "pip install faster-whisper"
            )

        if sd is None:
            raise RuntimeError(
                "sounddevice is not installed.\n"
                "Run:\n"
                "pip install sounddevice"
            )

        self._print_input_device()

        print("Loading Whisper model...")
        print("Please wait...")
        print()

        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
        )

        print("Whisper model loaded successfully.")
        print()

    # ======================================================
    # MICROPHONE INFORMATION
    # ======================================================

    def _print_input_device(self):

        try:

            device_info = sd.query_devices(
                self.input_device
            )

            print("----------------------------------------")
            print("Microphone information")
            print("----------------------------------------")

            print(
                f"Name          : "
                f"{device_info['name']}"
            )

            print(
                f"Input channels: "
                f"{device_info['max_input_channels']}"
            )

            print(
                f"Native rate   : "
                f"{device_info['default_samplerate']:.0f} Hz"
            )

            print("----------------------------------------")
            print()

        except Exception as error:

            print(
                f"⚠️ Could not query microphone: {error}"
            )

            print()

    # ======================================================
    # RESAMPLE 48 kHz → 16 kHz
    # ======================================================

    def _resample_to_whisper_rate(
        self,
        audio: np.ndarray,
    ) -> np.ndarray:

        if self.sample_rate == self.WHISPER_SAMPLE_RATE:

            return audio.astype(
                np.float32,
                copy=False,
            )

        original_length = len(audio)

        if original_length == 0:

            return np.array(
                [],
                dtype=np.float32,
            )

        new_length = int(
            original_length
            * self.WHISPER_SAMPLE_RATE
            / self.sample_rate
        )

        if new_length <= 0:

            return np.array(
                [],
                dtype=np.float32,
            )

        # Linear interpolation.
        old_positions = np.linspace(
            0,
            1,
            original_length,
            endpoint=False,
        )

        new_positions = np.linspace(
            0,
            1,
            new_length,
            endpoint=False,
        )

        resampled = np.interp(
            new_positions,
            old_positions,
            audio,
        )

        return resampled.astype(
            np.float32
        )

    # ======================================================
    # RECORD AUDIO
    # ======================================================

    def record(
        self,
        duration: float = 5.0,
    ) -> np.ndarray:

        if sd is None:

            raise RuntimeError(
                "sounddevice is not installed."
            )

        print()
        print("🎙️ Get ready...")

        time.sleep(
            self.LEAD_IN_SECONDS
        )

        print("Speak now...")
        print()

        try:

            audio = sd.rec(
                int(
                    duration
                    * self.sample_rate
                ),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                device=self.input_device,
            )

            sd.wait()

        except Exception as error:

            raise RuntimeError(
                f"Microphone recording failed: {error}"
            )

        print("Recording finished.")

        audio = audio.flatten()

        # --------------------------------------------------
        # Check microphone level
        # --------------------------------------------------

        peak = (
            float(np.abs(audio).max())
            if len(audio)
            else 0.0
        )

        rms = (
            float(np.sqrt(np.mean(audio ** 2)))
            if len(audio)
            else 0.0
        )

        print(
            f"Peak amplitude: {peak:.4f}"
        )

        print(
            f"RMS level     : {rms:.4f}"
        )

        if peak < self.MIN_PEAK_AMPLITUDE:

            print()
            print(
                "⚠️ Microphone signal is very low."
            )

            print(
                "Check Windows microphone volume "
                "and input permissions."
            )

            print()

        return audio

    # ======================================================
    # SAVE WAV
    # ======================================================

    def _save_wav(
        self,
        audio: np.ndarray,
    ) -> str:

        descriptor, file_path = tempfile.mkstemp(prefix="indu_recording_", suffix=".wav")
        os.close(descriptor)

        audio_int16 = np.int16(
            np.clip(
                audio,
                -1.0,
                1.0,
            )
            * 32767
        )

        with wave.open(
            file_path,
            "wb",
        ) as wav:

            wav.setnchannels(
                self.CHANNELS
            )

            wav.setsampwidth(2)

            wav.setframerate(
                self.WHISPER_SAMPLE_RATE
            )

            wav.writeframes(
                audio_int16.tobytes()
            )

        return file_path

    # ======================================================
    # TRANSCRIBE
    # ======================================================

    def transcribe(
        self,
        audio_file: str,
    ) -> tuple[str, str]:

        print()
        print(
            "🧠 Understanding your voice..."
        )

        try:

            segments, info = (
                self.model.transcribe(
                    audio_file,

                    beam_size=self.BEAM_SIZE,

                    # VAD disabled because your current
                    # ONNX Runtime installation has a
                    # Windows DLL loading problem.
                    vad_filter=False,

                    condition_on_previous_text=False,

                    temperature=0.0,

                    no_speech_threshold=0.6,

                    # None enables automatic English/Telugu/Hindi detection.
                    language=self.language,
                )
            )

            text_parts = []

            for segment in segments:

                text = segment.text.strip()

                if text:

                    text_parts.append(
                        text
                    )

            text = " ".join(
                text_parts
            ).strip()

            language = (
                info.language
                if info.language
                else "unknown"
            )

            print()
            print("----------------------------------------")
            print(
                f"Detected language : {language}"
            )
            print(
                f"You said          : {text!r}"
            )
            print("----------------------------------------")
            print()

            if not text:

                print(
                    "⚠️ No speech was recognized."
                )

                print(
                    "Try speaking slightly louder "
                    "and closer to the microphone."
                )

                print()

            return text, language

        except Exception as error:

            print()
            print(
                f"❌ Whisper transcription error: {error}"
            )
            print()

            raise RuntimeError("Whisper transcription failed") from error

    # ======================================================
    # RECORD + RESAMPLE + TRANSCRIBE
    # ======================================================

    def listen(
        self,
        duration: float = 5.0,
    ) -> tuple[str, str]:

        # --------------------------------------------------
        # 1. Record at microphone's native 48 kHz
        # --------------------------------------------------

        audio = self.record(
            duration=duration
        )

        # --------------------------------------------------
        # 2. Resample 48 kHz → 16 kHz
        # --------------------------------------------------

        print()
        print(
            "🔄 Converting audio: "
            "48000 Hz → 16000 Hz"
        )

        audio_16k = (
            self._resample_to_whisper_rate(
                audio
            )
        )

        print(
            f"Whisper samples: "
            f"{len(audio_16k)}"
        )

        # --------------------------------------------------
        # 3. Save 16 kHz WAV
        # --------------------------------------------------

        file_path = self._save_wav(
            audio_16k
        )

        try:

            # ------------------------------------------------
            # 4. Whisper transcription
            # ------------------------------------------------

            return self.transcribe(
                file_path
            )

        finally:

            try:

                Path(file_path).unlink(
                    missing_ok=True
                )

            except Exception:

                pass


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("       INDU STT DIRECT TEST")
    print("========================================")

    indu = InduSpeechToText(
        model_size="base",
        input_device=None,
    )

    result = indu.listen(
        duration=5.0
    )

    print()
    print("FINAL RESULT")
    print("----------------------------------------")
    print(result)
    print("----------------------------------------")
