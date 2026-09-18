import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from jarvis.cli import main
from jarvis.memory import Memory


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
        import io
        from contextlib import redirect_stdout

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["--no-memory", "calculate", "2", "+", "2"])
        self.assertEqual(exit_code, 0)
        self.assertIn("= 4", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
