import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from project_support import ProjectTestCase, missing_projects

from jarvis import projects


def _reply(body, returncode=0, stderr=""):
    stdout = body if isinstance(body, str) else json.dumps(body) + "\n"
    return subprocess.CompletedProcess(["node"], returncode, stdout=stdout, stderr=stderr)


class FakeCheckoutTestCase(unittest.TestCase):
    """Projects in a temporary folder that has only each project's marker file."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for project in projects.PROJECTS.values():
            marker = self.root / project.name / project.marker
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("{}", encoding="utf-8")
        environ = mock.patch.dict(os.environ, {"JARVIS_PROJECTS_DIR": str(self.root), "JARVIS_NODE": "node"})
        environ.start()
        self.addCleanup(environ.stop)

    def run_node(self, **kwargs):
        patcher = mock.patch.object(projects.subprocess, "run", **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()


class CallTests(FakeCheckoutTestCase):
    def test_sends_the_request_and_returns_the_result(self):
        run = self.run_node(return_value=_reply('noise\n{"ok": true, "result": {"answer": 42}}\n'))
        self.assertEqual(projects.call("workout", "program", {"x": 1}), {"answer": 42})
        command, request = run.call_args.args[0], json.loads(run.call_args.kwargs["input"])
        self.assertEqual(command[0], "node")
        self.assertTrue(command[-1].endswith("run.mjs"))
        self.assertEqual(request["project"], "workout")
        self.assertEqual(request["action"], "program")
        self.assertEqual(request["payload"], {"x": 1})
        self.assertEqual(Path(request["root"]), (self.root / "workout").resolve())

    def test_a_failure_in_the_project_is_a_project_error(self):
        self.run_node(return_value=_reply({"ok": False, "error": {"kind": "failed", "message": "boom"}}, 1))
        with self.assertRaisesRegex(projects.ProjectError, "workout failed: boom"):
            projects.call("workout", "program")

    def test_output_that_is_not_a_reply_is_a_project_error(self):
        self.run_node(return_value=_reply("not json\n", 1, stderr="SyntaxError: bad\n"))
        with self.assertRaisesRegex(projects.ProjectError, "SyntaxError: bad"):
            projects.call("workout", "program")

    def test_too_slow_is_a_project_error(self):
        self.run_node(side_effect=subprocess.TimeoutExpired("node", 2))
        with self.assertRaisesRegex(projects.ProjectError, "longer than 2 seconds"):
            projects.call("workout", "program", timeout=2)

    def test_old_or_missing_node_is_unavailable_with_setup_steps(self):
        self.run_node(return_value=_reply({"ok": False, "error": {"kind": "node-too-old", "message": "this is v20.1.0"}}, 1))
        with self.assertRaisesRegex(projects.ProjectUnavailable, r"needs Node\.js 22\.18 or newer, but this is v20\.1\.0"):
            projects.call("tax-break", "meta")
        self.run_node(side_effect=FileNotFoundError(2, "No such file or directory"))
        with self.assertRaisesRegex(projects.ProjectUnavailable, "Node.js could not be started"):
            projects.call("tax-break", "meta")
        with mock.patch.dict(os.environ, {"JARVIS_NODE": ""}), mock.patch.object(projects.shutil, "which", return_value=None):
            with self.assertRaisesRegex(projects.ProjectUnavailable, "isn't installed"):
                projects.call("tax-break", "meta")

    def test_a_missing_checkout_says_how_to_get_it(self):
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            projects.call("OpenTrading", "summary")
        message = str(raised.exception)
        self.assertIn("git submodule update --init projects/OpenTrading", message)
        self.assertIn("Node.js 22.18 or newer", message)
        self.assertIn(projects.PROJECTS["OpenTrading"].site, message)


class ReadJsonTests(FakeCheckoutTestCase):
    def test_reads_inside_the_checkout_only(self):
        data = self.root / "beat-it" / "site" / "data" / "facts.json"
        data.write_text('{"a": 1}', encoding="utf-8")
        self.assertEqual(projects.read_json("beat-it", "site/data/facts.json"), {"a": 1})
        with self.assertRaises(ValueError):
            projects.read_json("beat-it", "../workout/workout.js")
        with self.assertRaisesRegex(projects.ProjectError, "beat-it has no site/data/faq.json"):
            projects.read_json("beat-it", "site/data/faq.json")
        data.write_text("{", encoding="utf-8")
        with self.assertRaises(projects.ProjectError):
            projects.read_json("beat-it", "site/data/facts.json")

    def test_beat_it_needs_no_node(self):
        with mock.patch.dict(os.environ, {"JARVIS_NODE": "/no/such/node"}):
            projects.check("beat-it")
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            projects.check("beat-it")
        self.assertNotIn("Node.js", str(raised.exception))


class RunnerTests(ProjectTestCase):
    """The real runner, with Node.js and the workout checkout."""

    project = "workout"

    def test_ping_and_an_unknown_action(self):
        self.assertRegex(projects.call("workout", "ping")["node"], r"^v\d+\.")
        with self.assertRaisesRegex(projects.ProjectError, "workout has no action nonsense"):
            projects.call("workout", "nonsense")


if __name__ == "__main__":
    unittest.main()
