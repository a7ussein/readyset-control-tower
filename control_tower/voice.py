"""Optional: read an answer aloud in a natural voice (ElevenLabs), instead of the browser's built-in voice.

    audio = speak("Not yet. Three changes need review.", key)        # MP3 bytes

Only the words of the answer being read are sent. The key comes from the environment (ELEVENLABS_API_KEY) and is never
written anywhere by this tool. With no key the page uses the browser's own voice and nothing is sent.
"""
import json
import os
import re
import urllib.request

VOICE = os.environ.get("READYSET_VOICE_ID") or "onwK4e9ZLuTAKqWW03F9"        # "Daniel", a steady broadcaster
MODEL = os.environ.get("READYSET_VOICE_MODEL") or "eleven_turbo_v2_5"
LIMIT = 600


def available():
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def spoken(text):
    """The text as it should be said: ids and file names are for the eye, not the ear."""
    text = re.sub(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}(-\d\d)?", "a named sample", str(text or ""))
    text = re.sub(r"\b[\w.-]+\.tsv(\.gz)?\b", "the data file", text)
    text = re.sub(r"\b([FRA])(\d+)\b", lambda m: {"F": "change ", "R": "fix ", "A": "analysis "}[m.group(1)] + m.group(2), text)
    text = re.sub(r"(a named sample(, | and )?){2,}", "the named samples ", text)
    text = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s+", " ", text))
    return text.strip()[:LIMIT]


def speak(text, key=None):
    key = key or os.environ["ELEVENLABS_API_KEY"]
    body = {"text": spoken(text), "model_id": MODEL,
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.0, "use_speaker_boost": True}}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()
