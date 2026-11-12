"""
INDU WAKE WORD ENGINE
=====================

Wake phrase detection for Indu.

Primary wake phrase:
    Hey Indu

Accepted pronunciation/transcription variations:
    Hey Indu
    Hey Hindu
    Hey Hendo
    Hey Hando
    Hi Indu
    Hi Hindu
    Hello Indu
    Hello Hindu

Important:
    No fuzzy matching is used.

This prevents phrases such as:
    "Hey no"
    "Hey man"
    "Hey bro"

from accidentally activating Indu.
"""

import re
import time

if __package__ and "." in __package__:
    from .stt import InduSpeechToText
else:
    from voice.stt import InduSpeechToText


class InduWakeWord:

    # ======================================================
    # SETTINGS
    # ======================================================

    LISTEN_DURATION = 3.0

    COOLDOWN_SECONDS = 2.0

    # ======================================================
    # VALID WAKE PHRASES
    # ======================================================

    WAKE_PHRASES = {
        "hey indu",
        "hey hindu",
        "hey hendo",
        "hey hando",

        "hi indu",
        "hi hindu",

        "hello indu",
        "hello hindu",
    }

    # ======================================================
    # TRANSCRIPTION VARIATIONS
    # ======================================================

    INDU_VARIATIONS = {
        "indu",
        "hindu",
        "hendo",
        "hando",
    }

    WAKE_WORDS = {
        "hey",
        "hi",
        "hello",
    }

    def __init__(self, stt=None):

        print()
        print("========================================")
        print("          INDU WAKE WORD ENGINE")
        print("========================================")
        print()

        # IMPORTANT:
        # This uses your confirmed working microphone:
        #
        # Device 9
        # 48 kHz microphone
        # Converted internally to 16 kHz for Whisper

        self.stt = stt or InduSpeechToText(
            model_size="base",
            input_device=None,
            sample_rate=48000,
        )

        self.last_activation_time = 0.0

    # ======================================================
    # NORMALIZE TEXT
    # ======================================================

    @staticmethod
    def normalize(text: str) -> str:

        if not text:
            return ""

        text = text.lower().strip()

        # Remove punctuation.
        text = re.sub(
            r"[^\w\s]",
            " ",
            text,
        )

        # Remove repeated whitespace.
        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    # ======================================================
    # CHECK WAKE PHRASE
    # ======================================================

    def is_wake_word(
        self,
        text: str,
    ) -> bool:

        normalized = self.normalize(text)

        if not normalized:
            return False

        # --------------------------------------------------
        # Exact phrase
        # --------------------------------------------------

        if normalized in self.WAKE_PHRASES:
            return True

        words = normalized.split()

        # --------------------------------------------------
        # Controlled two-word recognition
        #
        # Example:
        # hey indu
        # hey hindu
        # hey hendo
        # hey hando
        # --------------------------------------------------

        if len(words) == 2:

            first = words[0]
            second = words[1]

            if (
                first in self.WAKE_WORDS
                and second in self.INDU_VARIATIONS
            ):
                return True

        # --------------------------------------------------
        # Wake phrase at beginning of longer transcription
        #
        # Example:
        # "Hey Indu please listen"
        #
        # We only examine the FIRST TWO words.
        # --------------------------------------------------

        if len(words) >= 2:

            first = words[0]
            second = words[1]

            if (
                first in self.WAKE_WORDS
                and second in self.INDU_VARIATIONS
            ):
                return True

        return False

    # ======================================================
    # WAIT FOR WAKE WORD
    # ======================================================

    def wait_for_wake_word(self):

        print()
        print("👂 INDU IS LISTENING")
        print("----------------------------------------")
        print("Say: Hey Indu")
        print("----------------------------------------")
        print()

        while True:

            try:

                text, language = self.stt.listen(
                    duration=self.LISTEN_DURATION
                )

                print(
                    f"Wake check: {text!r}"
                )

                # --------------------------------------------------
                # Ignore empty transcription
                # --------------------------------------------------

                if not text:
                    continue

                # --------------------------------------------------
                # Cooldown
                # --------------------------------------------------

                current_time = time.monotonic()

                if (
                    current_time
                    - self.last_activation_time
                    < self.COOLDOWN_SECONDS
                ):
                    continue

                # --------------------------------------------------
                # Check wake phrase
                # --------------------------------------------------

                if self.is_wake_word(text):

                    self.last_activation_time = (
                        current_time
                    )

                    print()
                    print("✨✨✨ WAKE WORD DETECTED ✨✨✨")
                    print(
                        f"Recognized: {text}"
                    )
                    print()

                    return True

                # --------------------------------------------------
                # Not wake word
                # --------------------------------------------------

                print(
                    "❌ Not a wake phrase."
                )
                print()

            except KeyboardInterrupt:

                print()
                print("----------------------------------------")
                print("Wake-word listener stopped.")
                print("----------------------------------------")

                return False

            except Exception as error:

                print()
                print(
                    f"⚠️ Wake-word error: {error}"
                )
                print()

                # Prevent rapid error loops.
                time.sleep(1)


# ==========================================================
# DIRECT TEST
# ==========================================================

if __name__ == "__main__":

    indu = InduWakeWord()

    while True:

        detected = indu.wait_for_wake_word()

        if detected:

            print()
            print("🎉 INDU ACTIVATED!")
            print("Wake-word system is working.")
            print()

            break
