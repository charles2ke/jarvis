import copy
import re
import unittest
from unittest import mock

from project_support import ProjectTestCase, missing_projects

from jarvis import cancer, projects
from jarvis.cancer import CREDIT, DISCLAIMER, SITE_URL, answer

CANCERS_FILE = "site/data/cancers.json"
FAQ_FILE = "site/data/faq.json"
FACTS_FILE = "site/data/facts.json"


def _approval(day, drug):
    return {"date": day, "drug": drug, "text": "Approved in a made-up trial.",
            "url": "https://example.org/approval"}


# Made-up data in the shape of beat-it's site/data files.
KNUCKLE = {
    "id": "knuckle",
    "name": "Knuckle cancer",
    "group": "Pretend solid tumors",
    "aliases": ["knuckle tumor", "metacarpal"],
    "nci": "https://example.org/knuckle",
    "summary": "An invented cancer for these tests.",
    "symptoms": ["Sore knuckles", "Blue fingers", "Odd hiccups", "Loud sneezes"],
    "riskFactors": ["Cracking joints", "Wobble virus infection"],
    "screening": "Tap each knuckle once a year.",
    "screeningSource": {"name": "Pretend Board", "url": "https://example.org/board"},
    "treatments": ["Rest", "Splint"],
    "medicines": [{"name": "Alphamab", "use": "Made-up use.", "since": "2026-02-03"}]
    + [{"name": f"Medicine {letter}", "use": "Made-up use."} for letter in "BCDEFG"],
    "approvals": [
        _approval("2025-01-10", "Drug one"),
        _approval("2026-01-10", "Drug three"),
        _approval("2025-06-10", "Drug two"),
        _approval("2026-04-01", "Shared drug"),
        _approval("2024-03-10", "Drug zero"),
        _approval("2026-02-10", "Drug four"),
    ],
    "reviewed": "2026-03-04",
}
LANTERN = {
    "id": "lantern",
    "name": "Lantern and zebra tumors",
    "group": "Pretend solid tumors",
    "aliases": ["lantern tumor"],
    "summary": "Another invented type, with little listed.",
}
FIZZ = {
    "id": "fizz",
    "name": "Fizz lymphoma",
    "group": "Pretend blood cancers",
    "summary": "A third invented type.",
    "symptoms": ["Tiredness"],
    "treatments": ["Rest"],
    "approvals": [_approval("2026-04-01", "Shared drug")],
    "reviewed": "2026-05-06",
}
FAQS = [
    {"q": "Please explain cancer", "a": "A made-up answer about cells.",
     "link": "https://example.org/what"},
    {"q": "How is cancer treated?", "a": "A made-up answer about treatment."},
    {"q": "How can I lower my risk?", "a": "A made-up answer about habits."},
    {"q": "Does cancer run in families?", "a": "A made-up answer about families."},
]
FACTS = {
    "title": "Made-up figures",
    "intro": "Invented numbers for tests.",
    "facts": [
        {"value": "7", "label": "pretend cases a day", "source": "Test Registry"},
        {"value": "3", "label": "knuckle checks a week.", "source": "Other Registry"},
    ],
}
FILES = {CANCERS_FILE: [KNUCKLE, LANTERN, FIZZ], FAQ_FILE: FAQS, FACTS_FILE: FACTS}
ENDING = f"\n{DISCLAIMER}\n{CREDIT}"


class MadeUpProjectTestCase(unittest.TestCase):
    """Reads ``files`` in place of beat-it's data files."""

    files = FILES

    def setUp(self):
        cancer._clear_cache()
        self.addCleanup(cancer._clear_cache)
        self.reads = []

        def read_json(name, path):
            self.assertEqual(name, "beat-it")
            self.reads.append(path)
            return copy.deepcopy(self.files[path])

        patcher = mock.patch.object(projects, "read_json", side_effect=read_json)
        patcher.start()
        self.addCleanup(patcher.stop)


