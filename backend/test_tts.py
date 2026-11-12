"""
INDU TTS TEST
=============
Tests Indu's text-to-speech engine.
"""

if __package__:
    from .voice.tts import InduTextToSpeech
else:
    from voice.tts import InduTextToSpeech


def main():

    print()
    print("========================================")
    print("            INDU VOICE TEST")
    print("========================================")
    print()

    tts = InduTextToSpeech(
        rate=175,
        volume=1.0,
    )

    message = (
        "Hello Akhi. "
        "I am Indu, your personal AI assistant."
    )

    print("Indu is speaking...")
    print()
    print(f"Message: {message}")
    print()

    tts.speak(message)

    print()
    print("Speech completed.")
    print()


if __name__ == "__main__":
    main()
