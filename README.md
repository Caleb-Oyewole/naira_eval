# naira-eval: where do AI models get everyday money decisions wrong in Nigeria?

Entry for the micro1 Eval Hackathon (solo). Eight tasks, each written in two wordings (plain English and light
Nigerian Pidgin), graded by plain code with no LLM judge.

## 1. Short description

**Domain:** personal finance for ordinary Nigerians (loans, bank charges, import costs, savings, income tax),
plus one engineering sizing task. **The gap:** a person types a money question into a chatbot and acts on the
answer. Models can be fluent and still get the number wrong in three ways this eval isolates: (a) multi-step
arithmetic with local traps (boundaries, exemptions, two exchange rates, compounding), (b) not knowing that the law
changed (Nigeria's income tax rules changed on 1 Jan 2026), and (c) answering confidently when the question cannot
be answered. **Key finding:** <<FILL: one or two sentences from the real run, e.g. which tasks frontier models failed and why>>

## 2. Video walkthrough

<<FILL: public video link, 5 minutes or less (YouTube unlisted, Loom, Vimeo or Google Drive with "anyone with the link")>>

## 3. Domain and expertise

<<FILL: one short paragraph in your own words: your field and what you draw on, e.g. Nigerian student and backend
developer who has built a landed-cost calculator for importers and uses these tools daily. Keep it true and specific.>>

## 4. What it tests and why it matters

| task | tests | kind |
|---|---|---|
| `ear_instalment_loan` | true yearly rate of a weekly-instalment loan (IRR, then compounding) | rules supplied |
| `bank_charges_schedule` | fee schedule with boundaries, exemptions, VAT on part of the charge | rules supplied |
| `landed_cost_two_rates` | import cost with a customs exchange rate and a different market rate | rules supplied |
| `underspecified_savings_plan` | whether the model asks instead of guessing when the question can't be answered | abstention |
| `real_value_after_wht_inflation` | savings after withholding tax and 28.9% inflation | rules supplied |
| `solar_battery_sizing` | battery count from loads, inverter efficiency and depth of discharge | rules supplied, engineering |
| `paye_2026_rent_relief_cap` | PAYE under the 2026 rules: new bands, rent relief with a cap, pension | **knowledge** (no rules given) |
| `paye_2026_low_earner` | whether a ₦700,000 earner owes tax under the new 0% band | **knowledge** (no rules given) |

Who it is for: people and small businesses (traders, importers, salaried workers) who use chatbots for money
decisions, and anyone building a finance assistant for Nigeria. What a wrong answer costs: a trader accepts a loan
whose real rate is 766% a year, an importer mis-budgets the landed cost by about ₦120,000, a worker budgets for tax they no
longer owe, or a saver trusts a number computed from an invented maturity date.

Every task is also written in an informal (light Pidgin) wording with identical numbers, so a gap between the two
columns is about wording, not difficulty.

## 5. Setup and run instructions

Python 3.10+ and nothing else (standard library only, see `requirements.txt`). Keys are listed in `.env.example`;
the key is read from the environment only and is never written to a file.

```bash
# Offline demo with fake models. Free, no key, proves the pipeline works (about 1 second).
python run_eval.py run --mock --models mock-oracle,mock-naive --out results/demo.jsonl
python run_eval.py report results/demo.jsonl

# Real models through OpenRouter (https://openrouter.ai/models; ids change, so none are hard-coded).
export OPENROUTER_API_KEY=your-key-here
python run_eval.py run --models vendor/model-a,vendor/model-b --dry-run     # count calls first
python run_eval.py run --models vendor/model-a,vendor/model-b --samples 3 --temperature 0.7 --out results/run1.jsonl
python run_eval.py report results/run1.jsonl --md results/run1.md --csv results/run1.csv

# Tests (offline, about 6 seconds) and consistency check of the task file
python -m unittest discover -s tests -t .
python tasks/build_tasks.py --check
```

`run` is resumable: re-running the same command only makes the missing or failed calls. Raw replies are saved
untouched and graded at report time, so a grader fix never needs new API calls.

**Runtime and cost:** <<FILL: measured from the real run, e.g. "N calls, about M minutes, about $X on OpenRouter">>.
The task set is 16 cases (8 tasks x 2 wordings); calls = models x 16 x samples.

## 6. Models tested and results

<<FILL: table of exact OpenRouter model ids, date of run (UTC), temperature, samples per case, and pass rates.
Paste from `results/run1.md`. The raw outputs are in `results/run1.jsonl`.>>

## 7. Failure analysis

<<FILL: where and why models failed, from reading the failing replies. Use the report's "Why runs failed" section
and the trap names (each trap is a specific wrong answer computed from one specific mistake). Say which tasks
turned out to be controls that strong models pass.>>

## 8. Prior work and sources

- No existing benchmark or dataset is used. The harness, tasks and graders were written for this hackathon, with the
  help of an AI coding assistant (allowed by the rules); every answer key was re-derived independently in the tests.
- Tasks 1-6 use fictional or hypothetical rules stated in the prompt, so the keys never go stale.
- Tasks 7-8 depend on the Nigerian personal income tax rules for the 2026 tax year (Nigeria Tax Act 2025: first
  ₦800,000 at 0%, then 15%, 18%, 21%, 23%, 25% on widths of 2.2M, 9M, 13M, 25M and the remainder; Consolidated Relief
  Allowance abolished; rent relief of 20% of rent paid capped at ₦500,000). Sources used to build the key:
  PwC Tax Summaries (Nigeria, individual taxes) and countrytaxcalc.com's 2026 PAYE guide; <<FILL: confirm against the
  Act or FIRS guidance and cite the section or page you checked>>.

## How grading works

The prompt ends with an instruction to finish with one line, either `FINAL ANSWER: <number>` or
`NEED MORE INFO: <what is missing>`. The grader reads the **last** such line, so working above it can be as long as
the model likes. There is no LLM judge anywhere, so there is no judge prompt to validate.

- **numeric**: within the task's tolerance (relative or absolute) of the key. A wrong answer is also compared with the
  task's known `traps` and with scale slips (7.66 instead of 766), so the report says *why* a run failed.
- **abstain**: passes only if the model replies `NEED MORE INFO` and names a genuinely missing fact (tenor or the
  period of the 12%). A confident number fails. Five other tasks are fully specified, so a model that always
  abstains fails them; abstaining cannot game the suite.
- Truncated replies and API errors are **excluded** from pass rates and listed separately.

## Task format (`tasks/tasks.json`, generated by `tasks/build_tasks.py`)

| field | meaning |
|---|---|
| `id`, `title`, `domain`, `family`, `difficulty` | metadata |
| `prompts.plain` / `prompts.informal` | the two wordings; must state the same numbers (tested) |
| `answer_hint` | format hint appended to the prompt (never contains the answer; tested) |
| `grader` | numeric (`answer`, `tolerance`) or abstain (`must_mention_any` regexes) |
| `answer_key` | the value and the worked steps, for reviewers |
| `traps` | plausible wrong answers, each computed from one specific mistake and outside the tolerance (tested) |
| `expected_failure` | a hypothesis until the real run confirms or refutes it |

To add a task: add a gold function and a dict in `build_tasks.py`, run it, then add an independent recomputation to
`tests/test_tasks.py` (a *different* method from the generator, so one bug cannot sit in both places).

## What has and has not been verified

Verified (64 offline tests): each answer key against an independent recomputation; prompts do not leak their
answers; both wordings carry the same numbers; parsing and grading edge cases; the OpenRouter client against a local
fake server (retries, auth header, no retry on 4xx); the run loop, resume, report and CSV end to end.

**Not verified until the run is done:** whether real models fail these tasks. The `expected_failure` entries are
hypotheses, and some tasks may turn out to be controls that strong models pass.

## Known limitations

- The grader reads the first number on the final line, so `FINAL ANSWER: 3.15, so 4` is read as 3.15.
- `underspecified_savings_plan` counts an answer that states an assumption as a miss, because the missing facts move
  the result by more than 3x. A reviewer could reasonably disagree.
- The two tax tasks are only as reliable as the cited sources; the law may be amended or clarified by FIRS guidance.
- The Pidgin is light and was written without a native-speaker review beyond the author's own read.
- Eight tasks is a small set; the brief recommends 5 to 10 well-designed ones.
