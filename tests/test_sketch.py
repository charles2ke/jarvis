import unittest

from jarvis import sketch
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class SketchDataTests(unittest.TestCase):
    def test_lookup_by_subject_alias_and_typo(self):
        self.assertEqual(sketch.lookup("cat").subject, "cat")
        self.assertEqual(sketch.lookup(" A Kitten ").subject, "cat")
        self.assertEqual(sketch.lookup("sailboat").subject, "boat")
        self.assertEqual(sketch.lookup("rockett").subject, "rocket")
        self.assertIsNone(sketch.lookup(""))
        self.assertIsNone(sketch.lookup("photosynthesis"))

    def test_subjects_are_sorted_and_unique(self):
        names = sketch.subjects()
        self.assertEqual(names, sorted(names))
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("rocket", names)

    def test_every_sketch_renders_ascii_lines(self):
        for drawing in sketch.SKETCHES:
            lines = drawing.lines()
            self.assertTrue(lines, drawing.subject)
            self.assertTrue(all(line.strip() for line in lines), drawing.subject)
            rendered = sketch.render(drawing)
            self.assertTrue(rendered.endswith(drawing.caption))

    def test_suggestions_offer_close_subjects(self):
        self.assertIn("house", sketch.suggestions("mouse"))
        self.assertEqual(sketch.suggestions(""), [])


class SketchSkillTests(unittest.TestCase):
    def test_draw_request_returns_the_sketch(self):
        reply = make_assistant().respond("draw a cat")
        self.assertIn("cat sketch", reply)
        self.assertIn("/\\_/\\", reply)

    def test_polite_and_picture_phrasings(self):
        assistant = make_assistant()
        self.assertIn("house sketch", assistant.respond("can you draw me a house?"))
        self.assertIn(
            "robot sketch", assistant.respond("draw me a picture of a robot")
        )
        self.assertIn("moon sketch", assistant.respond("show me a sketch of the moon"))

    def test_unknown_subject_suggests_alternatives(self):
        reply = make_assistant().respond("draw a mouse")
        self.assertIn("cannot sketch", reply)
        self.assertIn("house", reply)

    def test_missing_subject_asks_what_to_draw(self):
        reply = make_assistant().respond("draw")
        self.assertIn("What would you like me to sketch?", reply)

    def test_topics_list_every_subject(self):
        reply = make_assistant().respond("what can you sketch?")
        for name in sketch.subjects():
            self.assertIn(name, reply)


if __name__ == "__main__":
    unittest.main()
