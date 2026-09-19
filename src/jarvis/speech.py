"""Text to speech support for Jarvis.

Jarvis stays dependency free, so speech is produced by whichever text to
speech program the operating system already provides (``say`` on macOS,
``espeak-ng``/``espeak``/``spd-say`` on Linux and PowerShell's speech
synthesiser on Windows).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

DEFAULT_TIMEOUT = 60.0

_POWERSHELL_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak([Console]::In.ReadToEnd())"
)


class SpeechError(RuntimeError):
    """Raised when text could not be spoken aloud."""


@dataclass(frozen=True)
class Voice:
    """A text to speech program available on this machine."""

    name: str
    command: Sequence[str]
    text_as_argument: bool = True

    def arguments(self, text: str) -> List[str]:
        args = list(self.command)
        if self.text_as_argument:
            args.append(text)
        return args


VOICES: tuple[Voice, ...] = (
    Voice("say", ("say",)),
    Voice("espeak-ng", ("espeak-ng",)),
    Voice("espeak", ("espeak",)),
    Voice("spd-say", ("spd-say", "--wait")),
    Voice(
        "powershell",
        ("powershell", "-NoProfile", "-Command", _POWERSHELL_SCRIPT),
        text_as_argument=False,
    ),
)


def available_voice(
    which: Callable[[str], Optional[str]] = shutil.which
) -> Optional[Voice]:
    """Return the first text to speech program installed on this machine."""

    preferred = os.environ.get("JARVIS_TTS_COMMAND", "").strip()
    if preferred:
        return Voice("custom", tuple(shlex.split(preferred)))
    for voice in VOICES:
        if which(voice.command[0]):
            return voice
    return None


def speak(text: str, *, timeout: float = DEFAULT_TIMEOUT) -> Voice:
    """Read ``text`` aloud and return the voice that was used.

    Raises :class:`SpeechError` when there is nothing to say or when no text
    to speech program is available.
    """

    words = (text or "").strip()
    if not words:
        raise SpeechError("Tell me what you would like me to say out loud.")

    voice = available_voice()
    if voice is None:
        raise SpeechError(
            "I could not find a text to speech program. Install one of: "
            + ", ".join(entry.command[0] for entry in VOICES)
            + ", or set JARVIS_TTS_COMMAND to the command I should use."
        )

    try:
        subprocess.run(
            voice.arguments(words),
            input=None if voice.text_as_argument else words,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise SpeechError(f"'{voice.name}' took too long to speak.") from exc
    except subprocess.CalledProcessError as exc:
        raise SpeechError(f"'{voice.name}' could not speak that text.") from exc
    except OSError as exc:
        raise SpeechError(f"I could not run '{voice.name}': {exc}") from exc
    return voice