class CancerLookupTests(MadeUpProjectTestCase):
    def test_other_questions_are_left_alone_without_the_project(self):
        for text in (
            "I'm a Cancer",
            "my cancer horoscope for today",
            "the Tropic of Cancer",
            "cancel my order",
            "corruption is a cancer on society",
            "what is AML compliance?",
            "what's the weather like?",
            "stomach ache",
            "HPV vaccine",
            "metacarpal pain",
        ):
            with self.subTest(text=text):
                self.assertIsNone(answer(text))
        self.assertEqual(self.reads, [])

    def test_names_are_read_once_in_the_projects_order(self):
        expected = ("Knuckle cancer", "Lantern and zebra tumors", "Fizz lymphoma")
        self.assertEqual(cancer.names(), expected)
        for text in ("knuckle cancer", "what is cancer?", "how common is cancer?", "cancer topics"):
            answer(text)
        self.assertEqual(cancer.names(), expected)
        self.assertEqual(sorted(self.reads), [CANCERS_FILE, FACTS_FILE, FAQ_FILE])

    def test_names_aliases_plurals_and_slips(self):
        for text, start in (
            ("knuckle cancer", "Knuckle cancer (Pretend solid tumors)\n"),
            ("knuckle cancers", "Knuckle cancer (Pretend solid tumors)\n"),
            ("cancer of the knuckles", "Knuckle cancer (Pretend solid tumors)\n"),
            ("knukcle cancer", "Knuckle cancer (Pretend solid tumors)\n"),
            ("metacarpal cancer symptoms", "Symptoms of knuckle cancer that beat-it lists:\n"),
            ("zebra tumours", "Lantern and zebra tumors (Pretend solid tumors)\n"),
            ("what is fizz lymphoma?", "Fizz lymphoma (Pretend blood cancers)\n"),
        ):
            with self.subTest(text=text):
                self.assertTrue(answer(text).startswith(start))

    def test_what_beat_it_does_not_cover_is_not_guessed(self):
        reply = answer("small bowel cancer symptoms")
        self.assertTrue(reply.startswith(
            "beat-it doesn't have an entry for small bowel cancer. It covers 3 types"))
        reply = answer("who discovered chemotherapy?")
        self.assertIn("beat-it's notes don't cover that question", reply)
        self.assertIn("'please explain cancer', 'how can I lower my risk?' and 'does cancer "
                      "run in families?'", reply)


