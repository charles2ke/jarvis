import unittest

from jarvis import bible
from jarvis.assistant import Assistant


class BibleDataTests(unittest.TestCase):
    def test_books_are_the_full_canon_in_order(self):
        names = bible.books()
        self.assertEqual(len(names), 66)
        self.assertEqual(names[0], "Genesis")
        self.assertEqual(names[-1], "Revelation")
        self.assertEqual(len(set(names)), 66)
        self.assertEqual(
            sum(1 for book in bible.BOOKS if book.testament == "Old Testament"), 39
        )
        self.assertEqual(
            sum(1 for book in bible.BOOKS if book.testament == "New Testament"), 27
        )

    def test_find_book_handles_aliases_and_typos(self):
        self.assertEqual(bible.find_book("genesis").name, "Genesis")
        self.assertEqual(bible.find_book("the book of Job").name, "Job")
        self.assertEqual(bible.find_book("first corinthians").name, "1 Corinthians")
        self.assertEqual(bible.find_book("1 cor").name, "1 Corinthians")
        self.assertEqual(bible.find_book("revelations").name, "Revelation")
        self.assertEqual(bible.find_book("psalm").name, "Psalms")
        self.assertIsNone(bible.find_book("book of Elrond"))
        self.assertIsNone(bible.find_book(""))

    def test_parse_reference_normalises_and_validates(self):
        self.assertEqual(bible.parse_reference("john 3:16"), "John 3:16")
        self.assertEqual(bible.parse_reference("1 cor 13:13"), "1 Corinthians 13:13")
        self.assertEqual(bible.parse_reference("Psalm 23:1"), "Psalms 23:1")
        self.assertIsNone(bible.parse_reference("John 99:1"))
        self.assertIsNone(bible.parse_reference("love"))

    def test_find_verse_returns_quoted_text(self):
        verse = bible.find_verse("John 3:16")
        self.assertIsNotNone(verse)
        self.assertIn("God so loved the world", verse.text)
        self.assertEqual(verse.book, "John")
        self.assertIsNone(bible.find_verse("Genesis 5:2"))

    def test_find_topic_handles_aliases_and_typos(self):
        self.assertEqual(bible.find_topic("love").title, "Love")
        self.assertEqual(bible.find_topic("worry").title, "Anxiety and worry")
        self.assertEqual(bible.find_topic("forgivness").title, "Forgiveness")
        self.assertEqual(bible.find_topic("ten commandments").title, "The Ten Commandments")
        self.assertIsNone(bible.find_topic("quantum physics"))

    def test_topic_references_resolve_in_canonical_order(self):
        topic = bible.find_topic("love")
        references = [verse.reference for verse in bible.verses_for(topic)]
        self.assertEqual(
            references,
            [
                "Matthew 22:37",
                "Matthew 22:39",
                "1 Corinthians 13:4",
                "1 Corinthians 13:13",
                "1 John 4:8",
            ],
        )

    def test_search_finds_verses_by_keyword(self):
        found = bible.search("shepherd")
        self.assertEqual([verse.reference for verse in found], ["Psalms 23:1"])
        self.assertEqual(bible.search(""), [])
        self.assertEqual(bible.search("the and for"), [])

    def test_topics_are_sorted_titles(self):
        titles = bible.topics()
        self.assertEqual(titles, sorted(titles))
        self.assertEqual(len(titles), len(bible.TOPICS))

    def test_suggestions_offer_close_titles(self):
        self.assertIn("Forgiveness", bible.suggestions("forgivenes"))
        self.assertEqual(bible.suggestions(""), [])


class BibleSkillTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant()

    def test_verse_lookup(self):
        reply = self.assistant.respond("bible John 3:16")
        self.assertTrue(reply.startswith("John 3:16:"))
        self.assertIn("eternal life", reply)

    def test_topic_question(self):
        reply = self.assistant.respond("what does the bible say about hope?")
        self.assertTrue(reply.startswith("Hope:"))
        self.assertIn("Jeremiah 29:11", reply)

    def test_verses_about_phrasing(self):
        reply = self.assistant.respond("bible verses about anxiety")
        self.assertTrue(reply.startswith("Anxiety and worry:"))

    def test_book_question(self):
        reply = self.assistant.respond("tell me about the book of Job")
        self.assertIn("Old Testament", reply)
        self.assertIn("42 chapters", reply)

    def test_person_question(self):
        reply = self.assistant.respond("who was Moses in the bible")
        self.assertTrue(reply.startswith("Moses:"))

    def test_keyword_fallback_quotes_matching_verses(self):
        reply = self.assistant.respond("bible shepherd")
        self.assertIn("Psalms 23:1", reply)

    def test_unknown_reference_is_admitted(self):
        reply = self.assistant.respond("bible Genesis 5:2")
        self.assertIn("Genesis 5:2", reply)
        self.assertIn("offline selection", reply)

    def test_unknown_subject_suggests_topics(self):
        reply = self.assistant.respond("bible flibberty")
        self.assertIn("I do not have a Bible entry", reply)
        self.assertIn("bible topics", reply)

    def test_topics_and_books_listings(self):
        topics = self.assistant.respond("bible topics")
        self.assertIn("Forgiveness", topics)
        books = self.assistant.respond("books of the bible")
        self.assertIn("66 books", books)
        self.assertIn("Revelation", books)

    def test_overview(self):
        reply = self.assistant.respond("what is the bible")
        self.assertTrue(reply.startswith("The Bible:"))

    def test_other_skills_still_win(self):
        self.assertIn("gravity", self.assistant.respond("what is gravity?").lower())
        self.assertIn("name", self.assistant.respond("what is my name?").lower())


if __name__ == "__main__":
    unittest.main()
