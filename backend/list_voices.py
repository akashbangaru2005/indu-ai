import pyttsx3


engine = pyttsx3.init()

voices = engine.getProperty("voices")

print()
print("========================================")
print("        INDU AVAILABLE VOICES")
print("========================================")
print()

for index, voice in enumerate(voices):

    print(f"VOICE {index}")
    print(f"Name   : {voice.name}")
    print(f"ID     : {voice.id}")
    print(f"Gender : {getattr(voice, 'gender', 'Unknown')}")
    print("-" * 40)

engine.stop()