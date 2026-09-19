import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from jarvis.assistant import Assistant
from jarvis.cli import main
from jarvis.memory import Memory
from jarvis.speech import SpeechError, Voice, available_voice, speak


class SpeechTests(unittest.TestCase):
    def test_available_voice_prefers_environment_command(self):
        with mock.patch.dict("os.environ", {"JARVIS_TTS_COMMAND": "mytts --slow"}):
            voice = available_voice()
        self.assertIsNotNone(voice)
        self.assertEqual(voice.command, ("mytts", "--slow"))

    def test_available_voice_picks_first_installed_program(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            voice = available_voice(which=lambda name: name if name == "espeak" else None)
        self.assertIsNotNone(voice)
        self.assertEqual(voice.name, "espeak")

    def test_available_voice_returns_none_when_nothing_installed(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(available_voice(which=lambda name: None))

    def test_speak_runs_the_voice_command(self):
        voice = Voice("espeak", ("espeak",))
        with mock.patch("jarvis.speech.available_voice", return_value=voice), mock.patch(
            "subprocess.run"
        ) as run:
            self.assertIs(speak("hello there"), voice)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["espeak", "hello there"])

    def test_speak_pipes_text_when_the_voice_reads_stdin(self):
        voice = Voice("powershell", ("powershell", "-Command", "x"), text_as_argument=False)
        with mock.patch("jarvis.speech.available_voice", return_value=voice), mock.patch(
            "subprocess.run"
        ) as run:
            speak("hello there")
        self.assertEqual(run.call_args.args[0], ["powershell", "-Command", "x"])
        self.assertEqual(run.call_args.kwargs["input"], "hello there")

    def test_speak_rejects_empty_text(self):
        with self.assertRaises(SpeechError):
            speak("   ")

    def test_speak_reports_missing_program(self):
        with mock.patch("jarvis.speech.available_voice", return_value=None):
            with self.assertRaises(SpeechError):
                speak("hello")

    def test_speak_reports_failing_program(self):
        import subprocess

        voice = Voice("espeak", ("espeak",))
        with mock.patch("jarvis.speech.available_voice", return_value=voice), mock.patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "espeak")
        ):
            with self.assertRaises(SpeechError):
                speak("hello")


class SpeakSkillTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant(memory=Memory(None))

    def test_speak_skill_reads_text_aloud(self):
        with mock.patch("jarvis.skills.speak") as spoken:
            reply = self.assistant.respond("say out loud hello Charles")
        spoken.assert_called_once_with("hello Charles")
        self.assertIn("hello Charles", reply)

    def test_trailing_out_loud_phrasing(self):
        with mock.patch("jarvis.skills.speak") as spoken:
            self.assistant.respond('read "the report is ready" aloud')
        spoken.assert_called_once_with("the report is ready")

    def test_text_to_speech_prefix(self):
        with mock.patch("jarvis.skills.speak") as spoken:
            self.assistant.respond("text to speech: good morning")
        spoken.assert_called_once_with("good morning")

    def test_speech_failure_is_reported(self):
        with mock.patch("jarvis.skills.speak", side_effect=SpeechError("no voice")):
            reply = self.assistant.respond("say out loud hello")
        self.assertIn("no voice", reply)

    def test_speak_skill_does_not_hijack_other_skills(self):
        with mock.patch("jarvis.skills.speak") as spoken:
            self.assistant.respond("tell me a joke")
            self.assistant.respond("say something funny")
        spoken.assert_not_called()


class SpeakFlagTests(unittest.TestCase):
    def test_one_shot_reply_is_spoken(self):
        buffer = io.StringIO()
        with mock.patch("jarvis.cli.speak") as spoken, redirect_stdout(buffer):
            main(["--no-memory", "--speak", "calculate 21 * 2"])
        spoken.assert_called_once()
        self.assertIn("42", buffer.getvalue())

    def test_speech_failure_does_not_crash_the_cli(self):
        buffer = io.StringIO()
        with mock.patch("jarvis.cli.speak", side_effect=SpeechError("no voice")), redirect_stdout(
            buffer
        ):
            exit_code = main(["--no-memory", "--speak", "calculate 1 + 1"])
        self.assertEqual(exit_code, 0)
        self.assertIn("speech unavailable", buffer.getvalue())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
