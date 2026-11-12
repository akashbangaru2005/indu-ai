"""
INDU VOICE ASSISTANT LOOP
=========================

Flow:

    Hey Indu
        ↓
    Wake detected
        ↓
    Indu acknowledges
        ↓
    Listen to question
        ↓
    Gemini
        ↓
    Edge TTS
        ↓
    Speak response
        ↓
    Listen for Hey Indu again
"""

import time

if __package__ and "." in __package__:
    from .stt import InduSpeechToText
    from .tts import InduTextToSpeech
    from .wake_word import InduWakeWord
    from ..brain.llm import InduBrain
else:
    from voice.stt import InduSpeechToText
    from voice.tts import InduTextToSpeech
    from voice.wake_word import InduWakeWord
    from brain.llm import InduBrain


class InduVoiceAssistant:

    def __init__(self):

        print()
        print("========================================")
        print("       INDU VOICE ASSISTANT")
        print("========================================")
        print()

        # ==================================================
        # AI BRAIN
        # ==================================================

        print("🧠 Initializing Indu Brain...")

        self.brain = InduBrain()

        print("✅ Brain ready.")
        print()

        # ==================================================
        # TEXT TO SPEECH
        # ==================================================

        print("🔊 Initializing Indu voice...")

        self.tts = InduTextToSpeech()

        print("✅ Voice ready.")
        print()

        # ==================================================
        # WAKE WORD ENGINE
        # ==================================================

        print("✨ Initializing wake-word engine...")

        self.question_stt = InduSpeechToText(model_size="base")
        self.wake_word = InduWakeWord(stt=self.question_stt)

        print("✅ Wake-word engine ready.")
        print()

        # ==================================================
        # QUESTION LISTENER
        # ==================================================

        print("🎙️ Initializing question listener...")

        # Wake detection and questions share one Whisper model.

        print("✅ Question listener ready.")
        print()

        print("========================================")
        print("          INDU IS READY")
        print("========================================")
        print()

    # ======================================================
    # SPEAK
    # ======================================================

    def speak(self, text: str):

        if not text:
            return

        print()
        print("🔊 INDU:")
        print(text)
        print()

        self.tts.speak(
            text
        )

    # ======================================================
    # LISTEN FOR QUESTION
    # ======================================================

    def listen_for_question(self):

        print()
        print("----------------------------------------")
        print("🎙️ INDU IS LISTENING TO YOUR QUESTION")
        print("----------------------------------------")
        print()

        text, language = self.question_stt.listen(
            duration=7.0
        )

        if not text:
            print(
                "⚠️ No question detected."
            )

            return None

        print()
        print(
            f"📝 Question: {text}"
        )
        print(
            f"🌐 Language: {language}"
        )
        print()

        return text

    # ======================================================
    # THINK
    # ======================================================

    def think(self, question: str):

        print()
        print("----------------------------------------")
        print("🧠 INDU IS THINKING")
        print("----------------------------------------")
        print()

        try:

            response = self.brain.chat(
                question
            )

            return response

        except Exception as error:

            print(
                f"❌ Brain error: {error}"
            )

            return (
                "I'm sorry, I couldn't process "
                "that request."
            )

    # ======================================================
    # ONE CONVERSATION
    # ======================================================

    def handle_conversation(self):

        # --------------------------------------------------
        # Wake acknowledged
        # --------------------------------------------------

        self.speak(
            "Yes, I'm listening."
        )

        # --------------------------------------------------
        # Listen
        # --------------------------------------------------

        question = self.listen_for_question()

        if not question:

            self.speak(
                "I didn't hear your question."
            )

            return

        # --------------------------------------------------
        # Think
        # --------------------------------------------------

        response = self.think(
            question
        )

        if not response:

            self.speak(
                "I couldn't generate a response."
            )

            return

        # --------------------------------------------------
        # Speak
        # --------------------------------------------------

        self.speak(
            response
        )

        # Small pause before returning to wake mode.
        time.sleep(0.5)

    # ======================================================
    # MAIN LOOP
    # ======================================================

    def run(self):

        print()
        print("🚀 INDU VOICE MODE STARTED")
        print()

        while True:

            try:

                # ------------------------------------------
                # Wait for "Hey Indu"
                # ------------------------------------------

                detected = (
                    self.wake_word
                    .wait_for_wake_word()
                )

                if not detected:

                    print(
                        "Wake-word system stopped."
                    )

                    break

                # ------------------------------------------
                # Handle conversation
                # ------------------------------------------

                self.handle_conversation()

                print()
                print("----------------------------------------")
                print("👂 Returning to wake-word mode...")
                print("----------------------------------------")
                print()

            except KeyboardInterrupt:

                print()
                print("========================================")
                print("      INDU VOICE MODE STOPPED")
                print("========================================")
                print()

                break

            except Exception as error:

                print()
                print(
                    f"⚠️ Assistant loop error: {error}"
                )

                print(
                    "Restarting wake-word mode..."
                )

                time.sleep(2)


# ==========================================================
# START INDU
# ==========================================================

if __name__ == "__main__":

    assistant = InduVoiceAssistant()

    assistant.run()
