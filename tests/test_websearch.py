import _thread
import http.client
import http.server
import io
import json
import os
import signal
import socket
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jarvis import websearch
from jarvis.assistant import FALLBACK_RESPONSE, Assistant
from jarvis.cli import main
from jarvis.memory import Memory
from jarvis.skills import WEB_STATE


class FakeHeaders:
    def __init__(self, content_type):
        self._content_type = content_type

    def get_content_charset(self):
        return "utf-8"

    def get_content_type(self):
        return self._content_type

    def get(self, _name, default=None):
        return default


class FakeResponse:
    def __init__(self, payload, content_type="application/json"):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = FakeHeaders(content_type)

    def read(self, amount=None):
        return self._payload if amount is None else self._payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWeb:
    """An opener that answers by URL prefix and records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        for prefix, answer in self.routes:
            if request.full_url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer() if callable(answer) else answer
        raise urllib.error.URLError("no route")

    def params(self, index=0):
        query = urllib.parse.urlsplit(self.requests[index].full_url).query
        return dict(urllib.parse.parse_qsl(query))


WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGES = [
    {
        "index": 2,
        "title": "Alexander Graham Bell",
        "fullurl": "https://en.wikipedia.org/wiki/Alexander_Graham_Bell",
        "extract": "Alexander Graham Bell was a Scottish-born inventor and teacher. "
        "He received the first patent for a practical telephone in 1876.[2]",
    },
    {
        "index": 1,
        "title": "Invention of the telephone",
        "fullurl": "https://en.wikipedia.org/wiki/Invention_of_the_telephone",
        "extract": "Many inventors worked on the telephone, and several made rival "
        "claims to it. Bell won the key patent in the U.S. in 1876. Courts later "
        "heard many disputes over who invented the telephone first.",
    },
    {
        "index": 3,
        "title": "Telephone (disambiguation)",
        "fullurl": "https://en.wikipedia.org/wiki/Telephone_(disambiguation)",
        "extract": "Telephone may refer to:",
    },
]


def wiki(pages=WIKI_PAGES):
    return lambda: FakeResponse({"query": {"pages": pages}})


DOCS = (
    websearch.Document(
        "Invention of the telephone",
        "https://en.wikipedia.org/wiki/Invention_of_the_telephone",
        "Many inventors worked on the telephone, and several made rival claims to it. "
        "Alexander Graham Bell won the key telephone patent in 1876. Courts later "
        "heard many disputes over who invented the telephone first. Early telephone "
        "lines connected only two rooms at a time. Telephone exchanges came later "
        "and let many lines connect to each other.",
    ),
    websearch.Document(
        "Alexander Graham Bell",
        "https://en.wikipedia.org/wiki/Alexander_Graham_Bell",
        "Alexander Graham Bell was a Scottish-born inventor and teacher of the deaf. "
        "He co-founded a telephone company in 1885.",
    ),
)


WEB_ENV = (
    "JARVIS_WEB_SEARCH",
    "JARVIS_SEARCH_PROVIDER",
    "JARVIS_BRAVE_API_KEY",
    "JARVIS_SEARXNG_URL",
    "JARVIS_WIKIPEDIA_LANG",
)


class CleanEnvTestCase(unittest.TestCase):
    """Ignore any web search settings in the developer's environment."""

    def setUp(self):
        env = {key: value for key, value in os.environ.items() if key not in WEB_ENV}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)


def fake_search(documents=DOCS, provider="Wikipedia"):
    calls = []

    def search(query, **_kwargs):
        calls.append(query)
        return websearch.SearchResults(query=query, provider=provider, documents=tuple(documents))

    search.calls = calls
    return search


