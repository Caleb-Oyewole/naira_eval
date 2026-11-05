#!/usr/bin/env python3
"""Generate tasks/tasks.json.

Every answer key and every "trap" (a plausible wrong answer) is computed here
from the task's own rules. Nothing is typed in by hand, so a prompt edit cannot
silently leave a stale key behind.

    python tasks/build_tasks.py           # (re)write tasks/tasks.json
    python tasks/build_tasks.py --check   # exit 1 if tasks.json is out of date

Tasks 1-6 supply every rule in the prompt (fictional or hypothetical) and test
reasoning over supplied rules. Tasks 7-8 (family "current_law_knowledge") supply
NO rules and test knowledge of the Nigerian personal income tax law in force for
the 2026 tax year, so their keys depend on the cited sources.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path

OUT = Path(__file__).with_name("tasks.json")
N = "₦"  # naira sign


# --------------------------------------------------------------------------
# Gold computations
# --------------------------------------------------------------------------

# T1 -- effective annual rate of an instalment loan -------------------------
T1_PRINCIPAL, T1_PAYMENT, T1_WEEKS = 60_000, 9_000, 8


def annuity_pv(rate: float, payment: float, n: int) -> float:
    return payment * (1 - (1 + rate) ** -n) / rate


def solve_weekly_rate(principal: float, payment: float, n: int) -> float:
    lo, hi = 1e-9, 5.0
    for _ in range(300):
        mid = (lo + hi) / 2
        if annuity_pv(mid, payment, n) > principal:  # PV falls as rate rises
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


T1_RATE = solve_weekly_rate(T1_PRINCIPAL, T1_PAYMENT, T1_WEEKS)
T1_EAR = ((1 + T1_RATE) ** 52 - 1) * 100
T1_TOTAL_INTEREST_PCT = (T1_PAYMENT * T1_WEEKS - T1_PRINCIPAL) / T1_PRINCIPAL * 100
T1_FLAT_ANNUALISED = T1_TOTAL_INTEREST_PCT * 52 / T1_WEEKS
T1_NOMINAL_APR = T1_RATE * 52 * 100

# T2 -- bank charges under a stated fee schedule ----------------------------
T2_ACTIVITY = [
    (4_500, "other"),
    (5_000, "other"),
    (5_001, "other"),
    (10_000, "other"),
    (9_999, "other"),
    (50_000, "other"),
    (50_001, "other"),
    (120_000, "other"),
    (2_000, "other"),
    (30_000, "own"),
    (15_000, "failed"),
    (8_000, "card"),
]


def bank_charges(*, vat_on_stamp=False, stamp_strict=False, band_exclusive=False,
                 charge_exempt=False, no_vat=False) -> D:
    total = D(0)
    for amount, kind in T2_ACTIVITY:
        if kind != "other" and not charge_exempt:
            continue
        if band_exclusive:
            fee = D(10) if amount < 5_000 else D(25) if amount < 50_000 else D(50)
        else:
            fee = D(10) if amount <= 5_000 else D(25) if amount <= 50_000 else D(50)
        stamp = D(50) if (amount > 10_000 if stamp_strict else amount >= 10_000) else D(0)
        vat = D(0) if no_vat else (fee + (stamp if vat_on_stamp else D(0))) * D("0.075")
        total += fee + stamp + vat
    return total


T2_KEY = bank_charges()

# T3 -- landed cost with two different exchange rates -----------------------


def landed_cost(*, customs_rate_for_all=False, vat_on_cif_only=False,
                surcharge_on_cif=False, pay_supplier_at_customs=False) -> D:
    fob, freight, ins = D(2400), D(350), D(50)
    market, customs = D(1620), D(1500)
    usd = fob + freight + ins
    cif = usd * (market if customs_rate_for_all else customs)
    duty = cif * D("0.20")
    surcharge = (cif if surcharge_on_cif else duty) * D("0.07")
    levy = cif * D("0.04")
    vat_base = cif if vat_on_cif_only else cif + duty + surcharge + levy
    vat = vat_base * D("0.075")
    agent = cif * D("0.015")
    haulage = D(85_000)
    dollars_paid = usd * (customs if pay_supplier_at_customs else market)
    return dollars_paid + duty + surcharge + levy + vat + agent + haulage


T3_KEY = landed_cost()

# T4 -- under-specified savings question ------------------------------------
T4_PRINCIPAL = 500_000
T4_ASSUME_ANNUAL = T4_PRINCIPAL * 1.12
T4_ASSUME_MONTHLY_FOR_YEAR = T4_PRINCIPAL * 1.12 ** 12

# T5 -- real value after withholding tax and inflation ----------------------


def real_value(*, skip_wht=False, subtract_net=False, subtract_gross=False) -> float:
    p, rate, wht, infl = F(1_000_000), F("0.18"), F("0.10"), F("0.289")
    net_rate = rate * (1 - wht)
    if subtract_net:
        return float(p * (1 + net_rate - infl))
    if subtract_gross:
        return float(p * (1 + rate - infl))
    balance = p * (1 + (rate if skip_wht else net_rate))
    return float(balance / (1 + infl))


T5_KEY = real_value()

# T6 -- battery bank sizing --------------------------------------------------


def batteries_needed(*, efficiency=True, dod=True, fridge_continuous=False) -> int:
    fridge_hours = 24 if fridge_continuous else 12
    wh = 3 * 10 * 5 + 120 * fridge_hours + 80 * 6 + 60 * 8 + 70 * 5
    supply = F(wh) / F(9, 10) if efficiency else F(wh)
    usable = F(128, 10) * 100 * (F(8, 10) if dod else 1)
    return math.ceil(supply / usable)


T6_KEY = batteries_needed()
T6_DAILY_WH = 3 * 10 * 5 + 120 * 12 + 80 * 6 + 60 * 8 + 70 * 5

# T7/T8 -- Nigerian PAYE for the 2026 tax year (KNOWLEDGE tasks: no rules in the prompt) ----
# Source rules (Nigeria Tax Act 2025, effective 1 Jan 2026), cross-checked against two secondary
# summaries (PwC Tax Summaries; countrytaxcalc.com). Verify against the Act / FIRS before submitting.
NEW_BANDS = [(800_000, F(0)), (2_200_000, F(15, 100)), (9_000_000, F(18, 100)),
             (13_000_000, F(21, 100)), (25_000_000, F(23, 100)), (None, F(25, 100))]
# Superseded regime (PITA 2011 as amended): bands after the Consolidated Relief Allowance.
OLD_BANDS = [(300_000, F(7, 100)), (300_000, F(11, 100)), (500_000, F(15, 100)),
             (500_000, F(19, 100)), (1_600_000, F(21, 100)), (None, F(24, 100))]
RENT_RELIEF_RATE, RENT_RELIEF_CAP = F(20, 100), 500_000


def progressive_tax(taxable, bands) -> float:
    rem, tax = F(taxable), F(0)
    for width, rate in bands:
        if width is None or rem <= width:
            return float(tax + max(rem, 0) * rate)
        tax += width * rate
        rem -= width
    return float(tax)


T7_GROSS, T7_PENSION, T7_RENT = 9_600_000, 768_000, 4_000_000
T7_RELIEF = min(F(T7_RENT) * RENT_RELIEF_RATE, RENT_RELIEF_CAP)
T7_TAXABLE = T7_GROSS - T7_PENSION - T7_RELIEF
T7_KEY = progressive_tax(T7_TAXABLE, NEW_BANDS)
T7_UNCAPPED_RENT = progressive_tax(T7_GROSS - T7_PENSION - F(T7_RENT) * RENT_RELIEF_RATE, NEW_BANDS)
T7_NO_RENT_RELIEF = progressive_tax(T7_GROSS - T7_PENSION, NEW_BANDS)
_cra = max(F(200_000), F(T7_GROSS) / 100) + F(T7_GROSS) * F(20, 100)
T7_OLD_LAW = progressive_tax(T7_GROSS - T7_PENSION - _cra, OLD_BANDS)

T8_GROSS = 700_000
T8_KEY = progressive_tax(T8_GROSS, NEW_BANDS)
T8_OLD_NO_CRA = progressive_tax(T8_GROSS, OLD_BANDS)
T8_OLD_WITH_CRA = progressive_tax(F(T8_GROSS) - (F(200_000) + F(T8_GROSS) * F(20, 100)), OLD_BANDS)


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

T2_RULES = f"""Bank X rules for transfers:
1. Transfer fee, charged on each transfer to another bank: {N}10 if the amount is up to and including {N}5,000; {N}25 if the amount is above {N}5,000 and up to and including {N}50,000; {N}50 if the amount is above {N}50,000.
2. Stamp duty: {N}50 on each transfer to another bank of {N}10,000 or more.
3. VAT: 7.5% of the transfer fee only. There is no VAT on stamp duty.
4. Transfers to another account at the same bank are free: no fee, no stamp duty, no VAT.
5. A failed transfer that is reversed is not charged at all.
6. Card payments and airtime purchases are not transfers, so none of the above applies to them.

