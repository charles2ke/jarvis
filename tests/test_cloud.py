import json
import unittest
from unittest import mock

from jarvis.assistant import Assistant
from jarvis.cloud import CloudSession, CloudSessionError, detect_repository, spawn_session
from jarvis.memory import Memory


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class CloudSessionTests(unittest.TestCase):
    def test_detect_repository_prefers_environment(self):
        with mock.patch.dict("os.environ", {"JARVIS_GITHUB_REPO": "charles2ke/jarvis"}):
            self.assertEqual(detect_repository(), "charles2ke/jarvis")

    def test_detect_repository_falls_back_to_https_origin_remote(self):
        fake_result = mock.Mock(stdout="https://github.com/charles2ke/jarvis.git\n")
        env = {}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch(
            "subprocess.run", return_value=fake_result
        ) as run:
            self.assertEqual(detect_repository(), "charles2ke/jarvis")
        run.assert_called_once()

    def test_detect_repository_falls_back_to_ssh_origin_remote(self):
        fake_result = mock.Mock(stdout="git@github.com:charles2ke/jarvis.git\n")
        env = {}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch(
            "subprocess.run", return_value=fake_result
        ):
            self.assertEqual(detect_repository(), "charles2ke/jarvis")

    def test_detect_repository_reports_unparseable_remote(self):
        fake_result = mock.Mock(stdout="not-a-github-url\n")
        env = {}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch(
            "subprocess.run", return_value=fake_result
        ):
            with self.assertRaises(CloudSessionError):
                detect_repository()

    def test_detect_repository_reports_missing_git(self):
        env = {}
        with mock.patch.dict("os.environ", env, clear=True), mock.patch(
            "subprocess.run", side_effect=OSError("no git")
        ):
            with self.assertRaises(CloudSessionError):
                detect_repository()

    def test_spawn_session_posts_query_and_model(self):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["auth"] = request.headers["Authorization"]
            return FakeResponse({"session_id": "abc123", "html_url": "https://example.test/1"})

        env = {"JARVIS_GITHUB_REPO": "charles2ke/jarvis", "JARVIS_GITHUB_TOKEN": "t0ken"}
        with mock.patch.dict("os.environ", env, clear=False), mock.patch(
            "urllib.request.urlopen", fake_urlopen
        ):
            session = spawn_session("why is the sky blue?")

        self.assertEqual(session.repository, "charles2ke/jarvis")
        self.assertEqual(session.session_id, "abc123")
        self.assertEqual(session.url, "https://example.test/1")
        self.assertEqual(captured["body"]["problem_statement"], "why is the sky blue?")
        self.assertEqual(captured["body"]["model"], "claude-opus-5")
        self.assertEqual(captured["body"]["reasoning_effort"], "max")
        self.assertIn("charles2ke/jarvis", captured["url"])
        self.assertEqual(captured["auth"], "Bearer " + "t0ken")

    def test_spawn_session_prefers_session_url(self):
        env = {"JARVIS_GITHUB_REPO": "charles2ke/jarvis", "JARVIS_GITHUB_TOKEN": "t0ken"}
        with mock.patch.dict("os.environ", env, clear=False), mock.patch(
            "urllib.request.urlopen",
            lambda request, timeout=None: FakeResponse(
                {
                    "session_id": "abc123",
                    "session_url": "https://example.test/session/abc123",
                    "html_url": "https://example.test/1",
                }
            ),
        ):
            session = spawn_session("why is the sky blue?")

        self.assertEqual(session.url, "https://example.test/session/abc123")

    def test_spawn_session_requires_a_query(self):
        with self.assertRaises(CloudSessionError):
            spawn_session("   ")

    def test_spawn_session_requires_a_token(self):
        env = {"JARVIS_GITHUB_REPO": "charles2ke/jarvis"}
        with mock.patch.dict("os.environ", env, clear=True):
            with self.assertRaises(CloudSessionError):
                spawn_session("hello?")

    def test_spawn_session_rejects_non_object_response(self):
        env = {"JARVIS_GITHUB_REPO": "charles2ke/jarvis", "JARVIS_GITHUB_TOKEN": "t0ken"}
        with mock.patch.dict("os.environ", env, clear=False), mock.patch(
            "urllib.request.urlopen", lambda request, timeout=None: FakeResponse(None)
        ):
            with self.assertRaises(CloudSessionError):
                spawn_session("why is the sky blue?")

    def test_summary_mentions_model_and_link(self):
        summary = CloudSession(
            repository="charles2ke/jarvis",
            model="claude-opus-5",
            query="what is this repo?",
            session_id="abc",
            url="https://example.test/1",
        ).summary()
        self.assertIn("claude-opus-5", summary)
        self.assertIn("max", summary)
        self.assertIn("https://example.test/1", summary)


class AnswerSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant(memory=Memory(None))

    def test_answer_skill_spawns_a_cloud_session(self):
        with mock.patch("jarvis.skills.ask_cloud", return_value="spawned") as spawn:
            reply = self.assistant.respond("answer how does the registry resolve skills?")
        spawn.assert_called_once_with("how does the registry resolve skills?")
        self.assertEqual(reply, "spawned")

    def test_alternate_phrasings(self):
        with mock.patch("jarvis.skills.ask_cloud", return_value="spawned") as spawn:
            self.assistant.respond("ask the cloud what does memory.py do?")
            self.assistant.respond("spawn a cloud session on this repo to answer: who wrote it?")
        self.assertEqual(
            [call.args[0] for call in spawn.call_args_list],
            ["what does memory.py do?", "who wrote it?"],
        )

    def test_failure_is_reported_gracefully(self):
        with mock.patch("jarvis.skills.ask_cloud", side_effect=CloudSessionError("no token")):
            reply = self.assistant.respond("answer anything")
        self.assertIn("no token", reply)

    def test_crisis_support_still_wins(self):
        reply = self.assistant.respond("answer me: I want to kill myself")
        self.assertIn("988", reply)


if __name__ == "__main__":
    unittest.main()