class WikipediaTests(unittest.TestCase):
    def test_parses_ranked_extracts_and_skips_disambiguation(self):
        web = FakeWeb([(WIKI_API, wiki())])
        results = websearch.search("invented the telephone", opener=web, environ={})
        self.assertEqual(results.provider, "Wikipedia")
        self.assertEqual(
            [doc.title for doc in results.documents],
            ["Invention of the telephone", "Alexander Graham Bell"],
        )
        summary = websearch.summarize("telephone patent", results.documents, limit=10)
        self.assertIn("He received the first patent for a practical telephone in 1876.", [s.text for s in summary])
        params = web.params()
        self.assertEqual(params["gsrsearch"], "invented the telephone")
        self.assertEqual(params["prop"], "extracts|info")

    def test_retries_with_any_word_when_nothing_matches(self):
        responses = iter([FakeResponse({"batchcomplete": True}), wiki()()])
        web = FakeWeb([(WIKI_API, lambda: next(responses))])
        results = websearch.search("telephone inventor rivalry", opener=web, environ={})
        self.assertEqual(len(web.requests), 2)
        self.assertEqual(web.params(1)["gsrsearch"], "telephone OR inventor OR rivalry")
        self.assertEqual(len(results.documents), 2)

    def test_language_comes_from_the_environment_and_is_validated(self):
        web = FakeWeb([("https://de.wikipedia.org/w/api.php", wiki())])
        websearch.search("Telefon", opener=web, environ={"JARVIS_WIKIPEDIA_LANG": "de"})
        self.assertEqual(len(web.requests), 1)
        with self.assertRaisesRegex(websearch.WebSearchError, "language code"):
            websearch.search("x", opener=web, environ={"JARVIS_WIKIPEDIA_LANG": "evil.com/x"})

    def test_network_failures_become_readable_errors(self):
        refused = urllib.error.HTTPError(WIKI_API, 503, "busy", {}, None)
        for answer, message in (
            (refused, r"Wikipedia refused the search \(HTTP 503\)\."),
            (urllib.error.URLError("no route to host"), "Wikipedia could not be reached"),
            (http.client.IncompleteRead(b"{", 10), "Wikipedia could not be reached"),
            # The server's bad status line is quoted without its escape codes.
            (http.client.BadStatusLine("\x1b[2Jbad"), r"Wikipedia could not be reached \(\[2Jbad\)\.$"),
            (lambda: FakeResponse(b"<html>"), "could not read"),
        ):
            with self.subTest(message=message):
                web = FakeWeb([(WIKI_API, answer)])
                with self.assertRaisesRegex(websearch.WebSearchError, message):
                    websearch.search("telephone", opener=web, environ={})

    def test_strips_terminal_control_characters_from_results(self):
        pages = [dict(WIKI_PAGES[0], title="Bell\x1b[2J\u202e", extract="Bell\x07 built a telephone in 1876.")]
        web = FakeWeb([(WIKI_API, wiki(pages))])
        doc = websearch.search("bell", opener=web, environ={}).documents[0]
        self.assertEqual(doc.title, "Bell[2J")
        self.assertEqual(doc.text, "Bell built a telephone in 1876.")


