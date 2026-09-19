import unittest

from jarvis.assistant import Assistant
from jarvis.memory import Memory
from jarvis.science import (
    ScienceError,
    molar_mass,
    parse_formula,
    solve_biology,
    solve_chemistry,
    solve_equation,
    solve_physics,
    solve_problem,
)


class EquationTests(unittest.TestCase):
    def test_linear_equation(self):
        answer = solve_equation("solve 2x + 3 = 11")
        self.assertIn("x = 4", answer)

    def test_linear_equation_with_brackets_and_named_variable(self):
        answer = solve_equation("solve 3(y - 2) = 9 for y")
        self.assertIn("y = 5", answer)

    def test_quadratic_with_two_roots(self):
        answer = solve_equation("solve x^2 - 5x + 6 = 0")
        self.assertIn("x = 3", answer)
        self.assertIn("x = 2", answer)

    def test_quadratic_with_repeated_root(self):
        answer = solve_equation("solve x^2 - 4x + 4 = 0")
        self.assertIn("repeated root", answer)

    def test_quadratic_without_real_roots(self):
        answer = solve_equation("solve x^2 + 2x + 5 = 0")
        self.assertIn("no real solutions", answer)

    def test_identity_and_contradiction(self):
        self.assertIn("Every value", solve_equation("solve 2x = 2x"))
        self.assertIn("no value", solve_equation("solve x + 1 = x + 2"))

    def test_two_unknowns_are_declined(self):
        self.assertIsNone(solve_equation("solve 3x + 2y = 6"))

    def test_unsupported_degree_is_reported(self):
        self.assertIn("linear and quadratic", solve_equation("solve x^3 = 8"))

    def test_division_by_zero_is_reported(self):
        self.assertIn("divides by zero", solve_equation("solve x/0 = 2"))

    def test_non_equation_is_ignored(self):
        self.assertIsNone(solve_equation("tell me a story"))


class PhysicsTests(unittest.TestCase):
    def test_force(self):
        answer = solve_physics("calculate the force with mass 5 kg and acceleration 2 m/s^2")
        self.assertIn("F = m a", answer)
        self.assertIn("10 N", answer)

    def test_speed(self):
        answer = solve_physics("how fast is a car that travels 150 m in 10 s")
        self.assertIn("15 m/s", answer)

    def test_kinetic_energy(self):
        answer = solve_physics("what is the kinetic energy of a 3 kg mass moving at 4 m/s")
        self.assertIn("24 J", answer)

    def test_acceleration_is_not_treated_as_speed(self):
        for unit in ("m/s^2", "m/s2", "m/s²"):
            with self.subTest(unit=unit):
                answer = solve_physics(
                    f"what is the kinetic energy of a 3 kg mass moving at 4 {unit}"
                )
                self.assertIn("speed", answer)
                self.assertNotIn("24 J", answer)

    def test_ohms_law(self):
        answer = solve_physics("what is the voltage with current 2 A and resistance 5 ohms")
        self.assertIn("10 V", answer)

    def test_missing_quantity_is_explained(self):
        answer = solve_physics("calculate the force with mass 5 kg for 3 items")
        self.assertIn("acceleration", answer)

    def test_question_without_numbers_is_ignored(self):
        self.assertIsNone(solve_physics("what is force"))


class ChemistryTests(unittest.TestCase):
    def test_parse_formula_with_brackets(self):
        self.assertEqual(parse_formula("Ca(OH)2"), {"Ca": 1, "O": 2, "H": 2})

    def test_molar_mass(self):
        self.assertAlmostEqual(molar_mass("H2O"), 18.015, places=3)

    def test_unknown_element_raises(self):
        with self.assertRaises(ScienceError):
            parse_formula("Xx2")

    def test_unbalanced_brackets_raise(self):
        with self.assertRaises(ScienceError):
            parse_formula("Ca(OH2")

    def test_molar_mass_question(self):
        answer = solve_chemistry("what is the molar mass of Ca(OH)2")
        self.assertIn("74.09", answer)

    def test_moles_question(self):
        answer = solve_chemistry("how many moles are in 36 g of H2O")
        self.assertIn("mol", answer)
        self.assertIn("1.998", answer)

    def test_ph_question(self):
        answer = solve_chemistry("what is the pH of 0.001 M solution")
        self.assertIn("pH = 3.00", answer)

    def test_ideal_gas_law(self):
        answer = solve_chemistry(
            "use the ideal gas law with 2 mol at 300 K and pressure 1 atm"
        )
        self.assertIn("volume", answer)
        self.assertIn("49.2", answer)

    def test_unrelated_question_is_ignored(self):
        self.assertIsNone(solve_chemistry("tell me a joke"))


class BiologyTests(unittest.TestCase):
    def test_complement(self):
        self.assertIn("TACG", solve_biology("what is the complement of ATGC"))

    def test_reverse_complement(self):
        self.assertIn("GGCAT", solve_biology("reverse complement of ATGCC"))

    def test_transcription(self):
        self.assertIn("AUGC", solve_biology("transcribe ATGC"))

    def test_translation(self):
        answer = solve_biology("translate the RNA sequence AUGGCCUAA")
        self.assertIn("MA*", answer)

    def test_gc_content(self):
        self.assertIn("66.7%", solve_biology("gc content of ATGCGC"))

    def test_punnett_square(self):
        answer = solve_biology("punnett square for Aa x Aa")
        self.assertIn("Aa 2/4", answer)
        self.assertIn("3/4 dominant", answer)

    def test_mixed_sequence_is_rejected(self):
        self.assertIn("mixes T and U", solve_biology("complement of ATGU"))

    def test_unrelated_question_is_ignored(self):
        self.assertIsNone(solve_biology("how are you"))


class ScienceSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant(memory=Memory(None))

    def test_skill_answers_equation(self):
        self.assertIn("x = 4", self.assistant.respond("solve 2x + 3 = 11"))

    def test_skill_answers_chemistry(self):
        self.assertIn(
            "g/mol", self.assistant.respond("what is the molar mass of Ca(OH)2")
        )

    def test_skill_answers_biology(self):
        self.assertIn("TACG", self.assistant.respond("what is the complement of ATGC"))

    def test_skill_offers_help_when_unsure(self):
        self.assertIn(
            "maths, physics, chemistry and biology",
            self.assistant.respond("solve 3x + 2y = 6"),
        )

    def test_calculator_still_wins_plain_arithmetic(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")

    def test_time_skill_is_not_hijacked(self):
        self.assertTrue(self.assistant.respond("what is the current time").startswith("It is"))

    def test_solve_problem_returns_none_for_chitchat(self):
        self.assertIsNone(solve_problem("hello there"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
