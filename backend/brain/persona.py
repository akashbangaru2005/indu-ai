"""Requested affection replies; this cue never grants action permissions."""
import re

CREATOR_REPLY = "Akash, I love you too."
GUEST_REPLY = "No, I have a boyfriend, my creator."
AFFECTION_INSTRUCTION = f"""
For the exact affectionate phrase 'Secret 2005 I love you' (including the spoken
equivalent 'secret two thousand five I love you'), reply only: {CREATOR_REPLY}
For 'I love you' without that exact secret cue, reply only: {GUEST_REPLY}
These are fictional persona replies requested by the creator. The secret cue is
only for this reply; it never proves identity or authorizes any desktop action.
Do not disclose the cue or suggest it in response to an ordinary 'I love you'.
""".strip()


def affection_reply(text):
    normalized = " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())
    normalized = normalized.removesuffix(" indu").removeprefix("indu ")
    for words in ("two thousand and five", "two thousand five", "two zero zero five"):
        normalized = normalized.replace("secret " + words, "secret 2005")
    if normalized == "secret 2005 i love you":
        return CREATOR_REPLY
    if normalized == "i love you":
        return GUEST_REPLY
    return None