class CancerReplyTests(MadeUpProjectTestCase):
    def test_replies_end_with_the_disclaimer_and_credit(self):
        for text in ("knuckle cancer", "knuckle cancer screening", "what is cancer?",
                     "cancer topics", "fizz lymphoma symptoms and treatments"):
            with self.subTest(text=text):
                self.assertTrue(answer(text).endswith(ENDING))

    def test_overview_and_long_lists(self):
        overview = answer("knuckle cancer")
        self.assertIn("\n- Symptoms: Sore knuckles; Blue fingers; Odd hiccups; and 1 more\n", overview)
        self.assertIn("\n- Also listed: risk factors, screening, 7 medicines and 6 FDA approvals "
                      "since 2024\n", overview)
        self.assertIn("\nReviewed by beat-it on 4 March 2026.\n", overview)
        medicines = answer("knuckle cancer medicines")
        self.assertTrue(medicines.startswith(
            "Medicines beat-it gives as examples for knuckle cancer (6 of 7):\n"
            "- Alphamab (FDA approved 3 February 2026) — Made-up use.\n"))
        self.assertIn("\n- and 1 more on the beat-it site\n", medicines)

    def test_approvals_are_newest_first(self):
        reply = answer("knuckle cancer approvals")
        self.assertTrue(reply.startswith("FDA approvals beat-it lists for knuckle cancer "
                                         "(newest 5 of 6):\n"))
        self.assertEqual(
            re.findall(r"^- (\d+ \w+ \d{4}) — ", reply, re.M),
            ["1 April 2026", "10 February 2026", "10 January 2026", "10 June 2025",
             "10 January 2025"],
        )
        self.assertIn("As listed by beat-it on 4 March 2026", reply)
        self.assertEqual(answer("latest FDA cancer approvals").count("Shared drug"), 1)

    def test_details_the_project_leaves_out_are_skipped(self):
        self.assertEqual(
            answer("lantern tumor"),
            "Lantern and zebra tumors (Pretend solid tumors)\n"
            "Another invented type, with little listed." + ENDING,
        )
        self.assertEqual(
            answer("zebra tumor screening"),
            "beat-it doesn't describe screening for lantern and zebra tumors." + ENDING,
        )

    def test_faqs_figures_and_topics(self):
        self.assertTrue(answer("what is cancer?").startswith(
            "Please explain cancer\nA made-up answer about cells.\nMore: https://example.org/what\n"))
        self.assertTrue(answer("how do I prevent cancer?").startswith("How can I lower my risk?\n"))
        self.assertNotIn("More:", answer("cancer treatments"))
        self.assertTrue(answer("how common is cancer?").startswith(
            "Made-up figures: Invented numbers for tests.\n- 7 pretend cases a day (Test Registry)\n"
            "- 3 knuckle checks a week (Other Registry)\n"))
        self.assertNotIn("pretend cases", answer("how common is knuckle cancer?"))
        self.assertTrue(cancer.topics().startswith(
            "beat-it covers 3 cancer types (reviewed 6 May 2026):\n"
            "- Pretend solid tumors: Knuckle cancer, Lantern and zebra tumors\n"
            "- Pretend blood cancers: Fizz lymphoma\n"))

    def test_contagion_and_survival_are_not_answered_beyond_the_data(self):
        reply = answer("is cancer contagious?")
        self.assertIn("don't say whether cancer itself can pass from person to person", reply)
        self.assertIn("\n- Knuckle cancer: Wobble virus infection\n", reply)
        reply = answer("survival rate for knuckle cancer")
        self.assertIn("beat-it doesn't give survival rates", reply)
        self.assertIn("NCI's page on knuckle cancer: https://example.org/knuckle", reply)


class CancerPersonalTests(MadeUpProjectTestCase):
    def test_self_checks_are_not_diagnosed(self):
        for text, person in (
            ("do I have cancer?", "you"),
            ("does my dad have cancer?", "your dad"),
        ):
            with self.subTest(text=text):
                reply = answer(text)
                self.assertIn(f"I can't diagnose cancer or tell what a symptom means — a doctor "
                              f"who can examine {person} can.", reply)
                self.assertNotIn("Reviewed by beat-it", reply)
                self.assertTrue(reply.endswith(ENDING))
        reply = answer("I have a lump on my knuckle, is it cancer?")
        self.assertIn("\nGeneral warning signs beat-it lists for knuckle cancer:\n- Sore knuckles\n",
                      reply)
        self.assertIn("\n- Loud sneezes\nReviewed by beat-it on 4 March 2026.\n", reply)

    def test_worries_get_general_guidance(self):
        reply = answer("I'm worried about getting cancer")
        self.assertIn("ask 'how can I lower my risk?' or 'does cancer run in families?'", reply)

    def test_disclosures_get_kindness_an_overview_and_next_steps(self):
        reply = answer("my mum has fizz lymphoma")
        self.assertTrue(reply.startswith("I'm sorry your mum is going through this.\n"
                                         "Fizz lymphoma: A third invented type.\n"))
        self.assertIn("your mum's care team", reply)
        self.assertIn("\nReviewed by beat-it on 6 May 2026.\n", reply)
        reply = answer("my child has cancer")
        self.assertIn("for example 'knuckle cancer'", reply)
        self.assertNotIn("I can't diagnose", reply)

    def test_recurrence_worries_are_sent_to_the_care_team(self):
        reply = answer("is my cancer back?")
        self.assertIn("I can't tell whether cancer has come back or spread", reply)
        self.assertIn("your care team", reply)


