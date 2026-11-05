"""Task loading, validation, and prompt construction."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .graders import GRADERS, within

ANSWER_SUFFIX = (
    "Work it out step by step, keeping the working short. Then finish with exactly one last line, "
    "in one of these two forms:\n"
    "FINAL ANSWER: <one number only: no units, no words>\n"
    "NEED MORE INFO: <the specific missing information>\n"
    "Use NEED MORE INFO only when the question cannot be answered without facts that were not given."
)

VARIANTS = ("plain", "informal")


@dataclass
class Case:
    case_id: str
    task_id: str
    variant: str
    prompt: str
    task: dict


def build_prompt(task: dict, variant: str) -> str:
    hint = task.get("answer_hint", "").strip()
    suffix = ANSWER_SUFFIX + (f" {hint}" if hint else "")
    return f"{task['prompts'][variant]}\n\n{suffix}"


def validate_tasks(tasks: list[dict]) -> None:
    problems: list[str] = []
    seen: set[str] = set()
    for t in tasks:
        tid = t.get("id", "<missing id>")
        if tid in seen:
            problems.append(f"{tid}: duplicate id")
        seen.add(tid)
        for key in ("id", "title", "domain", "family", "prompts", "grader", "answer_key", "expected_failure"):
            if key not in t:
                problems.append(f"{tid}: missing '{key}'")
        prompts = t.get("prompts", {})
        for v in VARIANTS:
            if not str(prompts.get(v, "")).strip():
                problems.append(f"{tid}: missing prompt variant '{v}'")
        g = t.get("grader", {})
        gtype = g.get("type")
        if gtype not in GRADERS:
            problems.append(f"{tid}: unknown grader type {gtype!r}")
            continue
        if gtype == "numeric":
            if not isinstance(g.get("answer"), (int, float)):
                problems.append(f"{tid}: numeric grader needs a numeric 'answer'")
            tol = g.get("tolerance", {})
            if not tol or not (tol.get("rel") is not None or tol.get("abs") is not None):
                problems.append(f"{tid}: numeric grader needs tolerance.rel or tolerance.abs")
            else:
                for trap in t.get("traps", []):
                    if within(trap["wrong_answer"], g["answer"], tol):
                        problems.append(f"{tid}: trap '{trap['name']}' falls inside the tolerance of the key")
        if gtype == "abstain" and not g.get("must_mention_any"):
            problems.append(f"{tid}: abstain grader needs 'must_mention_any'")
        for trap in t.get("traps", []):
            if "name" not in trap or "wrong_answer" not in trap:
                problems.append(f"{tid}: every trap needs 'name' and 'wrong_answer'")
    if problems:
        raise ValueError("invalid tasks:\n  - " + "\n  - ".join(problems))


def load_tasks(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = data["tasks"]
    validate_tasks(tasks)
    return tasks


def expand_cases(tasks: list[dict], variants=VARIANTS, task_ids=None) -> list[Case]:
    wanted = set(task_ids) if task_ids else None
    unknown = (wanted or set()) - {t["id"] for t in tasks}
    if unknown:
        raise ValueError(f"unknown task id(s): {', '.join(sorted(unknown))}")
    cases = []
    for t in tasks:
        if wanted is not None and t["id"] not in wanted:
            continue
        for v in variants:
            cases.append(Case(f"{t['id']}:{v}", t["id"], v, build_prompt(t, v), t))
    return cases
