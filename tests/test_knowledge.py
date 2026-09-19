import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jarvis import knowledge
from jarvis.assistant import Assistant
from jarvis.memory import Memory


class FakeResponse:
    def __init__(
        self, payload: bytes, content_type: str = "text/html", charset: str = "utf-8"
    ) -> None:
        self._payload = payload
        self.headers = FakeHeaders(content_type, charset)

    def read(self, amount=None) -> bytes:
        return self._payload if amount is None else self._payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeHeaders:
    def __init__(self, content_type: str, charset: str) -> None:
        self._content_type = content_type
        self._charset = charset

    def get_content_charset(self):
        return self._charset

    def get_content_type(self):
        return self._content_type

    def get(self, _name, default=None):
        return default


PAGE = b"""
<html><head><title>Zephyr docs</title><style>body{color:red}</style></head>
<body><h1>Zephyr</h1><p>Zephyr is a build system.</p>
<p>The release cadence is monthly.</p><script>ignore()</script></body></html>
"""


class KnowledgeFileTests(unittest.TestCase):
    def test_add_file_reads_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("Zephyr is a build system.\n", encoding="utf-8")
            source = knowledge.add_file(str(path))
        self.assertEqual(source.kind, "file")
        self.assertEqual(source.title, "notes.md")
        self.assertIn("build system", source.text)

    def test_add_file_extracts_html_title_and_text(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_bytes(PAGE)
            source = knowledge.add_file(path)
        self.assertEqual(source.title, "Zephyr docs")
        self.assertIn("release cadence is monthly", source.text)
        self.assertNotIn("ignore()", source.text)

    def test_add_file_rejects_missing_file(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.add_file("/tmp/definitely-not-here.md")

    def test_add_file_rejects_directory(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(knowledge.KnowledgeError):
                knowledge.add_file(tmp)

    def test_add_file_rejects_binary_suffix(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.png"
            path.write_bytes(b"\x89PNG")
            with self.assertRaises(knowledge.KnowledgeError):
                knowledge.add_file(path)

    def test_add_file_rejects_empty_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("   \n", encoding="utf-8")
            with self.assertRaises(knowledge.KnowledgeError):
                knowledge.add_file(path)


class KnowledgeWebsiteTests(unittest.TestCase):
    def test_add_website_extracts_visible_text(self):
        opener = mock.Mock(return_value=FakeResponse(PAGE))
        source = knowledge.add_website("https://example.com/docs", opener=opener)
        self.assertEqual(source.kind, "website")
        self.assertEqual(source.title, "Zephyr docs")
        self.assertEqual(source.location, "https://example.com/docs")
        self.assertIn("Zephyr is a build system.", source.text)
        self.assertNotIn("color:red", source.text)

    def test_add_website_defaults_to_https(self):
        opener = mock.Mock(return_value=FakeResponse(b"<p>hello</p>"))
        source = knowledge.add_website("example.com", opener=opener)
        self.assertEqual(source.location, "https://example.com")
        self.assertEqual(opener.call_args[0][0].full_url, "https://example.com")

    def test_add_website_reads_plain_text(self):
        opener = mock.Mock(
            return_value=FakeResponse(b"Zephyr ships monthly.", "text/plain")
        )
        source = knowledge.add_website("https://example.com/notes.txt", opener=opener)
        self.assertEqual(source.text, "Zephyr ships monthly.")

    def test_add_website_falls_back_for_unknown_charset(self):
        opener = mock.Mock(return_value=FakeResponse(b"<p>hello</p>", charset="unknown"))
        source = knowledge.add_website("https://example.com", opener=opener)
        self.assertEqual(source.text, "hello")

    def test_add_website_rejects_non_text_content(self):
        opener = mock.Mock(return_value=FakeResponse(b"\x00", "image/png"))
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.add_website("https://example.com/logo.png", opener=opener)

    def test_add_website_rejects_oversized_response(self):
        opener = mock.Mock(
            return_value=FakeResponse(b"x" * (knowledge.MAX_WEBSITE_BYTES + 1))
        )
        with self.assertRaises(knowledge.KnowledgeError) as caught:
            knowledge.add_website("https://example.com/large", opener=opener)
        self.assertIn("too large", str(caught.exception))

    def test_add_website_rejects_unsupported_scheme(self):
        with self.assertRaises(knowledge.KnowledgeError):
            knowledge.add_website("ftp://example.com/file")

    def test_add_website_reports_network_failure(self):
        opener = mock.Mock(side_effect=OSError("no route"))
        with self.assertRaises(knowledge.KnowledgeError) as caught:
            knowledge.add_website("https://example.com", opener=opener)
        self.assertIn("could not reach", str(caught.exception))


class KnowledgeSearchTests(unittest.TestCase):
    def test_search_returns_best_passage(self):
        source = knowledge.Source(
            kind="file",
            title="notes.md",
            location="/tmp/notes.md",
            text="Zephyr is a build system.\nThe release cadence is monthly.",
        )
        found = knowledge.search([source], "what is the release cadence?")
        self.assertIsNotNone(found)
        matched, passages = found
        self.assertIs(matched, source)
        self.assertIn("release cadence is monthly", passages[0])

    def test_search_returns_none_without_matches(self):
        source = knowledge.Source("file", "notes.md", "/tmp/notes.md", "Zephyr.")
        self.assertIsNone(knowledge.search([source], "quantum tunnelling"))

    def test_search_ignores_stopword_only_query(self):
        source = knowledge.Source("file", "notes.md", "/tmp/notes.md", "It is ready.")
        self.assertIsNone(knowledge.search([source], "what is it?"))

    def test_search_matches_whole_words(self):
        source = knowledge.Source(
            "file", "notes.md", "/tmp/notes.md", "Concatenate these strings."
        )
        self.assertIsNone(knowledge.search([source], "cat"))

    def test_load_ignores_unreadable_entries(self):
        stored = [
            {"kind": "file", "title": "n", "location": "/tmp/n.md", "text": "hi"},
            {"kind": "file", "title": "empty", "location": "/tmp/empty.md", "text": " "},
            {"kind": "podcast", "location": "x"},
            "nonsense",
        ]
        self.assertEqual(len(knowledge.load(stored)), 1)
        self.assertEqual(knowledge.load("nonsense"), [])


class KnowledgeSkillTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(None)
        self.assistant = Assistant(memory=self.memory)

    def test_add_file_skill_stores_source(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("Zephyr is a build system.\n", encoding="utf-8")
            reply = self.assistant.respond(
                f"add the file {path} as a knowledge source"
            )
        self.assertIn("Added the file 'notes.md'", reply)
        stored = self.memory.get(knowledge.MEMORY_KEY)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["kind"], "file")

    def test_add_bare_path_is_treated_as_a_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("Zephyr ships monthly.\n", encoding="utf-8")
            reply = self.assistant.respond(f"add {path} as a knowledge source")
        self.assertIn("knowledge source", reply)
        self.assertEqual(len(self.memory.get(knowledge.MEMORY_KEY)), 1)

    def test_add_website_skill_stores_source(self):
        opener = mock.Mock(return_value=FakeResponse(PAGE))
        with mock.patch("urllib.request.urlopen", opener):
            reply = self.assistant.respond(
                "add https://example.com/docs as a knowledge source"
            )
        self.assertIn("Added the website 'Zephyr docs'", reply)
        stored = self.memory.get(knowledge.MEMORY_KEY)
        self.assertEqual(stored[0]["kind"], "website")

    def test_add_website_by_keyword(self):
        opener = mock.Mock(return_value=FakeResponse(PAGE))
        with mock.patch("urllib.request.urlopen", opener):
            reply = self.assistant.respond(
                "learn from the website https://example.com/docs"
            )
        self.assertIn("Added the website", reply)

    def test_add_website_reports_unsupported_scheme(self):
        reply = self.assistant.respond("add ftp://example.com/file as a knowledge source")
        self.assertIn("only read http and https", reply)

    def test_add_nested_relative_path_is_treated_as_a_file(self):
        reply = self.assistant.respond("add src/jarvis/knowledge.py as a knowledge source")
        self.assertIn("Added the file 'knowledge.py'", reply)

    def test_add_nested_relative_path_without_extension_is_treated_as_a_file(self):
        with TemporaryDirectory() as tmp:
            nested = Path(tmp) / "docs"
            nested.mkdir()
            (nested / "handbook").write_text("Zephyr ships monthly.\n", encoding="utf-8")
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                reply = self.assistant.respond("add docs/handbook as a knowledge source")
            finally:
                os.chdir(cwd)
        self.assertIn("Added the file 'handbook'", reply)

    def test_nested_domain_path_is_still_read_as_a_website(self):
        opener = mock.Mock(return_value=FakeResponse(PAGE))
        with mock.patch("urllib.request.urlopen", opener):
            reply = self.assistant.respond("add example.com/docs as a knowledge source")
        self.assertIn("Added the website", reply)

    def test_adding_the_same_source_twice_does_not_duplicate(self):
        opener = mock.Mock(return_value=FakeResponse(PAGE))
        with mock.patch("urllib.request.urlopen", opener):
            self.assistant.respond("add https://example.com as a knowledge source")
            self.assistant.respond("add https://example.com as a knowledge source")
        self.assertEqual(len(self.memory.get(knowledge.MEMORY_KEY)), 1)

    def test_missing_target_asks_for_one(self):
        self.assertIn("Which website", self.assistant.respond("add a website as a knowledge source"))
        self.assertIn("Which file", self.assistant.respond("add a file as a knowledge source"))

    def test_failures_are_reported_not_raised(self):
        reply = self.assistant.respond(
            "add the file /tmp/definitely-not-here.md as a knowledge source"
        )
        self.assertIn("could not find", reply)
        self.assertIsNone(self.memory.get(knowledge.MEMORY_KEY))

    def test_questions_are_answered_from_sources(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text(
                "Zephyr is our build system.\nThe release cadence is monthly.\n",
                encoding="utf-8",
            )
            self.assistant.respond(f"add the file {path} as a knowledge source")
            reply = self.assistant.respond("what is the release cadence?")
        self.assertIn("release cadence is monthly", reply)
        self.assertIn("notes.md", reply)

    def test_list_and_clear_sources(self):
        self.assertIn("no knowledge sources", self.assistant.respond("list my knowledge sources"))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("Zephyr.\n", encoding="utf-8")
            self.assistant.respond(f"add the file {path} as a knowledge source")
            listed = self.assistant.respond("list my knowledge sources")
        self.assertIn("notes.md", listed)
        self.assertIn("Forgot 1", self.assistant.respond("clear my knowledge sources"))
        self.assertEqual(self.memory.get(knowledge.MEMORY_KEY, []), [])

    def test_existing_routing_is_unchanged(self):
        self.assertIn("42", self.assistant.respond("calculate 21 * 2"))
        self.assertIn("Noted", self.assistant.respond("remember buy milk"))
        self.assertIn("Python", self.assistant.respond("what is Python?"))


if __name__ == "__main__":
    unittest.main()