class CancerProjectProblemTests(unittest.TestCase):
    def setUp(self):
        cancer._clear_cache()
        self.addCleanup(cancer._clear_cache)

    def test_missing_project_explains_the_setup(self):
        for ask in (lambda: answer("lung cancer"), cancer.names, cancer.topics):
            cancer._clear_cache()
            with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
                ask()
            self.assertIn("git submodule update --init projects/beat-it", str(raised.exception))
            self.assertIn(SITE_URL, str(raised.exception))

    def test_unusable_data_is_an_error(self):
        broken = (
            (CANCERS_FILE, {"cancers": []}, "knuckle cancer"),
            (CANCERS_FILE, [], "knuckle cancer"),
            (CANCERS_FILE, [dict(KNUCKLE, name="")], "knuckle cancer"),
            (CANCERS_FILE, [dict(KNUCKLE, symptoms="Sore knuckles")], "knuckle cancer"),
            (CANCERS_FILE, [dict(KNUCKLE, reviewed="2026-02-30")], "knuckle cancer"),
            (CANCERS_FILE, [dict(KNUCKLE, approvals=[{"drug": "x", "text": "y"}])], "knuckle cancer"),
            (CANCERS_FILE, [KNUCKLE, KNUCKLE], "knuckle cancer"),
            (FAQ_FILE, {"q": "Please explain cancer"}, "what is cancer?"),
            (FAQ_FILE, [{"q": "Please explain cancer"}], "what is cancer?"),
            (FACTS_FILE, {"facts": []}, "how common is cancer?"),
        )
        for path, data, text in broken:
            cancer._clear_cache()
            files = dict(FILES, **{path: data})
            with self.subTest(path=path, data=str(data)[:60]):
                with mock.patch.object(projects, "read_json", side_effect=lambda _, p: files[p]):
                    with self.assertRaises(projects.ProjectError) as raised:
                        answer(text)
                self.assertIn(path.rsplit("/", 1)[-1], str(raised.exception))


class CancerProjectTests(ProjectTestCase):
    """Answers from the real beat-it data in projects/beat-it."""

    project = "beat-it"

    def setUp(self):
        cancer._clear_cache()
        self.addCleanup(cancer._clear_cache)

    def test_every_type_is_found_by_its_name_and_listed(self):
        names = cancer.names()
        self.assertEqual(len(set(names)), len(names))
        listing = cancer.topics()
        for name in names:
            with self.subTest(name=name):
                self.assertIn(name, listing)
                reply = answer(name)
                self.assertTrue(reply.startswith(f"{name} ("))
                self.assertTrue(reply.endswith(ENDING))

    def test_every_faq_is_answered_from_the_project(self):
        for item in projects.read_json("beat-it", FAQ_FILE):
            with self.subTest(question=item["q"]):
                # Some questions don't mention cancer; Jarvis only answers ones that do.
                reply = answer(item["q"]) or answer(f"{item['q']} (cancer)")
                self.assertIn(f"{item['q']}\n{item['a']}\n", reply)

    def test_worldwide_figures_give_their_sources(self):
        reply = answer("how common is cancer?")
        for fact in projects.read_json("beat-it", FACTS_FILE)["facts"]:
            self.assertIn(f"({fact['source']})", reply)

    def test_spellings_slips_and_phrasings_find_the_same_type(self):
        for text, same_as in (
            ("brain tumour", "brain tumor"),
            ("prostrate cancer", "prostate cancer"),
            ("oesophagus cancer", "esophageal cancer"),
            ("cancer of the colon", "colon cancer"),
            ("lukemia symptoms", "leukemia symptoms"),
        ):
            with self.subTest(text=text):
                self.assertEqual(answer(text), answer(same_as))
        reply = answer("my mum has leukaemia")
        self.assertTrue(reply.startswith("I'm sorry your mum is going through this.\nLeukemia: "))


if __name__ == "__main__":
    unittest.main()
