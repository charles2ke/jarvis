import unittest

from jarvis import maritime


class MaritimeTests(unittest.TestCase):
    def test_lookup_by_title_and_alias(self):
        self.assertEqual(maritime.lookup("GMDSS").title, "GMDSS")
        self.assertEqual(
            maritime.lookup("emergency position indicating radio beacon").title,
            "EPIRB",
        )
        self.assertEqual(maritime.lookup("digital selective calling").title, "DSC")
        self.assertEqual(maritime.lookup("mayday").title, "Distress priorities")

    def test_lookup_is_forgiving(self):
        self.assertEqual(maritime.lookup("  Navtex! ").title, "NAVTEX")
        self.assertEqual(maritime.lookup("s.o.s.").title, "SOS")
        self.assertEqual(maritime.lookup("epirbs").title, "EPIRB")
        self.assertEqual(maritime.lookup("navtexx").title, "NAVTEX")

    def test_lookup_unknown_returns_none(self):
        self.assertIsNone(maritime.lookup("quantum submarine"))
        self.assertIsNone(maritime.lookup(""))

    def test_topics_are_sorted_titles(self):
        titles = maritime.topics()
        self.assertEqual(titles, sorted(titles))
        self.assertIn("SART", titles)
        self.assertEqual(len(titles), len(maritime.ENTRIES))

    def test_suggestions_offer_close_titles(self):
        self.assertIn("EPIRB", maritime.suggestions("epirp beacon"))
        self.assertEqual(maritime.suggestions(""), [])


if __name__ == "__main__":
    unittest.main()
