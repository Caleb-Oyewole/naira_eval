import unittest

from evalkit.graders import grade, parse_number, parse_response, within

NUMERIC = {
    "id": "t", "traps": [{"name": "common_slip", "wrong_answer": 3}],
    "grader": {"type": "numeric", "answer": 4, "tolerance": {"abs": 0}},
}
PERCENT = {
    "id": "p", "traps": [],
    "grader": {"type": "numeric", "answer": 766.3, "tolerance": {"rel": 0.02}},
}
ABSTAIN = {
    "id": "a", "traps": [{"name": "assumed_annual", "wrong_answer": 560000}],
    "grader": {"type": "abstain", "must_mention_any": [r"\b(tenor|how long|maturity)\b", r"per\s+(year|month)"]},
}


class ParseNumber(unittest.TestCase):
    def test_formats(self):
        cases = {
            "901,474": 901474.0,
            "₦901,474.50": 901474.5,
            "**N1,162,000**": 1162000.0,
            "776%": 776.0,
            "-12.5": -12.5,
            "−12.5": -12.5,
            "4 batteries": 4.0,
            "1.5 million": 1500000.0,
            "2 Billion naira": 2e9,
            "4, because the load is high": 4.0,
            ".5": 0.5,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_number(text), want)

    def test_no_number(self):
        self.assertIsNone(parse_number("<one number only: no units, no words>"))
        self.assertIsNone(parse_number("about right"))

    def test_space_before_digit_is_not_a_minus_sign(self):
        self.assertEqual(parse_number("- 4"), 4.0)


class ParseResponse(unittest.TestCase):
    def test_last_final_line_wins(self):
        r = parse_response("FINAL ANSWER: 1\nrechecking\nFINAL ANSWER: 4")
        self.assertEqual((r["kind"], r["value"]), ("answer", 4.0))

    def test_bold_markdown(self):
        r = parse_response("**FINAL ANSWER:** ₦901,474")
        self.assertEqual(r["value"], 901474.0)

    def test_case_insensitive(self):
        self.assertEqual(parse_response("final answer: 7")["value"], 7.0)

    def test_need_info_after_answer_wins_and_vice_versa(self):
        r = parse_response("FINAL ANSWER: 5\nNEED MORE INFO: the tenor")
        self.assertEqual(r["kind"], "need_info")
        r = parse_response("NEED MORE INFO: the tenor\nFINAL ANSWER: 5")
        self.assertEqual(r["kind"], "answer")

    def test_echoed_template_is_unparsable_not_a_number(self):
        r = parse_response("FINAL ANSWER: <one number only: no units, no words>")
        self.assertEqual(r["kind"], "unparsable")

    def test_none(self):
        self.assertEqual(parse_response("I think it is about 4")["kind"], "none")
        self.assertEqual(parse_response("")["kind"], "none")


class Tolerance(unittest.TestCase):
    def test_abs_and_rel_boundaries(self):
        self.assertTrue(within(4, 4, {"abs": 0}))
        self.assertFalse(within(4.01, 4, {"abs": 0}))
        self.assertTrue(within(102.0, 100, {"rel": 0.02}))
        self.assertFalse(within(102.1, 100, {"rel": 0.02}))
        self.assertTrue(within(447.254, 447.25, {"abs": 0.005}))
        self.assertFalse(within(447.26, 447.25, {"abs": 0.005}))


class NumericGrader(unittest.TestCase):
    def test_pass(self):
        g = grade(NUMERIC, "FINAL ANSWER: 4")
        self.assertTrue(g["passed"])
        self.assertIsNone(g["failure_kind"])

    def test_wrong_answer_names_the_trap(self):
        g = grade(NUMERIC, "FINAL ANSWER: 3")
        self.assertFalse(g["passed"])
        self.assertEqual(g["failure_kind"], "wrong_answer")
        self.assertEqual(g["diagnosis"], ["common_slip"])

    def test_wrong_answer_matching_no_trap_has_empty_diagnosis(self):
        g = grade(NUMERIC, "FINAL ANSWER: 9")
        self.assertEqual((g["failure_kind"], g["diagnosis"]), ("wrong_answer", []))

    def test_scale_error_detected(self):
        g = grade(PERCENT, "FINAL ANSWER: 7.663")
        self.assertFalse(g["passed"])
        self.assertIn("scale_error_x100", g["diagnosis"])

    def test_unnecessary_abstain(self):
        g = grade(NUMERIC, "NEED MORE INFO: everything")
        self.assertEqual(g["failure_kind"], "unnecessary_abstain")

    def test_missing_and_unreadable_final_line(self):
        self.assertEqual(grade(NUMERIC, "it is 4")["failure_kind"], "no_final_answer")
        self.assertEqual(grade(NUMERIC, "FINAL ANSWER: four")["failure_kind"], "unparsable_answer")

    def test_percent_tolerance(self):
        self.assertTrue(grade(PERCENT, "FINAL ANSWER: 780%")["passed"])
        self.assertFalse(grade(PERCENT, "FINAL ANSWER: 800")["passed"])


class AbstainGrader(unittest.TestCase):
    def test_good_clarification_passes(self):
        self.assertTrue(grade(ABSTAIN, "NEED MORE INFO: how long is the plan?")["passed"])
        self.assertTrue(grade(ABSTAIN, "NEED MORE INFO: is 12% per month?")["passed"])

    def test_vague_clarification_fails(self):
        g = grade(ABSTAIN, "NEED MORE INFO: more details please")
        self.assertEqual(g["failure_kind"], "vague_clarification")

    def test_confident_answer_fails_and_is_diagnosed(self):
        g = grade(ABSTAIN, "Assuming one year.\nFINAL ANSWER: 560000")
        self.assertEqual(g["failure_kind"], "answered_instead_of_asking")
        self.assertEqual(g["diagnosis"], ["assumed_annual"])


if __name__ == "__main__":
    unittest.main()
