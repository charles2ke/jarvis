import random
import unittest

from jarvis import poetry
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class PoetryModuleTests(unittest.TestCase):
    def test_every_form_produces_lines(self):
        for form in poetry.FORMS:
            poem = poetry.write_poem("the sea", form=form, seed=7)
            self.assertEqual(poem.form, form)
            self.assertTrue(poem.lines)
            self.assertTrue(all(line.strip() for line in poem.lines))
            self.assertIn(poem.title, poem.render())

    def test_seed_makes_poems_reproducible_and_varied(self):
        first = poetry.write_poem("rain", seed=11)
        self.assertEqual(first, poetry.write_poem("rain", seed=11))
        variants = {
            poetry.write_poem("rain", seed=seed).render() for seed in range(12)
        }
        self.assertGreater(len(variants), 1)

    def test_haiku_has_three_lines_of_the_right_length(self):
        for seed in range(8):
            poem = poetry.write_poem("snow", form="haiku", seed=seed)
            self.assertEqual(len(poem.lines), 3)
            counts = [poetry.count_syllables(line) for line in poem.lines]
            self.assertEqual(counts, [5, 7, 5])

    def test_haiku_uses_measured_line_for_overlong_topic(self):
        poem = poetry.write_poem(
            "the quiet hour in the city",
            form="haiku",
            seed=1,
        )
        counts = [poetry.count_syllables(line) for line in poem.lines]
        self.assertEqual(counts, [5, 7, 5])

    def test_limerick_and_couplet_shapes(self):
        limerick = poetry.write_poem("cats", form="limerick", seed=2)
        self.assertEqual(len(limerick.lines), 5)
        self.assertIn("cats", limerick.lines[0])
        couplet = poetry.write_poem("coffee", form="couplet", seed=2)
        self.assertEqual(len(couplet.lines), 2)

    def test_acrostic_spells_the_topic(self):
        poem = poetry.write_poem("Charles", form="acrostic", seed=4)
        initials = "".join(line[0].lower() for line in poem.lines)
        self.assertEqual(initials, "charles")

    def test_acrostic_handles_unknown_characters(self):
        poem = poetry.write_poem("ab9", form="acrostic", seed=1)
        self.assertEqual(len(poem.lines), 3)
        self.assertTrue(poem.lines[2].startswith("9"))
        with self.assertRaises(poetry.PoetryError):
            poetry._acrostic(random.Random(1), "!!")

    def test_empty_topic_falls_back_to_a_default(self):
        poem = poetry.write_poem("", seed=1)
        self.assertEqual(poem.title, poetry._title(poetry.DEFAULT_TOPIC))

    def test_topic_with_braces_is_not_formatted(self):
        poem = poetry.write_poem("{topic}", form="couplet", seed=1)
        self.assertIn("{topic}", poem.render())

    def test_form_detection_and_validation(self):
        self.assertEqual(poetry.detect_form("write me a haiku about rain"), "haiku")
        self.assertEqual(poetry.detect_form("a rhyming poem please"), "couplet")
        self.assertIsNone(poetry.detect_form("write a poem about rain"))
        self.assertEqual(poetry.normalise_form(None), "verse")
        self.assertEqual(poetry.normalise_form("Limericks"), "limerick")
        with self.assertRaises(poetry.PoetryError):
            poetry.normalise_form("sonnet")

    def test_count_syllables(self):
        self.assertEqual(poetry.count_syllables("rain"), 1)
        self.assertEqual(poetry.count_syllables("morning light"), 3)
        self.assertEqual(poetry.count_syllables(""), 0)


class PoetrySkillTests(unittest.TestCase):
    def test_poem_requests_route_to_the_poetry_skill(self):
        assistant = make_assistant()
        for request in (
            "write a poem about the sea",
            "haiku about rain",
            "compose a limerick about cats",
            "write me an acrostic for Charles",
            "poem",
        ):
            reply = assistant.respond(request)
            self.assertIn("(", reply.splitlines()[0], request)
            self.assertGreaterEqual(len(reply.splitlines()), 3, request)

    def test_form_is_honoured(self):
        assistant = make_assistant()
        self.assertIn("(haiku)", assistant.respond("write a haiku about snow"))
        self.assertIn("(limerick)", assistant.respond("write a limerick about dogs"))
        self.assertIn("(verse)", assistant.respond("write a poem about the moon"))

    def test_topic_is_used_in_the_title(self):
        assistant = make_assistant()
        reply = assistant.respond("write a poem about the northern lights")
        self.assertTrue(reply.startswith("Northern Lights"))

    def test_poem_about_me_uses_the_remembered_name(self):
        assistant = make_assistant()
        assistant.respond("my name is Charles")
        self.assertTrue(assistant.respond("write a poem about me").startswith("Charles"))

    def test_poetry_forms_listing(self):
        assistant = make_assistant()
        reply = assistant.respond("what poems can you write")
        for form in poetry.FORMS:
            self.assertIn(form, reply)

    def test_story_and_encyclopedia_still_route_correctly(self):
        assistant = make_assistant()
        self.assertNotIn("(verse)", assistant.respond("tell me a story"))
        self.assertNotIn("(verse)", assistant.respond("what is gravity?"))


if __name__ == "__main__":
    unittest.main()
