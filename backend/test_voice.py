"""
INDU VOICE TEST
===============

Tests microphone recording and speech recognition.
"""

if __package__:
    from .voice.stt import InduSpeechToText
else:
    from voice.stt import InduSpeechToText


def main():

    print()
    print("========================================")
    print("          INDU VOICE TEST")
    print("========================================")
    print()

    print("Initializing speech recognition...")

    stt = InduSpeechToText(
        model_size="base"
    )

    print()
    print("Press ENTER to start recording.")
    input()

    text, language = stt.listen(
        duration=5
    )

    print()
    print("========================================")
    print("              RESULT")
    print("========================================")
    print()
    print(f"Language : {language}")
    print(f"Text     : {text}")
    print()


if __name__ == "__main__":
    main()