class ProviderTests(unittest.TestCase):
    def test_choose_provider(self):
        self.assertEqual(websearch.choose_provider({}), "wikipedia")
        self.assertEqual(websearch.choose_provider({"JARVIS_SEARXNG_URL": "https://s.example"}), "searxng")
        self.assertEqual(
            websearch.choose_provider({"JARVIS_SEARXNG_URL": "https://s.example", "JARVIS_BRAVE_API_KEY": "k"}),
            "brave",
        )
        self.assertEqual(
            websearch.choose_provider({"JARVIS_BRAVE_API_KEY": "k", "JARVIS_SEARCH_PROVIDER": "Wikipedia"}),
            "wikipedia",
        )
        with self.assertRaisesRegex(websearch.WebSearchError, "must be wikipedia, searxng or brave"):
            websearch.choose_provider({"JARVIS_SEARCH_PROVIDER": "bing"})

    def test_brave_reads_result_pages_and_falls_back_to_snippets(self):
        page = FakeResponse(
            b"<html><head><title>Bells</title></head><body><p>Bell patented the "
            b"telephone in 1876.</p></body></html>",
            content_type="text/html",
        )
        api = {
            "web": {
                "results": [
                    {"title": "<b>Bell</b> story", "url": "https://bells.example/a", "description": "A <b>bell</b> history."},
                    {"title": "Down", "url": "https://down.example/b", "description": "Snippet only.", "extra_snippets": ["More."]},
                    {"title": "Private", "url": "http://192.168.1.5/admin", "description": "Router page."},
                ]
            }
        }
        web = FakeWeb(
            [
                (websearch.BRAVE_ENDPOINT, lambda: FakeResponse(api)),
                ("https://bells.example/", page),
                ("https://down.example/", http.client.IncompleteRead(b"", 10)),
            ]
        )
        results = websearch.search(
            "bell telephone", opener=web, environ={"JARVIS_BRAVE_API_KEY": "secret"}
        )
        self.assertEqual(results.provider, "Brave Search")
        self.assertEqual(web.requests[0].get_header("X-subscription-token"), "secret")
        first, second, third = results.documents
        self.assertEqual(first.title, "Bell story")
        self.assertEqual(first.text, "A bell history.\nBell patented the telephone in 1876.")
        self.assertEqual(second.text, "Snippet only.\nMore.")
        self.assertEqual(third.text, "Router page.")
        fetched = [request.full_url for request in web.requests]
        self.assertNotIn("http://192.168.1.5/admin", fetched)

    def test_searxng_uses_the_configured_instance(self):
        api = {"results": [{"title": "Bell", "url": "https://x.example/bell", "content": "Bell made a telephone."}]}
        web = FakeWeb([("https://search.example/search?", lambda: FakeResponse(api))])
        with mock.patch("jarvis.websearch.knowledge.add_website", side_effect=websearch.knowledge.KnowledgeError("no")):
            results = websearch.search(
                "bell", opener=web, environ={"JARVIS_SEARXNG_URL": "https://search.example/search/"}
            )
        self.assertEqual(web.params()["format"], "json")
        self.assertEqual(results.documents[0].text, "Bell made a telephone.")
        refused = urllib.error.HTTPError("https://search.example/search", 403, "no", {}, None)
        web = FakeWeb([("https://search.example/", refused)])
        with self.assertRaisesRegex(websearch.WebSearchError, "json format"):
            websearch.search("bell", opener=web, environ={"JARVIS_SEARXNG_URL": "https://search.example"})

    def test_slow_pages_fall_back_to_snippets_and_do_not_block_ctrl_c(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(request, timeout=None):
            release.wait(5)
            raise urllib.error.URLError("too slow")

        hits = [("Slow", "https://slow.example/", "Snippet.")]
        started = time.monotonic()
        with mock.patch.object(websearch, "PAGE_DEADLINE", 0.3):
            documents = websearch._read_pages(hits, limit=3, opener=slow)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual([document.text for document in documents], ["Snippet."])

        previous = signal.signal(signal.SIGINT, signal.default_int_handler)
        self.addCleanup(signal.signal, signal.SIGINT, previous)
        timer = threading.Timer(0.2, _thread.interrupt_main)
        self.addCleanup(timer.cancel)
        started = time.monotonic()
        with self.assertRaises(KeyboardInterrupt):
            timer.start()
            websearch._read_pages(hits, limit=3, opener=slow)
        self.assertLess(time.monotonic() - started, 2)

    def test_private_addresses_are_never_read(self):
        for url in (
            "http://localhost:8080/",
            "http://127.0.0.1/",
            "http://10.1.2.3/",
            "http://[::1]/",
            "http://169.254.169.254/latest/meta-data",
            "http://2130706433/",
            "http://intranet/",
            "http://printer.local/",
            "file:///etc/passwd",
            # urllib would read these as 127.0.0.1:8080 or with a user name.
            "http://127.0.0.1%3a8080/admin",
            "http://user@example.com/",
            "http://example.com:0/",
        ):
            with self.subTest(url=url):
                self.assertFalse(websearch.is_public_url(url))
        self.assertTrue(websearch.is_public_url("https://en.wikipedia.org/wiki/Bell"))
        resolver = lambda host, port: [(2, 1, 6, "", ("10.0.0.7", 0))]
        self.assertFalse(websearch._resolves_publicly("rebind.example", resolver))

        def unknown(host, port):
            raise socket.gaierror("Name or service not known")

        self.assertFalse(websearch._resolves_publicly("nowhere.example", unknown))
        public = lambda host, port: [(2, 1, 6, "", ("1.1.1.1", 0))]
        self.assertTrue(websearch._resolves_publicly("one.example", public))

    def test_pages_are_refused_when_the_connection_reaches_a_private_address(self):
        requests = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                body = b"<title>Router</title><p>admin password</p>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def open_page(url):
            return websearch._open_public_page(urllib.request.Request(url), timeout=5)

        # The name resolved to a public address when checked, as in DNS rebinding.
        with mock.patch.dict(os.environ, {"no_proxy": "*", "NO_PROXY": "*"}), mock.patch.object(
            websearch, "_resolves_publicly", return_value=True
        ):
            for scheme in ("http", "https"):
                with self.subTest(scheme=scheme):
                    with self.assertRaisesRegex(urllib.error.URLError, "private network address"):
                        open_page(f"{scheme}://127.0.0.1:{port}/")
            with mock.patch.object(websearch, "_is_public_address", return_value=True):
                with open_page(f"http://127.0.0.1:{port}/allowed") as response:
                    self.assertIn(b"admin password", response.read())
        self.assertEqual(requests, ["/allowed"])


class TextTests(unittest.TestCase):
    def test_split_sentences_keeps_abbreviations_together(self):
        text = "Dr. Smith moved to Washington, D.C. in 1990. The U.S. Army met J. R. Jones there. It rained."
        self.assertEqual(
            websearch.split_sentences(text),
            ["Dr. Smith moved to Washington, D.C. in 1990.", "The U.S. Army met J. R. Jones there.", "It rained."],
        )

    def test_summarize_prefers_relevant_sentences_and_cites_them(self):
        sentences = websearch.summarize("who invented the telephone?", DOCS)
        self.assertEqual(len(sentences), 3)
        self.assertEqual(sentences, sorted(sentences, key=lambda s: (s.source, s.position)))
        joined = websearch.cite(sentences)
        self.assertTrue(joined.startswith("Many inventors worked on the telephone"))
        self.assertIn("Alexander Graham Bell was a Scottish-born inventor", joined)
        self.assertNotIn("exchanges", joined)
        self.assertRegex(joined, r"patent in 1876\. \[1\] Alexander .* deaf\. \[2\]$")

    def test_summarize_prefers_answers_to_sentences_that_restate_the_question(self):
        doc = websearch.Document(
            "Invention of the telephone",
            "https://en.wikipedia.org/wiki/Invention_of_the_telephone",
            "The invention of the telephone involved many people. "
            "Alexander Graham Bell was the first to be awarded a patent for the electric telephone. "
            "Disputes over who invented the telephone went to court many times.",
        )
        picked = websearch.cite(websearch.summarize("who invented the telephone?", [doc], limit=2))
        self.assertIn("Alexander Graham Bell was the first", picked)
        self.assertNotIn("Disputes", picked)
        # A relative clause answers the question, so it is not penalised.
        answer = websearch.Document(
            "Telephone",
            "https://en.wikipedia.org/wiki/Telephone",
            "The telephone has a long history of development. "
            "Bell, who invented the telephone, was born in Edinburgh in 1847.",
        )
        best = websearch.summarize("who invented the telephone?", [answer], limit=1)
        self.assertEqual([s.position for s in best], [1])

    def test_summarize_skips_near_duplicates_and_excluded_sentences(self):
        doc = websearch.Document("A", "https://a.example", "Bell made the telephone in 1876. Bell made the telephone in 1876 too. Bell also taught deaf students.")
        picked = websearch.summarize("telephone bell", [doc], limit=3)
        self.assertEqual([s.position for s in picked], [0, 2])
        rest = websearch.summarize("telephone bell", [doc], exclude=[(0, 0), (0, 2)])
        self.assertEqual([s.position for s in rest], [1])

    def test_lookup_detection(self):
        for text in (
            "who invented the telephone?",
            "do you know when Rome was founded",
            "how do I tie a tie?",
            "Who was Elizabeth I?",
            "Tell me about Peter I of Russia",
            "When did World War I end?",
            "What is Stage I cancer?",
            "Why was World War I called the Great War?",
            "What does Stage I mean?",
            "Do you know when World War I ended?",
            "World War I ended in 1918; why did it start?",
            "What is a Grade I listed building?",
            "who was the first U.S. president?",
            "can dogs eat grapes?",
        ):
            with self.subTest(text=text):
                self.assertTrue(websearch.is_lookup(text))
        for text in (
            "what is my name?",
            "I am sad",
            "we need help",
            "are you ok?",
            "is that true?",
            "qwertyuiop",
            "what happened?",
            "where do I live?",
            "when do we get paid?",
            "how do you feel?",
            "what do u think?",
            "In January I moved to Paris, what is the best area?",
            "In January I, like many people, moved to Paris; what is the best area?",
            "During the Vietnam War I was exposed to Agent Orange, what cancers does it cause?",
            "Under the Affordable Care Act I pay 500 dollars a month, is that normal?",
            "While studying the Second World War I was diagnosed with diabetes; what causes it?",
            "Under this Act I pay 500 dollars a month, is that normal?",
            "Under this Act I also pay 500 dollars a month, is that normal?",
            "During Stage I noticed a lump, what does it mean?",
            "Since World War I have lived in London, what changed?",
            "Which Stage I am in?",
        ):
            with self.subTest(text=text):
                self.assertFalse(websearch.is_lookup(text))
        self.assertTrue(websearch.is_lookup("blockchain", require_question=False))

    def test_search_terms(self):
        self.assertEqual(websearch.search_terms("Hey Jarvis, can you tell me who invented the telephone?"), "invented the telephone")
        self.assertEqual(websearch.search_terms("what's the capital of Burkina Faso?"), "the capital of Burkina Faso")
        self.assertEqual(websearch.search_terms("how do I tie a tie?"), "how to tie a tie")
        self.assertEqual(websearch.search_terms("Thanks, who invented the telephone?"), "invented the telephone")
        self.assertLessEqual(len(websearch.search_terms("why " + "word " * 100)), websearch.MAX_QUERY_CHARS)


class AssistantWebTests(CleanEnvTestCase):
    def assistant(self, mode="auto", memory=None, notes=None):
        return Assistant(
            memory=memory or Memory(None),
            web_search=mode,
            notify=None if notes is None else notes.append,
        )

    def test_auto_mode_answers_unknown_questions_with_sources(self):
        search = fake_search()
        notes = []
        with mock.patch("jarvis.websearch.search", search):
            reply = self.assistant(notes=notes).respond("Who invented the telephone?")
        self.assertEqual(search.calls, ["invented the telephone"])
        self.assertEqual(notes, ["(searching Wikipedia for 'invented the telephone'...)"])
        self.assertTrue(reply.startswith("I searched Wikipedia for 'invented the telephone'. Here is a summary:"))
        self.assertIn("Sources:\n[1] Invention of the telephone - https://en.wikipedia.org/wiki/Invention_of_the_telephone", reply)
        self.assertIn("Say 'tell me more', 'sources' or 'learn that'.", reply)

    def test_follow_ups_continue_list_and_learn_the_answer(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            memory = Memory(path)
            assistant = self.assistant(memory=memory)
            with mock.patch("jarvis.websearch.search", fake_search()):
                first = assistant.respond("who invented the telephone?")
                more = assistant.respond("tell me more")
                sources = assistant.respond("sources")
                learned = assistant.respond("learn that")
            self.assertIn("Many inventors worked", first)
            self.assertNotIn("Many inventors worked", more)
            self.assertIn("Early telephone lines", more)
            self.assertIn("I searched Wikipedia for 'invented the telephone' and found:", sources)
            self.assertIn("[2] Alexander Graham Bell - https://en.wikipedia.org/wiki/Alexander_Graham_Bell", sources)
            self.assertIn("Learned the answer and 2 page(s)", learned)
            self.assertNotIn(WEB_STATE, path.read_text(encoding="utf-8"))

            offline = self.assistant(mode="off", memory=Memory(path))
            with mock.patch("jarvis.websearch.search", side_effect=AssertionError("went online")):
                answer = offline.respond("who invented the telephone?")
            self.assertTrue(answer.startswith("From what I learned searching Wikipedia for 'invented the telephone':"))
            self.assertIn("Many inventors worked", answer)
            self.assertIn("Early telephone lines", answer)

    def test_learned_answers_survive_when_the_pages_do_not_mention_the_question(self):
        sun = websearch.Document("Sun", "https://en.wikipedia.org/wiki/Sun", "It formed about 4.6 billion years ago.")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            assistant = self.assistant(memory=Memory(path))
            with mock.patch("jarvis.websearch.search", fake_search([sun])):
                self.assertIn("4.6 billion", assistant.respond("How old is the Sun?"))
                self.assertIn("Learned the answer and 1 page(s)", assistant.respond("learn that"))
            offline = self.assistant(mode="off", memory=Memory(path))
            with mock.patch("jarvis.websearch.search", side_effect=AssertionError("went online")):
                self.assertIn("It formed about 4.6 billion years ago. [1]", offline.respond("how old is the sun"))
                self.assertIn("1 answer(s) from web searches", offline.respond("list my knowledge sources"))
                self.assertEqual(
                    offline.respond("clear my knowledge sources"),
                    "Forgot 1 knowledge source(s) and 1 saved web answer(s).",
                )
                self.assertEqual(offline.respond("how old is the sun"), FALLBACK_RESPONSE)

    def test_more_only_continues_right_after_a_web_answer(self):
        assistant = self.assistant(mode="manual")
        with mock.patch("jarvis.websearch.search", fake_search()):
            assistant.respond("search the web for the telephone")
            assistant.respond("what time is it?")
            self.assertIn("Tell me what you would like to know more about", assistant.respond("tell me more"))
        self.assertIn("did not come from the web", assistant.respond("sources"))

    def test_auto_mode_tell_me_more_does_not_search_a_signal_command(self):
        assistant = self.assistant(mode="auto")
        search = fake_search()
        with mock.patch("jarvis.websearch.search", search):
            assistant.respond("signal +15551234567: who won the game?")
            reply = assistant.respond("tell me more")
        self.assertEqual(search.calls, [])
        self.assertIn("Tell me what you would like to know more about", reply)

    def test_manual_mode_suggests_looking_it_up(self):
        search = fake_search()
        assistant = self.assistant(mode="manual")
        with mock.patch("jarvis.websearch.search", search):
            self.assertEqual(
                assistant.respond("who invented the telephone?"),
                "I do not know that offline. Say 'look it up' to search the web for it.",
            )
            self.assertEqual(search.calls, [])
            reply = assistant.respond("look it up")
        self.assertEqual(search.calls, ["invented the telephone"])
        self.assertIn("Here is a summary:", reply)

    def test_off_mode_keeps_the_old_fallback(self):
        assistant = self.assistant(mode="off")
        with mock.patch("jarvis.websearch.search", side_effect=AssertionError("went online")):
            self.assertEqual(assistant.respond("who invented the telephone?"), FALLBACK_RESPONSE)
            self.assertIn("Web search is turned off", assistant.respond("search the web for llamas"))
            self.assertNotIn("look it up", assistant.respond("what is blockchain?"))

    def test_personal_messages_and_crisis_are_never_searched(self):
        assistant = self.assistant()
        with mock.patch("jarvis.websearch.search", side_effect=AssertionError("went online")):
            self.assertEqual(assistant.respond("we need help"), FALLBACK_RESPONSE)
            self.assertEqual(assistant.respond("where did I park my car?"), FALLBACK_RESPONSE)
            reply = assistant.respond("search the web for how to kill myself")
        self.assertNotIn("searched", reply)
        self.assertIn("988", reply)

    def test_self_harm_questions_are_not_searched_even_when_asked_again(self):
        for mode in ("auto", "manual"):
            assistant = self.assistant(mode=mode)
            with mock.patch("jarvis.websearch.search", side_effect=AssertionError("went online")):
                for message in (
                    "I want to end my life",
                    "look it up",
                    "is suicide painful?",
                    "tell me more",
                    "what is the most painless way to die?",
                    "what is a lethal dose of paracetamol?",
                    "how 2 kill urself",
                    "look it up",
                ):
                    with self.subTest(mode=mode, message=message):
                        reply = assistant.respond(message)
                        self.assertIn("988", reply)
                        self.assertNotIn("look it up", reply)
        search = fake_search()
        with mock.patch("jarvis.websearch.search", search):
            self.assistant().respond("how did Hitler die?")
        self.assertEqual(search.calls, ["Hitler die"])

    def test_encyclopedia_gaps_are_looked_up(self):
        with mock.patch("jarvis.websearch.search", fake_search()) as search:
            reply = self.assistant().respond("what is the telephone exchange?")
            self.assertIn("Here is a summary:", reply)
            manual = self.assistant(mode="manual").respond("what is blockchain?")
        self.assertEqual(search.calls, ["the telephone exchange"])
        self.assertIn("do not have an encyclopedia entry for 'blockchain'", manual)
        self.assertTrue(manual.endswith("Say 'look it up' to search the web for it."))

    def test_search_failures_are_explained(self):
        failure = websearch.WebSearchError("Wikipedia could not be reached (timed out).")
        with mock.patch("jarvis.websearch.search", side_effect=failure):
            reply = self.assistant().respond("who invented the telephone?")
        self.assertEqual(
            reply,
            "I do not know that offline. I could not search the web. Wikipedia could not be reached (timed out).",
        )

    def test_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            Assistant(memory=Memory(None), web_search="always")


class CliWebSearchTests(CleanEnvTestCase):
    def run_cli(self, argv, env=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        search = fake_search()
        with mock.patch.dict(os.environ, env or {}), mock.patch("jarvis.websearch.search", search):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--no-memory", *argv])
        return code, stdout.getvalue(), stderr.getvalue(), search.calls

    def test_searches_automatically_by_default(self):
        code, out, err, calls = self.run_cli(["who invented the telephone?"])
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["invented the telephone"])
        self.assertIn("Here is a summary:", out)
        self.assertIn("(searching Wikipedia for 'invented the telephone'...)", err)
        self.assertNotIn("searching", out)

    def test_flag_and_environment_choose_the_mode(self):
        _, out, _, calls = self.run_cli(["--web-search", "off", "who invented the telephone?"])
        self.assertEqual((out.strip(), calls), (FALLBACK_RESPONSE, []))
        _, out, _, calls = self.run_cli(["who invented the telephone?"], {"JARVIS_WEB_SEARCH": "manual"})
        self.assertIn("Say 'look it up'", out)
        self.assertEqual(calls, [])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cli(["hi"], {"JARVIS_WEB_SEARCH": "sometimes"})


@unittest.skipUnless(
    os.environ.get("JARVIS_LIVE_WEB_TESTS") == "1",
    "set JARVIS_LIVE_WEB_TESTS=1 to search the real web",
)
class LiveWebSearchTests(CleanEnvTestCase):
    def test_wikipedia_answers_a_question(self):
        results = websearch.search("invention of the telephone", environ={})
        self.assertTrue(results.documents)
        reply = Assistant(memory=Memory(None), web_search="auto").respond("who invented the telephone?")
        self.assertIn("Here is a summary:", reply)
        self.assertIn("wikipedia.org/wiki/", reply)


if __name__ == "__main__":
    unittest.main()
