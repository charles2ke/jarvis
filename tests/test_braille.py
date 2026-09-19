import unittest

from jarvis import Assistant
from jarvis.braille import BrailleError, dots_for, read_braille, write_braille


class BrailleModuleTests(unittest.TestCase):
    def test_write_letters(self) -> None:
        self.assertEqual(write_braille("hello"), "⠓⠑⠇⠇⠕")

    def test_read_letters(self) -> None:
        self.assertEqual(read_braille("⠓⠑⠇⠇⠕"), "hello")

    def test_capital_sign_round_trip(self) -> None:
        cells = write_braille("Hi")
        self.assertTrue(cells.startswith("⠠"))
        self.assertEqual(read_braille(cells), "Hi")

    def test_numbers_use_the_number_sign(self) -> None:
        cells = write_braille("42")
        self.assertEqual(cells, "⠼⠙⠃")
        self.assertEqual(read_braille(cells), "42")

    def test_spaces_and_punctuation_round_trip(self) -> None:
        text = "hello, world!"
        self.assertEqual(read_braille(write_braille(text)), text)

    def test_number_mode_ends_at_a_space(self) -> None:
        self.assertEqual(read_braille(write_braille("7 cats")), "7 cats")

    def test_unknown_character_is_reported(self) -> None:
        with self.assertRaises(BrailleError):
            write_braille("caf\u00e9")

    def test_reading_plain_text_is_rejected(self) -> None:
        with self.assertRaises(BrailleError):
            read_braille("hello")

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaises(BrailleError):
            write_braille("   ")
        with self.assertRaises(BrailleError):
            read_braille("")

    def test_dots_for_cell(self) -> None:
        self.assertEqual(dots_for("⠓"), (1, 2, 5))
        with self.assertRaises(BrailleError):
            dots_for("h")


class BrailleSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant()

    def test_read_braille_request(self) -> None:
        reply = self.assistant.respond("read braille ⠓⠑⠇⠇⠕")
        self.assertIn("hello", reply)

    def test_bare_braille_is_read(self) -> None:
        self.assertIn("hi", self.assistant.respond("⠓⠊"))

    def test_write_request(self) -> None:
        reply = self.assistant.respond("write hello in braille")
        self.assertIn("⠓⠑⠇⠇⠕", reply)

    def test_help_when_nothing_to_translate(self) -> None:
        self.assertIn("Grade 1 braille", self.assistant.respond("read brail"))

    def test_alphabet_chart(self) -> None:
        reply = self.assistant.respond("braille alphabet")
        self.assertIn("a ⠁", reply)

    def test_unsupported_character_is_explained(self) -> None:
        reply = self.assistant.respond("write caf\u00e9 in braille")
        self.assertIn("braille cell", reply)

    def test_other_skills_still_win(self) -> None:
        self.assertIn("42", self.assistant.respond("calculate 21 * 2"))
        self.assertIn("Gravity", self.assistant.respond("what is gravity?"))


if __name__ == "__main__":
    unittest.main()
