"""Grade raw run files and render the results tables."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from .graders import grade

VALID = ("pass", "fail")


def collect(path: str | Path, tasks: list[dict]) -> list[dict]:
    """Load a run file, keep the latest record per (model, case, sample), and grade each one."""
    by_id = {t["id"]: t for t in tasks}
    latest: dict[tuple, dict] = {}
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[(rec["model"], rec["case_id"], rec["sample"])] = rec
    rows = []
    for rec in latest.values():
        task = by_id.get(rec["task_id"])
        if task is None:
            continue
        if rec.get("error"):
            rows.append({**rec, "status": "error", "grade": None})
            continue
        g = grade(task, rec["response"])
        if g["passed"]:
            status = "pass"
        elif g["failure_kind"] == "no_final_answer" and rec.get("finish_reason") == "length":
            status = "truncated"  # ran out of tokens: not a real failure, so it is excluded from rates
        else:
            status = "fail"
        rows.append({**rec, "status": status, "grade": g})
    return rows


def _rate(rows) -> tuple[int, int]:
    valid = [r for r in rows if r["status"] in VALID]
    return sum(r["status"] == "pass" for r in valid), len(valid)


def _cell(rows) -> str:
    p, n = _rate(rows)
    return f"{p}/{n}" if n else "-"


def _pct(rows) -> str:
    p, n = _rate(rows)
    return f"{100 * p / n:.0f}% ({p}/{n})" if n else "-"


def _table(header: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def render_markdown(rows: list[dict], tasks: list[dict], source: str = "") -> str:
    models = list(dict.fromkeys(r["model"] for r in rows))
    out = [f"# Results{f' - {source}' if source else ''}", ""]
    invalid = Counter(r["status"] for r in rows if r["status"] not in VALID)
    out.append(f"{len(rows)} graded records across {len(models)} model(s). "
               f"Pass rates count only valid runs. Excluded: {invalid.get('error', 0)} API error(s), "
               f"{invalid.get('truncated', 0)} truncated reply(ies).")
    out.append("")

    # pass counts by task
    out.append("## Pass counts by task (plain + informal wordings, all samples)")
    body = []
    for t in tasks:
        trows = [r for r in rows if r["task_id"] == t["id"]]
        body.append([f"`{t['id']}`", t["domain"]] + [_cell([r for r in trows if r["model"] == m]) for m in models]
                    + [_cell(trows)])
    out.append(_table(["task", "domain"] + models + ["all models"], body))
    out.append("")

    # by wording
    out.append("## Pass rate by wording")
    body = []
    for m in models:
        mr = [r for r in rows if r["model"] == m]
        body.append([m, _pct([r for r in mr if r["variant"] == "plain"]),
                     _pct([r for r in mr if r["variant"] == "informal"]), _pct(mr)])
    out.append(_table(["model", "plain", "informal", "overall"], body))
    out.append("")

    # why they failed
    out.append("## Why runs failed")
    any_fail = False
    for m in models:
        fails = [r for r in rows if r["model"] == m and r["status"] == "fail"]
        if not fails:
            continue
        any_fail = True
        kinds = Counter(r["grade"]["failure_kind"] for r in fails)
        diag = Counter(d for r in fails for d in r["grade"]["diagnosis"])
        out.append(f"- **{m}**: " + ", ".join(f"{k} x{v}" for k, v in kinds.most_common()))
        if diag:
            out.append("  - matches a known trap: " + ", ".join(f"{k} x{v}" for k, v in diag.most_common()))
        unexplained = sum(1 for r in fails if r["grade"]["failure_kind"] == "wrong_answer" and not r["grade"]["diagnosis"])
        if unexplained:
            out.append(f"  - {unexplained} wrong answer(s) match no known trap: read them by hand, they may reveal a new trap or a bad key")
    if not any_fail:
        out.append("- no failures")
    out.append("")

    # task health
    out.append("## Task health")
    for t in tasks:
        trows = [r for r in rows if r["task_id"] == t["id"]]
        p, n = _rate(trows)
        if n < 3:
            verdict = "too few valid runs to judge"
        elif p == n:
            verdict = "every run passed: no signal yet (control, or make it harder)"
        elif p == 0:
            verdict = "every run failed: read the replies by hand to rule out a bad key or an ambiguous prompt"
        else:
            verdict = "discriminates between runs"
        out.append(f"- `{t['id']}`: {p}/{n} - {verdict}")
    out.append("")

    bad = [r for r in rows if r["status"] in ("error", "truncated")]
    if bad:
        out.append("## Invalid runs (excluded from rates)")
        bad.sort(key=lambda r: (r["model"], r["case_id"], r["sample"]))
        for r in bad[:10]:
            why = r["error"] if r["status"] == "error" else "reply cut off by max_tokens; rerun with a larger --max-tokens"
            out.append(f"- {r['model']} {r['case_id']} #{r['sample']}: {why}")
        if len(bad) > 10:
            out.append(f"- ... and {len(bad) - 10} more (see the CSV)")
        out.append("")
    return "\n".join(out)


def write_csv(rows: list[dict], path: str | Path) -> None:
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "case_id", "task_id", "variant", "sample", "status", "failure_kind",
                    "parsed_value", "expected", "diagnosis"])
        for r in sorted(rows, key=lambda r: (r["model"], r["case_id"], r["sample"])):
            g = r["grade"]
            parsed = (g["parsed"].get("value", g["parsed"].get("info", "")) if g else "")
            w.writerow([r["model"], r["case_id"], r["task_id"], r["variant"], r["sample"], r["status"],
                        (g or {}).get("failure_kind") or "", parsed, (g or {}).get("expected", ""),
                        ";".join((g or {}).get("diagnosis", []))])
