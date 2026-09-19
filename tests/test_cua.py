import unittest
from unittest import mock

from jarvis.assistant import Assistant
from jarvis.cua import Action, CuaError, actions_chart, backend_command, execute, is_enabled, plan
from jarvis.memory import Memory


class PlanTests(unittest.TestCase):
    def test_plans_a_multi_step_instruction(self):
        parsed = plan("open Safari then click on the Save button and type hello")
        self.assertEqual(
            [action.kind for action in parsed.actions],
            ["open", "click", "type"],
        )
        self.assertEqual(parsed.actions[0].target, "Safari")
        self.assertEqual(parsed.actions[1].target, "Save button")
        self.assertEqual(parsed.actions[2].value, "hello")

    def test_plans_every_action_kind(self):
        cases = {
            "go to example.com": "open",
            "double click the report": "double_click",
            "right click the desktop": "right_click",
            "move the mouse to the menu bar": "move",
            "drag report.pdf to the bin": "drag",
            'type "hello there" into the search box': "type",
            "press ctrl+s": "key",
            "scroll down 5": "scroll",
            "wait 2 seconds": "wait",
            "take a screenshot": "screenshot",
        }
        for instruction, kind in cases.items():
            with self.subTest(instruction=instruction):
                parsed = plan(instruction)
                self.assertEqual(len(parsed), 1)
                self.assertEqual(parsed.actions[0].kind, kind)

    def test_typing_keeps_quoted_text_and_target(self):
        action = plan('type "hello there" into the search box').actions[0]
        self.assertEqual(action.value, "hello there")
        self.assertEqual(action.target, "search box")

    def test_scroll_and_wait_have_defaults(self):
        self.assertEqual(plan("scroll down").actions[0].value, "3")
        self.assertEqual(plan("wait").actions[0].value, "1")

    def test_summary_numbers_every_step(self):
        summary = plan("open Mail and press enter").summary()
        self.assertIn("1. open Mail", summary)
        self.assertIn("2. press enter", summary)

    def test_rejects_empty_instruction(self):
        with self.assertRaises(CuaError):
            plan("   ")

    def test_reports_the_step_it_could_not_read(self):
        with self.assertRaises(CuaError) as caught:
            plan("open Mail then teleport to Mars")
        self.assertIn("teleport to Mars", str(caught.exception))
        self.assertIn("first 1 step", str(caught.exception))

    def test_action_arguments_feed_the_backend(self):
        self.assertEqual(Action("click", target="Save").arguments(), ("click", "Save"))
        self.assertEqual(Action("screenshot").arguments(), ("screenshot",))


class ExecutionTests(unittest.TestCase):
    def test_is_enabled_reads_the_environment(self):
        self.assertTrue(is_enabled({"JARVIS_CUA_ENABLED": "1"}))
        self.assertTrue(is_enabled({"JARVIS_CUA_ENABLED": "Yes"}))
        self.assertFalse(is_enabled({"JARVIS_CUA_ENABLED": "0"}))
        self.assertFalse(is_enabled({}))

    def test_backend_command_is_split(self):
        self.assertEqual(
            backend_command({"JARVIS_CUA_COMMAND": "cua-tool --device screen"}),
            ["cua-tool", "--device", "screen"],
        )

    def test_backend_command_requires_configuration(self):
        with self.assertRaises(CuaError):
            backend_command({})

    def test_execute_only_plans_when_not_enabled(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            reply = execute("open Safari")
        self.assertIn("Computer use plan for: open Safari", reply)
        self.assertIn("JARVIS_CUA_ENABLED", reply)

    def test_execute_runs_every_action_with_a_runner(self):
        seen = []

        def runner(action):
            seen.append(action.kind)
            return "ok"

        reply = execute("open Safari then press enter", runner=runner)
        self.assertEqual(seen, ["open", "key"])
        self.assertIn("1. open Safari — ok", reply)
        self.assertIn("2. press enter — ok", reply)

    def test_actions_chart_lists_the_known_actions(self):
        chart = actions_chart()
        self.assertIn("- click:", chart)
        self.assertIn("- screenshot:", chart)


class ComputerUseSkillTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant(memory=Memory(path=None))

    def test_skill_plans_without_touching_the_computer(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            reply = self.assistant.respond("use the computer to open Safari and click on Sign in")
        self.assertIn("1. open Safari", reply)
        self.assertIn("2. click Sign in", reply)

    def test_cua_prefix_routes_to_the_skill(self):
        resolved = self.assistant.registry.resolve("cua open Mail")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[0].name, "computer-use")

    def test_unknown_step_is_reported_kindly(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            reply = self.assistant.respond("use the computer to teleport to Mars")
        self.assertIn("I could not use the computer", reply)

    def test_actions_skill_lists_actions(self):
        reply = self.assistant.respond("computer use actions")
        self.assertIn("computer use actions", reply)
        self.assertIn("- type:", reply)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
