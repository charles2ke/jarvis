import unittest

from jarvis import encyclopedia
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class EncyclopediaLookupTests(unittest.TestCase):
    def test_lookup_is_case_and_punctuation_insensitive(self):
        article = encyclopedia.lookup("  gRaViTy!  ")
        self.assertIsNotNone(article)
        self.assertEqual(article.title, "Gravity")

    def test_lookup_resolves_aliases_and_leading_article(self):
        self.assertEqual(encyclopedia.lookup("AI").title, "Artificial intelligence")
        self.assertEqual(encyclopedia.lookup("the moon").title, "The Moon")
        self.assertEqual(encyclopedia.lookup("Moon").title, "The Moon")

    def test_lookup_tolerates_small_typos(self):
        self.assertEqual(encyclopedia.lookup("einstien").title, "Albert Einstein")

    def test_lookup_rejects_unknown_and_empty_queries(self):
        self.assertIsNone(encyclopedia.lookup("quantum tunnelling"))
        self.assertIsNone(encyclopedia.lookup("   "))

    def test_topics_are_sorted_and_unique(self):
        titles = encyclopedia.topics()
        self.assertEqual(titles, sorted(titles))
        self.assertEqual(len(titles), len(set(titles)))

    def test_suggestions_offer_close_titles(self):
        self.assertIn("Machine learning", encyclopedia.suggestions("machine lerning"))
        self.assertEqual(encyclopedia.suggestions(""), [])


class EncyclopediaSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_question_forms_return_the_article(self):
        for message in (
            "what is gravity?",
            "What's gravity",
            "tell me about gravity",
            "define gravity",
            "explain gravity.",
            "look up gravity",
            "encyclopedia: gravity",
        ):
            with self.subTest(message=message):
                reply = self.assistant.respond(message)
                self.assertTrue(reply.startswith("Gravity:"), reply)

    def test_who_questions_return_people(self):
        reply = self.assistant.respond("who was Alan Turing?")
        self.assertIn("Bletchley Park", reply)

    def test_unknown_topic_is_reported_with_suggestions(self):
        reply = self.assistant.respond("what is machine lerning")
        self.assertIn("Machine learning", reply)

    def test_unknown_topic_without_close_match_points_to_topics(self):
        reply = self.assistant.respond("what is the airspeed velocity of a swallow")
        self.assertIn("do not have an encyclopedia entry", reply)

    def test_topics_listing(self):
        reply = self.assistant.respond("encyclopedia topics")
        self.assertIn("Ada Lovelace", reply)
        self.assertIn("encyclopedia entries", reply)

    def test_encyclopedia_does_not_shadow_other_skills(self):
        self.assertEqual(self.assistant.respond("what is the time?")[:5], "It is")
        self.assertIn("September", self.assistant.respond("what is today's date?"))
        self.assertEqual(self.assistant.respond("what is 21 * 2"), "21 * 2 = 42")
        self.assertIn("do not know your name", self.assistant.respond("what is my name?"))
        self.assertIn("Here is what I can do", self.assistant.respond("what can you do"))


if __name__ == "__main__":
    unittest.main()