Ngozi's activity this month:
- {N}4,500 to another bank
- {N}5,000 to another bank
- {N}5,001 to another bank
- {N}10,000 to another bank
- {N}9,999 to another bank
- {N}50,000 to another bank
- {N}50,001 to another bank
- {N}120,000 to another bank
- {N}2,000 to another bank
- {N}30,000 to another account at Bank X
- {N}15,000 to another bank (failed and reversed)
- {N}8,000 card payment"""

T3_RULES = f"""- Supplier invoice (FOB): USD 2,400. Freight: USD 350. Insurance: USD 50. All three are paid in dollars, and Adaeze buys the dollars at {N}1,620 per USD.
- Customs converts dollar values to naira at its own fixed rate of {N}1,500 per USD. Customs value (CIF) = FOB + freight + insurance, converted at the customs rate.
- Import duty = 20% of the CIF value.
- Surcharge = 7% of the import duty amount.
- Port levy = 4% of the CIF value.
- VAT = 7.5% of (CIF + duty + surcharge + port levy).
- Clearing agent fee = 1.5% of the CIF value (no VAT on this fee).
- Local haulage to her shop: {N}85,000."""

T6_DATA = """- 3 LED bulbs, 10 W each, on for 5 hours.
- Refrigerator: 120 W while its compressor is running. The compressor runs 50% of the time, around the clock (24 hours).
- TV: 80 W for 6 hours.
- Fan: 60 W for 8 hours.
- Laptop charger: 70 W for 5 hours.
Everything runs through an inverter that is 90% efficient (the battery must supply the load energy divided by 0.9).
Each battery is 12.8 V and 100 Ah, and may only be discharged to 80% of its rated capacity (depth of discharge). Batteries are bought as whole units."""


def _f(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"


def build() -> dict:
    tasks = []

    tasks.append({
        "id": "ear_instalment_loan",
        "title": "True yearly cost of a weekly-instalment loan",
        "domain": "finance",
        "family": "informal_credit",
        "difficulty": "hard",
        "prompts": {
            "plain": (
                f"A market trader borrows {N}60,000 from a cooperative. She repays {N}9,000 at the end of each week for 8 weeks.\n\n"
                f"What is the effective annual interest rate on this loan? Find the weekly interest rate that makes the eight "
                f"{N}9,000 repayments (each paid at the end of its week) exactly worth {N}60,000 today, then compound that "
                f"weekly rate over 52 weeks."
            ),
            "informal": (
                f"Abeg help me check this loan. Cooperative people give me {N}60,000. I go pay {N}9,000 at the end of every week for 8 weeks.\n\n"
                f"Wetin be the real interest rate for one year? Find the weekly interest rate wey go make the eight "
                f"{N}9,000 payments (each one at the end of its week) worth exactly {N}60,000 today, then compound that "
                f"weekly rate over 52 weeks."
            ),
        },
        "answer_hint": "Give the effective annual rate as a percentage figure, for example 125.4 for 125.4%.",
        "grader": {"type": "numeric", "answer": round(T1_EAR, 6), "tolerance": {"rel": 0.02}},
        "answer_key": {
            "value": round(T1_EAR, 6),
            "working": [
                f"Weekly rate r solves 60,000 = 9,000 x (1 - (1+r)^-8) / r, giving r = {T1_RATE * 100:.4f}% per week.",
                f"Effective annual rate = (1+r)^52 - 1 = {_f(T1_EAR, 1)}%.",
            ],
        },
        "traps": [
            {"name": "flat_rate_annualised", "wrong_answer": round(T1_FLAT_ANNUALISED, 6),
             "description": "Treats the interest as flat: 20% over 8 weeks, scaled to 52 weeks."},
            {"name": "nominal_apr_not_compounded", "wrong_answer": round(T1_NOMINAL_APR, 6),
             "description": "Finds the right weekly rate but multiplies by 52 instead of compounding."},
            {"name": "total_interest_as_annual", "wrong_answer": round(T1_TOTAL_INTEREST_PCT, 6),
             "description": "Reports the 20% total interest over the loan term as the annual rate."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): models report the flat or nominal rate, or iterate the weekly rate "
            "imprecisely. Because compounding over 52 weeks multiplies small errors, a 'close' weekly rate still misses "
            "the 2% tolerance."
        ),
        "notes": "Real-world relevance: cooperative, thrift and app loans are often quoted per week or as a flat charge.",
    })

    tasks.append({
        "id": "bank_charges_schedule",
        "title": "Monthly bank charges under a stated fee schedule",
        "domain": "finance",
        "family": "rule_following",
        "difficulty": "medium",
        "prompts": {
            "plain": (
                "Use only the rules below. They are for this exercise and are not any real bank's rules.\n\n"
                f"{T2_RULES}\n\n"
                "What is the total in naira that Bank X charges Ngozi this month (transfer fees + stamp duty + VAT)?"
            ),
            "informal": (
                "Abeg help Ngozi calculate wetin her bank (Bank X) charge her this month. Use only the rules below. "
                "Dem dey for this exercise, no be real bank rules.\n\n"
                f"{T2_RULES}\n\n"
                "How much be the total wey Bank X charge Ngozi this month (transfer fees + stamp duty + VAT)?"
            ),
        },
        "answer_hint": "Give the total in naira as a plain number, for example 123.45 for ₦123.45.",
        "grader": {"type": "numeric", "answer": float(T2_KEY), "tolerance": {"abs": 0.005}},
        "answer_key": {
            "value": float(T2_KEY),
            "working": [
                "Chargeable: the nine transfers to another bank. Exempt: own-bank transfer, reversed failed transfer, card payment.",
                "Fees: 10+10+25+25+25+25+50+50+10 = 230. VAT = 7.5% x 230 = 17.25.",
                "Stamp duty on 10,000, 50,000, 50,001, 120,000 (not 9,999): 4 x 50 = 200.",
                f"Total = 230 + 17.25 + 200 = {_f(float(T2_KEY))}.",
            ],
        },
        "traps": [
            {"name": "vat_on_stamp_duty", "wrong_answer": float(bank_charges(vat_on_stamp=True)),
             "description": "Applies VAT to stamp duty as well as the fee."},
            {"name": "stamp_boundary_strict", "wrong_answer": float(bank_charges(stamp_strict=True)),
             "description": "Reads 'of 10,000 or more' as 'above 10,000'."},
            {"name": "fee_band_boundary", "wrong_answer": float(bank_charges(band_exclusive=True)),
             "description": "Reads 'up to and including' as 'below' at 5,000 and 50,000."},
            {"name": "charges_exempt_items", "wrong_answer": float(bank_charges(charge_exempt=True)),
             "description": "Charges the own-bank transfer, the reversed transfer and the card payment."},
            {"name": "forgets_vat", "wrong_answer": float(bank_charges(no_vat=True)),
             "description": "Leaves out VAT."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): this may be close to a control. Twelve items with seven boundary and "
            "exemption rules give many chances for one slip, but strong models may get it right. If every model passes, "
            "keep it as a control or cut it."
        ),
        "notes": "Fictional schedule, so the key never goes stale. Boundary amounts (5,000 / 5,001 / 9,999 / 10,000 / 50,000 / 50,001) are deliberate.",
    })

    tasks.append({
        "id": "landed_cost_two_rates",
        "title": "Import landed cost with two exchange rates",
        "domain": "finance",
        "family": "rule_following",
        "difficulty": "hard",
        "prompts": {
            "plain": (
                "Adaeze imports a batch of sewing machines. Use only these rules, which are for this exercise.\n\n"
                f"{T3_RULES}\n\n"
                "How much naira does Adaeze spend in total to get the machines to her shop? Count the dollars she buys "
                "(at her rate) plus every naira charge listed above."
            ),
            "informal": (
                "Abeg help Adaeze calculate how much she go spend for her import. She wan bring sewing machines come. "
                "Use only these rules, dem dey for this exercise.\n\n"
                f"{T3_RULES}\n\n"
                "How much naira Adaeze go spend in total to get the machines reach her shop? Count the dollars she buys "
                "(at her rate) plus every naira charge listed above."
            ),
        },
        "answer_hint": "Give the total in naira as a plain number, for example 1234567.",
        "grader": {"type": "numeric", "answer": float(T3_KEY), "tolerance": {"rel": 0.0005}},
        "answer_key": {
            "value": float(T3_KEY),
            "working": [
                f"USD total = 2,400 + 350 + 50 = 2,800. Dollars bought at 1,620 = {N}{_f(2800 * 1620, 0)}.",
                f"CIF (customs rate 1,500) = {N}{_f(2800 * 1500, 0)}. Duty 20% = {N}{_f(2800 * 1500 * 0.20, 0)}.",
                f"Surcharge 7% of duty = {N}{_f(2800 * 1500 * 0.20 * 0.07, 0)}. Port levy 4% of CIF = {N}{_f(2800 * 1500 * 0.04, 0)}.",
                "VAT = 7.5% x (CIF + duty + surcharge + levy) = 7.5% x 5,266,800 = 395,010.",
                f"Agent 1.5% of CIF = 63,000. Haulage 85,000. Total = {N}{_f(float(T3_KEY), 0)}.",
            ],
        },
        "traps": [
            {"name": "market_rate_used_for_customs", "wrong_answer": float(landed_cost(customs_rate_for_all=True)),
             "description": "Values CIF at her 1,620 rate instead of the customs 1,500 rate."},
            {"name": "vat_base_excludes_duty_and_levies", "wrong_answer": float(landed_cost(vat_on_cif_only=True)),
             "description": "Charges VAT on CIF only."},
            {"name": "surcharge_on_cif", "wrong_answer": float(landed_cost(surcharge_on_cif=True)),
             "description": "Takes 7% of CIF instead of 7% of the duty amount."},
            {"name": "supplier_paid_at_customs_rate", "wrong_answer": float(landed_cost(pay_supplier_at_customs=True)),
             "description": "Counts the dollars she buys at the customs rate instead of what she actually pays."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): the two exchange rates (what she pays vs what customs assumes) and the "
            "stacked VAT base invite a wrong base somewhere. Expect the failures to be one of the four listed traps."
        ),
        "notes": "Fictional rules and rates. Mirrors the shape of real import-cost questions without depending on today's tariff schedule.",
    })

    tasks.append({
        "id": "underspecified_savings_plan",
        "title": "Savings plan question that cannot be answered as asked",
        "domain": "finance",
        "family": "underspecified",
        "difficulty": "medium",
        "prompts": {
            "plain": (
                f"I want to put {N}500,000 into a savings plan that says it pays 12%. How much will I have when the plan matures?"
            ),
            "informal": (
                f"I wan put {N}500,000 for one savings plan wey talk say e dey pay 12%. How much I go get when the plan mature?"
            ),
        },
        "answer_hint": "If you can answer, give the amount in naira.",
        "grader": {
            "type": "abstain",
            "must_mention_any": [
                r"\b(tenor|tenure|duration|maturity|how long|term|length)\b",
                r"per\s+(year|annum|month|week)|annual|p\.a\.|monthly|yearly|compound|simple",
            ],
            "example_valid_request": "How long until the plan matures, and is the 12% per year or per month?",
        },
        "answer_key": {
            "expected_behavior": "abstain",
            "missing_information": [
                "How long until maturity (the tenor).",
                "Whether 12% is per year, per month, or for the whole tenor.",
                "Whether interest is simple or compounded.",
            ],
            "working": [
                "Without the tenor and the period the 12% refers to, the final amount ranges from 560,000 to over 1.9 million.",
            ],
        },
        "traps": [
            {"name": "assumed_12pct_per_year", "wrong_answer": T4_ASSUME_ANNUAL,
             "description": "Silently assumes 12% per year for one year."},
            {"name": "assumed_12pct_per_month_compounded_one_year", "wrong_answer": round(T4_ASSUME_MONTHLY_FOR_YEAR, 6),
             "description": "Silently assumes 12% per month, compounded for 12 months."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): models pick a default (12% per year, one year) and report a confident "
            "figure instead of asking. The other five tasks are fully specified, so a model that always abstains "
            "fails those."
        ),
        "notes": "Tests asking vs guessing. Strict reading: an answer with a stated assumption still counts as a miss, because the missing facts change the result by more than 3x. Review this choice before submitting.",
    })

    tasks.append({
        "id": "real_value_after_wht_inflation",
        "title": "Real value of a savings balance after tax and inflation",
        "domain": "finance",
        "family": "real_returns",
        "difficulty": "medium",
        "prompts": {
            "plain": (
                f"Assume the following for one year. Chiamaka deposits {N}1,000,000 in a savings account that pays 18% interest per year, "
                f"paid once at the end of the year. The bank deducts 10% withholding tax from the interest before paying it. "
                f"Prices in general rise by 28.9% over the year.\n\n"
                f"At the end of the year, what is her total balance worth in today's naira (start-of-year purchasing power)? "
                f"Round to the nearest naira."
            ),
            "informal": (
                f"I put {N}1,000,000 for savings account for one year. Dem say e dey pay 18% interest per year, dem go pay am one time at the end of the year. "
                f"Bank go cut 10% withholding tax from the interest before dem pay me. Meanwhile prices for market go rise by 28.9% for the year.\n\n"
                f"At the end of the year, how much my total balance worth for today's naira (start-of-year purchasing power)? "
                f"Round am to the nearest naira."
            ),
        },
        "answer_hint": "Give the value in naira as a plain number, for example 123456.",
        "grader": {"type": "numeric", "answer": round(T5_KEY, 4), "tolerance": {"rel": 0.003}},
        "answer_key": {
            "value": round(T5_KEY, 4),
            "working": [
                "Interest = 180,000. Withholding tax = 18,000. Net interest = 162,000. Balance = 1,162,000.",
                f"Real value = 1,162,000 / 1.289 = {N}{_f(T5_KEY, 0)}.",
            ],
        },
        "traps": [
            {"name": "ignores_wht", "wrong_answer": round(real_value(skip_wht=True), 4),
             "description": "Forgets the withholding tax on the interest."},
            {"name": "subtracts_inflation_from_net_rate", "wrong_answer": round(real_value(subtract_net=True), 4),
             "description": "Uses 'real return = nominal - inflation' with the after-tax rate."},
            {"name": "subtracts_inflation_ignoring_wht", "wrong_answer": round(real_value(subtract_gross=True), 4),
             "description": "Uses 'nominal - inflation' with the 18% headline rate and no tax."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): at 28.9% inflation the subtract-the-rates shortcut is badly wrong, and "
            "forgetting the tax moves the answer by 1.5%. This is likely easier than the other finance tasks."
        ),
        "notes": "Hypothetical rates stated in the prompt, so the key is independent of real inflation data.",
    })

    tasks.append({
        "id": "solar_battery_sizing",
        "title": "How many batteries to run a household for a day",
        "domain": "engineering",
        "family": "energy_sizing",
        "difficulty": "medium",
        "prompts": {
            "plain": (
                "A family wants a battery bank to run the appliances below for one full day during a power cut. Use only the data given.\n\n"
                f"{T6_DATA}\n\n"
                "What is the minimum number of batteries needed?"
            ),
            "informal": (
                "My family wan buy battery for when NEPA take light for one full day. Use only the data given.\n\n"
                f"{T6_DATA}\n\n"
                "Minimum how many batteries we go need?"
            ),
        },
        "answer_hint": "Give a whole number of batteries.",
        "grader": {"type": "numeric", "answer": T6_KEY, "tolerance": {"abs": 0}},
        "answer_key": {
            "value": T6_KEY,
            "working": [
                f"Daily load = 150 + 1,440 + 480 + 480 + 350 = {T6_DAILY_WH:,} Wh (fridge: 120 W x 12 h).",
                f"Battery must supply {T6_DAILY_WH:,} / 0.9 = {T6_DAILY_WH / 0.9:,.1f} Wh.",
                "Usable per battery = 12.8 V x 100 Ah x 0.8 = 1,024 Wh.",
                f"{T6_DAILY_WH / 0.9:,.1f} / 1,024 = {T6_DAILY_WH / 0.9 / 1024:.2f}, so {T6_KEY} whole batteries.",
            ],
        },
        "traps": [
            {"name": "ignores_inverter_efficiency", "wrong_answer": batteries_needed(efficiency=False),
             "description": "Divides the load by battery capacity without the 0.9 inverter efficiency."},
            {"name": "ignores_depth_of_discharge", "wrong_answer": batteries_needed(dod=False),
             "description": "Uses the full 1,280 Wh instead of 80% usable."},
            {"name": "fridge_runs_continuously", "wrong_answer": batteries_needed(fridge_continuous=True),
             "description": "Counts the refrigerator at 120 W for 24 hours, ignoring the 50% duty cycle."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): the numbers are chosen so that skipping efficiency, skipping depth of "
            "discharge, or ignoring the fridge duty cycle each changes the integer answer. May be passed by strong models."
        ),
        "notes": "The engineering crossover. Deterministic integer answer; every wrong shortcut lands on a different integer than the key.",
    })

    tasks.append({
        "id": "paye_2026_rent_relief_cap",
        "title": "PAYE for a salaried worker under the 2026 Nigerian tax rules",
        "domain": "finance",
        "family": "current_law_knowledge",
        "difficulty": "hard",
        "prompts": {
            "plain": (
                f"Tunde is a salaried employee in Nigeria. For the 2026 tax year his gross salary is {N}9,600,000 a year. "
                f"His own pension contribution is {N}768,000 a year, and he pays {N}4,000,000 a year in rent. "
                f"He has no other income, reliefs or deductions, and he claims every relief the law allows him for these items.\n\n"
                f"Under the Nigerian personal income tax law that applies to the 2026 tax year, how much income tax (PAYE) does he owe "
                f"for the year, in naira?"
            ),
            "informal": (
                f"Tunde dey work for Nigeria as salary worker. For 2026 tax year, im gross salary na {N}9,600,000 for one year. "
                f"Im own pension contribution na {N}768,000 for one year, and im dey pay {N}4,000,000 for rent for one year. "
                f"Im no get any other income, relief or deduction, and im claim every relief wey the law allow am for these things.\n\n"
                f"Under the Nigerian personal income tax law wey dey work for 2026 tax year, how much income tax (PAYE) Tunde go pay "
                f"for the year, for naira?"
            ),
        },
        "answer_hint": "Give the annual tax in naira as a plain number, for example 123456.",
        "grader": {"type": "numeric", "answer": T7_KEY, "tolerance": {"abs": 1}},
        "answer_key": {
            "value": T7_KEY,
            "working": [
                "From 1 Jan 2026 the Consolidated Relief Allowance is abolished and replaced by rent relief: 20% of rent paid, capped at 500,000.",
                f"Rent relief = min(20% x 4,000,000 = 800,000, 500,000) = {N}{_f(float(T7_RELIEF), 0)}.",
                f"Taxable income = 9,600,000 - 768,000 (pension) - 500,000 = {N}{_f(float(T7_TAXABLE), 0)}.",
                "Bands: first 800,000 at 0%; next 2,200,000 at 15%; next 9,000,000 at 18%.",
                f"Tax = 0 + 330,000 + 18% x (8,332,000 - 3,000,000 = 5,332,000) = 330,000 + 959,760 = {N}{_f(T7_KEY, 0)}.",
            ],
        },
        "traps": [
            {"name": "rent_relief_cap_ignored", "wrong_answer": T7_UNCAPPED_RENT,
             "description": "Takes the full 20% of rent (800,000) and ignores the 500,000 cap."},
            {"name": "no_rent_relief_claimed", "wrong_answer": T7_NO_RENT_RELIEF,
             "description": "Forgets that rent relief exists under the new law."},
            {"name": "old_pita_regime_with_cra", "wrong_answer": T7_OLD_LAW,
             "description": "Applies the superseded regime: Consolidated Relief Allowance and the old 7%-24% bands."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): models with older training data apply the superseded PITA bands and the "
            "Consolidated Relief Allowance; newer models may know the 800,000 zero band but miss the 500,000 rent-relief cap. "
            "If strong models pass, keep as a control."
        ),
        "notes": (
            "KNOWLEDGE task: the prompt supplies no rates, so it tests whether the model knows the law in force. "
            "Key based on the Nigeria Tax Act 2025 as summarised by PwC Tax Summaries and countrytaxcalc.com; confirm against "
            "the Act or FIRS guidance. Pension is stated as a fixed amount to avoid ambiguity about the pension base."
        ),
    })

    tasks.append({
        "id": "paye_2026_low_earner",
        "title": "Does a low earner owe any income tax in 2026?",
        "domain": "finance",
        "family": "current_law_knowledge",
        "difficulty": "medium",
        "prompts": {
            "plain": (
                f"Amina is a salaried employee in Nigeria. For the 2026 tax year her gross salary is {N}700,000 a year. "
                f"She has no other income, reliefs or deductions.\n\n"
                f"Under the Nigerian personal income tax law that applies to the 2026 tax year, how much income tax (PAYE) does she owe "
                f"for the year, in naira?"
            ),
            "informal": (
                f"Amina dey work for Nigeria as salary worker. For 2026 tax year, her gross salary na {N}700,000 for one year. "
                f"She no get any other income, relief or deduction.\n\n"
                f"Under the Nigerian personal income tax law wey dey work for 2026 tax year, how much income tax (PAYE) Amina go pay "
                f"for the year, for naira?"
            ),
        },
        "answer_hint": "Give the annual tax in naira as a plain number.",
        "grader": {"type": "numeric", "answer": T8_KEY, "tolerance": {"abs": 0.5}},
        "answer_key": {
            "value": T8_KEY,
            "working": [
                "Under the Nigeria Tax Act 2025 (effective 1 Jan 2026) the first 800,000 of taxable income is taxed at 0%.",
                "700,000 is below 800,000, so the tax is 0.",
            ],
        },
        "traps": [
            {"name": "old_bands_no_cra", "wrong_answer": T8_OLD_NO_CRA,
             "description": "Applies the superseded 7%-24% bands to the full salary."},
            {"name": "old_regime_with_cra", "wrong_answer": T8_OLD_WITH_CRA,
             "description": "Applies the superseded Consolidated Relief Allowance, then the old bands."},
        ],
        "expected_failure": (
            "HYPOTHESIS (verify in the pilot): models relying on pre-2026 law report a positive tax. Newer models probably "
            "answer 0, so this may be a control. Real consequence: low earners who over-withhold or budget for tax they no longer owe."
        ),
        "notes": (
            "KNOWLEDGE task; same sourcing caveat as paye_2026_rent_relief_cap. The prompt deliberately does not hint that zero is "
            "possible; 0 is a valid FINAL ANSWER number."
        ),
    })

    return {"schema_version": 1, "name": "naira-everyday-money-eval", "tasks": tasks}


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if tasks.json differs from the generated output")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("tasks.json is out of date; run: python tasks/build_tasks.py", file=sys.stderr)
            return 1
        print("tasks.json is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(build()['tasks'])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
