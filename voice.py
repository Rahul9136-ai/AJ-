"""
Voice helpers — speech-to-text (input) and text-to-speech (output).

All functions degrade gracefully: if a library or microphone is missing, they
return a human-readable error string instead of crashing, so the rest of the app
keeps working in text mode.

- Transcription uses SpeechRecognition's free Google recognizer (needs internet,
  no API key).
- Speech output uses pyttsx3 (offline, uses the OS voice — Windows SAPI5).
"""

from __future__ import annotations

import io
from typing import Optional, Tuple


def transcribe(audio_bytes: bytes) -> Tuple[str, Optional[str]]:
    """Transcribe WAV audio bytes (e.g. from st.audio_input). Returns (text, error)."""
    try:
        import speech_recognition as sr
    except ImportError:
        return "", "Install voice deps: pip install SpeechRecognition"

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = recognizer.record(source)
    except Exception as exc:  # malformed/empty audio
        return "", f"Couldn't read the recording: {exc}"

    try:
        return recognizer.recognize_google(audio), None
    except sr.UnknownValueError:
        return "", "Didn't catch that — please try again."
    except sr.RequestError as exc:
        return "", f"Speech service unavailable (needs internet): {exc}"


def listen_from_mic(timeout: int = 8, phrase_time_limit: int = 20) -> Tuple[str, Optional[str]]:
    """Record from the default microphone and transcribe. Returns (text, error).

    Needs PyAudio (`pip install pyaudio`) for live mic capture.
    """
    try:
        import speech_recognition as sr
    except ImportError:
        return "", "Install voice deps: pip install SpeechRecognition pyaudio"

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    except AttributeError:
        return "", "Microphone support needs PyAudio: pip install pyaudio"
    except OSError as exc:
        return "", f"No microphone available: {exc}"
    except Exception as exc:  # e.g. listen timeout
        return "", f"No speech detected: {exc}"

    try:
        return recognizer.recognize_google(audio), None
    except sr.UnknownValueError:
        return "", "Didn't catch that — please try again."
    except sr.RequestError as exc:
        return "", f"Speech service unavailable (needs internet): {exc}"


# Names that indicate a female OS voice (Windows SAPI5 / macOS / Linux espeak).
_FEMALE_HINTS = ("zira", "female", "hazel", "eva", "susan", "samantha", "aria", "jenny", "michelle")


def speak(text: str) -> Optional[str]:
    """Speak text aloud through the OS voice, preferring a soft female voice."""
    try:
        import pyttsx3
    except ImportError:
        return "Install voice output: pip install pyttsx3"
    try:
        engine = pyttsx3.init()

        # Pick a female voice if one is available.
        for v in engine.getProperty("voices"):
            name = (getattr(v, "name", "") or "").lower()
            gender = " ".join(getattr(v, "gender", "") or "").lower() if getattr(v, "gender", None) else ""
            if any(h in name for h in _FEMALE_HINTS) or "female" in gender:
                engine.setProperty("voice", v.id)
                break

        engine.setProperty("rate", 170)   # a little slower = gentler/melodic
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return None
    except Exception as exc:
        return f"Text-to-speech failed: {exc}"
