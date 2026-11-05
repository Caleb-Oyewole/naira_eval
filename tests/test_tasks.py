"""Checks the eight tasks against INDEPENDENT re-computations.

The keys in tasks.json come from tasks/build_tasks.py. These tests deliberately
re-derive each answer a different way (Decimal loops, Fraction arithmetic,
verifying the key by substitution) so one bug cannot hide in both places.
"""
import importlib.util
import math
import re
import unittest
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path

from evalkit.graders import within
from evalkit.tasks import VARIANTS, build_prompt, expand_cases, load_tasks, validate_tasks

ROOT = Path(__file__).resolve().parent.parent
TASKS = {t["id"]: t for t in load_tasks(ROOT / "tasks" / "tasks.json")}


def key(task_id):
    return TASKS[task_id]["grader"]["answer"]


class GoldValues(unittest.TestCase):
    def test_ear_key_satisfies_the_definition(self):
        # Substitute the key back: derive the weekly rate from the EAR, then the
        # eight 9,000 repayments must be worth 60,000 today.
        ear = key("ear_instalment_loan")
        r = (1 + ear / 100) ** (1 / 52) - 1
        pv = sum(9000 / (1 + r) ** week for week in range(1, 9))
        self.assertAlmostEqual(pv, 60000, delta=0.01)

    def test_ear_key_is_not_any_of_the_shortcuts(self):
        self.assertGreater(key("ear_instalment_loan"), 700)  # flat 130, nominal 220, total 20

    def test_bank_charges_by_independent_loop(self):
        # (amount, charged?) typed out again here, not imported.
        charged = [4500, 5000, 5001, 10000, 9999, 50000, 50001, 120000, 2000]
        exempt = [30000, 15000, 8000]  # own-bank, reversed, card payment
        self.assertEqual(len(charged) + len(exempt), 12)
        fees = D(0)
        for a in charged:
            if a <= 5000:
                fees += 10
            elif a <= 50000:
                fees += 25
            else:
                fees += 50
        stamp = D(50) * sum(1 for a in charged if a >= 10000)
        vat = fees * D("0.075")
        self.assertEqual((fees, stamp, vat), (D(230), D(200), D("17.25")))
        self.assertEqual(float(fees + stamp + vat), key("bank_charges_schedule"))

    def test_landed_cost_by_independent_steps(self):
        usd = D(2400 + 350 + 50)
        cif = usd * 1500
        duty = cif * D("0.2")
        surcharge = duty * D("0.07")
        levy = cif * D("0.04")
        vat = (cif + duty + surcharge + levy) * D("0.075")
        agent = cif * D("0.015")
        total = usd * 1620 + duty + surcharge + levy + vat + agent + 85000
        self.assertEqual(vat, D("395010"))
        self.assertEqual(total, D("6145810"))
        self.assertEqual(float(total), key("landed_cost_two_rates"))

    def test_real_value_with_exact_fractions(self):
        balance = F(1_000_000) + F(1_000_000) * F(18, 100) * (1 - F(10, 100))
        self.assertEqual(balance, 1_162_000)
        real = balance / F(1289, 1000)
        self.assertAlmostEqual(float(real), key("real_value_after_wht_inflation"), places=3)
        self.assertEqual(round(real), 901_474)

    def test_battery_count_with_exact_fractions(self):
        wh = 3 * 10 * 5 + 120 * 12 + 80 * 6 + 60 * 8 + 70 * 5
        self.assertEqual(wh, 2900)
        supply = F(wh) / F(9, 10)
        usable = F(128, 10) * 100 * F(8, 10)
        self.assertEqual(usable, 1024)
        self.assertEqual(math.ceil(supply / usable), 4)
        self.assertEqual(key("solar_battery_sizing"), 4)
        # each shortcut really lands on a different integer
        self.assertEqual(math.ceil(F(wh) / usable), 3)
        self.assertEqual(math.ceil(supply / F(1280)), 3)

    def test_paye_keys_by_independent_arithmetic(self):
        # Typed out again, using the statutory band widths as running totals instead of a loop.
        taxable = 9_600_000 - 768_000 - min(4_000_000 // 5, 500_000)
        self.assertEqual(taxable, 8_332_000)
        tax = 0 * 800_000 + 15 * 2_200_000 // 100 + 18 * (taxable - 3_000_000) // 100
        self.assertEqual(tax, 1_289_760)
        self.assertEqual(float(tax), key("paye_2026_rent_relief_cap"))
        self.assertEqual(key("paye_2026_low_earner"), 0)  # 700,000 < 800,000 zero band

    def test_underspecified_task_expects_abstention(self):
        t = TASKS["underspecified_savings_plan"]
        self.assertEqual(t["grader"]["type"], "abstain")
        traps = {x["name"]: x["wrong_answer"] for x in t["traps"]}
        self.assertEqual(traps["assumed_12pct_per_year"], 560_000)
        self.assertAlmostEqual(traps["assumed_12pct_per_month_compounded_one_year"], 500_000 * 1.12 ** 12, places=2)


class TaskHygiene(unittest.TestCase):
    def test_generated_file_is_current(self):
        spec = importlib.util.spec_from_file_location("build_tasks", ROOT / "tasks" / "build_tasks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual((ROOT / "tasks" / "tasks.json").read_text(encoding="utf-8"), mod.render())

    def test_eight_tasks_two_variants_each(self):
        self.assertEqual(len(TASKS), 8)
        self.assertEqual(len(expand_cases(list(TASKS.values()))), 16)

    def test_variants_state_the_same_numbers(self):
        def numbers(text):
            return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
        for t in TASKS.values():
            with self.subTest(task=t["id"]):
                self.assertEqual(numbers(t["prompts"]["plain"]), numbers(t["prompts"]["informal"]))

    def test_no_prompt_leaks_the_answer(self):
        for t in TASKS.values():
            g = t["grader"]
            if g["type"] != "numeric":
                continue
            k = g["answer"]
            forms = {f"{k:,.2f}", f"{k:,.0f}", f"{k:.2f}", f"{k:.0f}", f"{k:g}"}
            for v in VARIANTS:
                prompt = build_prompt(t, v)
                for form in forms:
                    with self.subTest(task=t["id"], variant=v, form=form):
                        self.assertIsNone(re.search(rf"(?<![\d.,]){re.escape(form)}(?![\d,]|\.\d)", prompt),
                                          f"prompt contains the key as {form!r}")

    def test_every_trap_is_outside_the_tolerance_and_distinct_in_meaning(self):
        for t in TASKS.values():
            g = t["grader"]
            if g["type"] != "numeric":
                continue
            for trap in t["traps"]:
                with self.subTest(task=t["id"], trap=trap["name"]):
                    self.assertFalse(within(trap["wrong_answer"], g["answer"], g["tolerance"]))
            names = [x["name"] for x in t["traps"]]
            self.assertEqual(len(names), len(set(names)))

    def test_every_task_documents_a_hypothesis_not_a_fact(self):
        for t in TASKS.values():
            self.assertTrue(t["expected_failure"].startswith("HYPOTHESIS"), t["id"])

    def test_prompts_use_the_naira_sign_consistently(self):
        for t in TASKS.values():
            for v in VARIANTS:
                self.assertNotIn("NGN", t["prompts"][v])

    def test_validator_rejects_bad_tasks(self):
        good = TASKS["solar_battery_sizing"]
        bad_trap = {**good, "traps": [{"name": "same_as_key", "wrong_answer": 4}]}
        with self.assertRaisesRegex(ValueError, "inside the tolerance"):
            validate_tasks([bad_trap])
        missing = {k: v for k, v in good.items() if k != "answer_key"}
        with self.assertRaisesRegex(ValueError, "missing 'answer_key'"):
            validate_tasks([missing])
        with self.assertRaisesRegex(ValueError, "duplicate id"):
            validate_tasks([good, good])
        no_tol = {**good, "grader": {"type": "numeric", "answer": 4}}
        with self.assertRaisesRegex(ValueError, "tolerance"):
            validate_tasks([no_tol])

    def test_prompt_ends_with_answer_instructions(self):
        p = build_prompt(TASKS["solar_battery_sizing"], "plain")
        self.assertIn("FINAL ANSWER:", p)
        self.assertIn("NEED MORE INFO:", p)
        self.assertTrue(p.rstrip().endswith("Give a whole number of batteries."))


if __name__ == "__main__":
    unittest.main()
