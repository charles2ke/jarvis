import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from jarvis.cli import main
from jarvis.memory import Memory


def run_cli(argv, stdin=None):
    buffer = io.StringIO()
    patched = io.StringIO(stdin) if stdin is not None else None
    with redirect_stdout(buffer):
        if patched is None:
            exit_code = main(argv)
        else:
            with mock.patch("jarvis.cli.sys.stdin", patched):
                exit_code = main(argv)
    return exit_code, buffer.getvalue()


class MemoryTests(unittest.TestCase):
    def test_in_memory_mode_writes_nothing(self):
        memory = Memory(None)
        memory.set("user_name", "Charles")
        self.assertEqual(memory.get("user_name"), "Charles")

    def test_persists_and_reloads(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "memory.json"
            memory = Memory(path)
            memory.append("notes", "buy milk")
            self.assertEqual(json.loads(path.read_text())["notes"], ["buy milk"])
            self.assertEqual(Memory(path).get("notes"), ["buy milk"])

    def test_corrupt_file_is_ignored(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            path.write_text("not json")
            self.assertEqual(Memory(path).get("notes", []), [])

    def test_clear_all(self):
        memory = Memory(None)
        memory.set("a", 1)
        memory.clear()
        self.assertIsNone(memory.get("a"))


class CliTests(unittest.TestCase):
    def test_one_shot_message(self):
        exit_code, output = run_cli(["--no-memory", "calculate", "2", "+", "2"])
        self.assertEqual(exit_code, 0)
        self.assertIn("= 4", output)

    def test_single_piped_line_is_answered_like_one_shot(self):
        exit_code, output = run_cli(["--no-memory"], stdin="calculate 2 + 2\n")
        self.assertEqual(exit_code, 0)
        self.assertEqual(output.strip(), "2 + 2 = 4")

    def test_multiple_piped_lines_run_as_a_session(self):
        exit_code, output = run_cli(
            ["--no-memory"], stdin="calculate 2 + 2\ncalculate 3 + 3\nexit\n"
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("jarvis> 2 + 2 = 4", output)
        self.assertIn("jarvis> 3 + 3 = 6", output)
        self.assertTrue(output.rstrip().endswith("jarvis> Goodbye."))

    def test_list_skills(self):
        exit_code, output = run_cli(["--list-skills"])
        self.assertEqual(exit_code, 0)
        self.assertIn("calculator:", output)


if __name__ == "__main__":
    unittest.main()
