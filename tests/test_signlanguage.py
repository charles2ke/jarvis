import unittest

from jarvis import signlanguage
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class SignLanguageDataTests(unittest.TestCase):
    def test_lookup_by_term_alias_and_typo(self):
        self.assertEqual(signlanguage.lookup("thank you").term, "thank you")
        self.assertEqual(signlanguage.lookup("  Thanks ").term, "thank you")
        self.assertEqual(signlanguage.lookup("mom").term, "mother")
        self.assertEqual(signlanguage.lookup("helo").term, "hello")
        self.assertIsNone(signlanguage.lookup(""))
        self.assertIsNone(signlanguage.lookup("photosynthesis"))

    def test_lookup_ignores_trailing_language_filler(self):
        self.assertEqual(signlanguage.lookup("water in ASL").term, "water")
        self.assertEqual(signlanguage.lookup("the water").term, "water")

    def test_alphabet_and_digits_are_complete(self):
        self.assertEqual(len(signlanguage.ALPHABET), 26)
        self.assertEqual(len(signlanguage.DIGITS), 10)
        self.assertEqual(len(signlanguage.alphabet_lines()), 26)
        self.assertIsNotNone(signlanguage.letter("q"))
        self.assertIsNotNone(signlanguage.letter("7"))
        self.assertIsNone(signlanguage.letter("ab"))
        self.assertIsNone(signlanguage.letter("!"))

    def test_fingerspell_words_spaces_and_unknown_characters(self):
        spelled, skipped = signlanguage.fingerspell("Hi 5!")
        self.assertEqual([character for character, _ in spelled], ["H", "I", "␣", "5"])
        self.assertEqual(skipped, ["!"])

        spelled, skipped = signlanguage.fingerspell("  ")
        self.assertEqual(spelled, [])
        self.assertEqual(skipped, [])

    def test_fingerspell_respects_limit(self):
        spelled, skipped = signlanguage.fingerspell("abcdef!", limit=3)
        self.assertEqual(len(spelled), 3)
        self.assertEqual(skipped, ["!"])

    def test_terms_are_sorted_and_resolvable(self):
        names = signlanguage.terms()
        self.assertEqual(names, sorted(names))
        for name in names:
            with self.subTest(term=name):
                self.assertIsNotNone(signlanguage.lookup(name))

    def test_suggestions(self):
        self.assertIn("thank you", signlanguage.suggestions("thank yu"))
        self.assertEqual(signlanguage.suggestions(""), [])


class SignLanguageSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_overview_questions(self):
        for question in (
            "understand sign language",
            "what is sign language?",
            "teach me sign language",
            "explain American Sign Language",
        ):
            with self.subTest(question=question):
                reply = self.assistant.respond(question)
                self.assertIn("American Sign Language", reply)
                self.assertIn("fingerspell", reply)

    def test_sign_lookup_phrasings(self):
        for question in (
            "how do I sign thank you?",
            "what is the sign for thank you",
            "sign for thank you",
            "how do you say thank you in sign language",
        ):
            with self.subTest(question=question):
                self.assertIn("chin", self.assistant.respond(question))

    def test_unknown_sign_suggests_fingerspelling(self):
        reply = self.assistant.respond("how do I sign quantum physics")
        self.assertIn("do not have a sign", reply)
        self.assertIn("fingerspell quantum physics", reply)

    def test_single_letter_request_describes_handshape(self):
        self.assertIn("fingerspelled", self.assistant.respond("what is the sign for q"))

    def test_fingerspelling(self):
        reply = self.assistant.respond("fingerspell Charles")
        self.assertIn("C:", reply)
        self.assertIn("S:", reply)
        self.assertIn("H:", self.assistant.respond("spell hi in ASL"))

    def test_alphabet_and_topics(self):
        alphabet = self.assistant.respond("sign language alphabet")
        self.assertIn("manual alphabet", alphabet)
        self.assertIn("- Z:", alphabet)

        topics = self.assistant.respond("what signs do you know")
        self.assertIn("thank you", topics)

    def test_other_skills_still_win(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertIn("Jarvis", self.assistant.respond("hello"))


if __name__ == "__main__":
    unittest.main()
