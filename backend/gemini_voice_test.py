"""Manual Gemini microphone smoke test; shares the maintained demo implementation."""
import asyncio
from contextlib import suppress

if __package__:
    from .gemini_live import InduGeminiLive
else:
    from gemini_live import InduGeminiLive

if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(InduGeminiLive().run())
