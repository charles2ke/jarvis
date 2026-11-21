import importlib.util
import re
import sys
import unittest
from pathlib import Path

from jarvis import cancer
from jarvis.cancer import CREDIT, DISCLAIMER, answer
from jarvis.cancer_data import FACTS
from jarvis.dates import MONTH_NAMES

ROOT = Path(__file__).resolve().parent.parent


def _load_importer():
    path = ROOT / "scripts" / "import_beat_it.py"
    spec = importlib.util.spec_from_file_location("import_beat_it", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("import_beat_it", module)
    spec.loader.exec_module(module)
    return module


class CancerLookupTests(unittest.TestCase):
    def test_generic_aliases_need_a_cancer_word(self):
        for text in ("stomach ache", "renal failure", "my eGFR is 60", "HPV vaccine"):
            with self.subTest(text=text):
                self.assertIsNone(answer(text))
        reply = answer("stomach cancer symptoms")
        self.assertTrue(reply.startswith("Common symptoms of stomach (gastric) cancer"))

    def test_specific_names_and_acronyms_need_no_cancer_word(self):
        self.assertIn("leukemia", answer("AML treatments").lower())
        self.assertIn("Skin cancer (melanoma)", answer("what is melanoma?"))
        self.assertTrue(answer("lukemia symptoms").startswith("Common symptoms of leukemia"))

    def test_not_about_cancer_in_people(self):
        for text in (
            "I'm a Cancer",
            "my cancer horoscope for today",
            "the Tropic of Cancer",
            "cancel my order",
            "corruption is a cancer on society",
            "what is AML compliance?",
            "what's the weather like?",
        ):
            with self.subTest(text=text):
                self.assertIsNone(answer(text))

    def test_what_beat_it_does_not_cover_is_not_guessed(self):
        reply = answer("small bowel cancer symptoms")
        self.assertIn("beat-it doesn't have an entry for small bowel cancer", reply)
        self.assertNotIn("Colorectal", reply)
        reply = answer("who discovered chemotherapy?")
        self.assertIn("beat-it's notes don't cover that question", reply)


class CancerReplyTests(unittest.TestCase):
    def test_every_reply_is_short_and_ends_with_disclaimer_and_credit(self):
        for text in (
            "lung cancer",
            "lung cancer medicines",
            "breast cancer screening",
            "is cancer hereditary?",
            "cancer topics",
        ):
            with self.subTest(text=text):
                lines = answer(text).splitlines()
                self.assertEqual(lines[-2:], [DISCLAIMER, CREDIT])
                self.assertLessEqual(len(lines), 15)

    def test_long_lists_are_truncated(self):
        reply = answer("lung cancer medicines")
        self.assertRegex(reply, r"\n- and \d+ more")

    def test_approvals_are_newest_first_and_dated(self):
        reply = answer("recent lung cancer approvals")
        dates = []
        for day, month, year in re.findall(r"^- (\d+) ([A-Z][a-z]+) (\d{4}) — ", reply, re.M):
            dates.append((int(year), MONTH_NAMES.index(month), int(day)))
        self.assertGreaterEqual(len(dates), 3)
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertIn("As listed by beat-it on", reply)

    def test_faqs_and_worldwide_facts(self):
        self.assertTrue(answer("can cancer be prevented?").startswith("Can cancer be prevented?"))
        facts = answer("how common is cancer?")
        for fact in FACTS["facts"]:
            self.assertIn(f"({fact['source']})", facts)

    def test_contagion_is_not_answered_beyond_the_data(self):
        reply = answer("is cancer contagious?")
        self.assertIn("don't say whether cancer itself can pass from person to person", reply)
        self.assertIn("HPV", reply)

    def test_topics_name_every_entry(self):
        listing = cancer.topics()
        for name in cancer.NAMES:
            self.assertIn(name, listing)


class CancerPersonalTests(unittest.TestCase):
    def test_self_checks_are_not_diagnosed(self):
        for text, person in (
            ("do I have cancer?", "you"),
            ("is this lump cancer?", "you"),
            ("does my dad have cancer?", "your dad"),
        ):
            with self.subTest(text=text):
                reply = answer(text)
                self.assertIn("I can't diagnose cancer", reply)
                self.assertIn(f"a doctor who can examine {person} can", reply)
                self.assertIn("urgent care if a symptom is severe or came on suddenly", reply)
                self.assertNotIn("I'm sorry", reply)
                self.assertTrue(reply.endswith(f"{DISCLAIMER}\n{CREDIT}"))

    def test_self_checks_about_a_type_say_when_its_signs_were_reviewed(self):
        reply = answer("I have a lump in my breast, is it cancer?")
        self.assertIn("General warning signs beat-it lists for breast cancer:", reply)
        self.assertRegex(
            reply,
            rf"\n- [^\n]+\nReviewed by beat-it on \d{{1,2}} [A-Z][a-z]+ \d{{4}}\.\n"
            rf"{re.escape(DISCLAIMER)}\n",
        )
        self.assertNotIn("Reviewed by beat-it", answer("do I have cancer?"))

    def test_worried_self_checks_start_with_a_kind_line(self):
        for text, start in (
            ("I'm scared I have cancer", "It's understandable to feel scared.\nI can't diagnose"),
            ("I'm worried my mum has cancer",
             "It's understandable to be worried about your mum.\nI can't diagnose"),
            ("do I have cancer?", "I can't diagnose"),
            ("I'm not worried, but do I have cancer?", "I can't diagnose"),
        ):
            with self.subTest(text=text):
                self.assertTrue(answer(text).startswith(start))

    def test_disclosures_get_kindness_an_overview_and_next_steps(self):
        for text, opening, entry, team in (
            ("I have breast cancer", "I'm sorry you're dealing with this.", "Breast cancer:",
             "your care team"),
            ("my mum has leukaemia", "I'm sorry your mum is going through this.", "Leukemia:",
             "your mum's care team"),
        ):
            with self.subTest(text=text):
                reply = answer(text)
                self.assertTrue(reply.startswith(opening + "\n"))
                self.assertIn(entry, reply)
                self.assertIn("treatments", reply)
                self.assertIn(team, reply)
                self.assertNotIn("I can't diagnose", reply)
                self.assertTrue(reply.endswith(f"{DISCLAIMER}\n{CREDIT}"))

    def test_recurrence_worries_are_sent_to_the_care_team(self):
        reply = answer("is my cancer back?")
        self.assertIn("I can't tell whether cancer has come back or spread", reply)
        self.assertIn("your care team", reply)


class ImporterTests(unittest.TestCase):
    RAW = {
        "id": "test",
        "name": "Test cancer",
        "group": "Solid tumors",
        "aliases": ["testoma"],
        "nci": "https://www.cancer.gov/types/test",
        "summary": "A summary.",
        "symptoms": ["A lump"],
        "riskFactors": ["Age"],
        "screening": "None.",
        "screeningSource": {"name": "NCI", "url": "https://www.cancer.gov"},
        "treatments": ["Surgery"],
        "medicines": [{"name": "Drug", "use": "For tests"}],
        "approvals": [{"date": "2026-01-02", "drug": "Drug", "text": "Approved.", "url": "u"}],
        "query": "test cancer",
        "reviewed": "2026-11-12",
    }

    def test_render_is_deterministic_python_without_the_search_query(self):
        importer = _load_importer()
        cancers = [importer.convert_cancer(self.RAW)]
        faqs = [importer.convert_faq({"q": "Q?", "a": "A.", "link": "https://example.org"})]
        facts = importer.convert_facts({"title": "T", "intro": "I", "facts": []})
        source = importer.render(cancers, faqs, facts, commit="abc123", date="2026-11-20")
        again = importer.render(cancers, faqs, facts, commit="abc123", date="2026-11-20")
        self.assertEqual(source, again)
        self.assertIn("abc123", source.splitlines()[2])
        namespace = {}
        exec(compile(source, "cancer_data.py", "exec"), namespace)
        (entry,) = namespace["CANCERS"]
        self.assertNotIn("query", entry)
        self.assertEqual(entry["risk_factors"], ("Age",))
        self.assertEqual(namespace["FAQS"][0]["q"], "Q?")


if __name__ == "__main__":
    unittest.main()
