import io
import unittest
from unittest import mock

from jarvis.style import Style, color_enabled, strip_ansi


class FakeStream(io.StringIO):
    def __init__(self, tty: bool, encoding: str = "utf-8") -> None:
        super().__init__()
        self._tty = tty
        self._encoding = encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return self._encoding


class ColorEnabledTests(unittest.TestCase):
    def test_precedence(self):
        tty, pipe = FakeStream(True), FakeStream(False)
        cases = [
            (tty, "auto", {}, True),
            (pipe, "auto", {}, False),
            (tty, "auto", {"NO_COLOR": "1"}, False),
            (tty, "auto", {"NO_COLOR": ""}, True),
            (pipe, "auto", {"FORCE_COLOR": "1"}, True),
            (pipe, "auto", {"FORCE_COLOR": "0"}, False),
            (pipe, "auto", {"NO_COLOR": "1", "FORCE_COLOR": "1"}, False),
            (tty, "auto", {"TERM": "dumb"}, False),
            (pipe, "always", {"NO_COLOR": "1"}, True),
            (tty, "never", {"FORCE_COLOR": "1"}, False),
        ]
        for stream, mode, env, expected in cases:
            with self.subTest(tty=stream.isatty(), mode=mode, env=env):
                self.assertIs(color_enabled(stream, mode, env), expected)

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            color_enabled(FakeStream(True), "sometimes", {})


class StyleTests(unittest.TestCase):
    SKILL_LIST = "Skills that match 'calc':\n- calculator: Evaluate sums.\n    e.g. calculate 21 * 2"

    def test_disabled_style_leaves_text_untouched(self):
        style = Style(enabled=False)
        self.assertEqual(style.prompt(), "you> ")
        self.assertEqual(style.reply(self.SKILL_LIST), "jarvis> " + self.SKILL_LIST)
        self.assertEqual(style.greeting("Type 'help'."), "Type 'help'.")
        self.assertEqual(style.banner("1.0"), "")

    def test_highlight_only_adds_colour(self):
        lines = Style(enabled=True).highlight(self.SKILL_LIST).split("\n")
        self.assertEqual(strip_ansi("\n".join(lines)), self.SKILL_LIST)
        self.assertNotIn("\x1b[", lines[0])
        self.assertIn("\x1b[1;35mcalculator\x1b[0m", lines[1])
        self.assertTrue(lines[2].startswith("    \x1b[2me.g."))

    def test_prompt_marks_escapes_for_readline(self):
        style = Style(enabled=True)
        with mock.patch.dict("sys.modules", {"readline": mock.Mock()}):
            prompt = style.prompt()
        self.assertEqual(prompt.replace("\001", "").replace("\002", ""), "\x1b[1;32myou>\x1b[0m ")
        self.assertEqual(prompt.count("\001"), 2)

    def test_banner_falls_back_to_ascii(self):
        style = Style.for_stream(FakeStream(False, encoding="ascii"), "always", {})
        self.assertEqual(strip_ansi(style.banner("1.2.3")), "* Jarvis v1.2.3 - your personal AI companion")


if __name__ == "__main__":
    unittest.main()
