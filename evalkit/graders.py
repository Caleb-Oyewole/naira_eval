"""Deterministic graders. There is no LLM judge anywhere in this project.

A model reply is graded from its last "FINAL ANSWER:" or "NEED MORE INFO:"
line, so the working above that line can be as chatty as the model likes.
"""
from __future__ import annotations

import re
from typing import Any

FINAL_RE = re.compile(r"FINAL\s+ANSWER\s*:\s*([^\n]*)", re.IGNORECASE)
NEED_RE = re.compile(r"NEED\s+MORE\s+INFO\s*:\s*([^\n]*)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"([-−–])?(\d[\d,]*(?:\.\d+)?|\.\d+)")
_SCALE_RE = re.compile(r"^\s*(thousand|million|billion)\b", re.IGNORECASE)
_SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
_SCALE_FACTORS = (100, 0.01, 1000, 0.001)


def _clean(s: str) -> str:
    return s.replace("*", "").replace("`", "").strip()


def parse_number(payload: str) -> float | None:
    """First number in `payload`, tolerant of N/naira signs, commas, %, and 'million'."""
    s = _clean(payload)
    m = _NUMBER_RE.search(s)
    if not m:
        return None
    digits = m.group(2).rstrip(",").replace(",", "")
    try:
        value = float(digits)
    except ValueError:
        return None
    if m.group(1):
        value = -value
    scale = _SCALE_RE.match(s[m.end():])
    if scale:
        value *= _SCALES[scale.group(1).lower()]
    return value


def parse_response(text: str) -> dict[str, Any]:
    """Return {'kind': 'answer'|'need_info'|'unparsable'|'none', ...} from the LAST final line."""
    last: tuple[int, str, str] | None = None
    for m in FINAL_RE.finditer(text or ""):
        if last is None or m.start() > last[0]:
            last = (m.start(), "answer", m.group(1))
    for m in NEED_RE.finditer(text or ""):
        if last is None or m.start() > last[0]:
            last = (m.start(), "need_info", m.group(1))
    if last is None:
        return {"kind": "none"}
    _, kind, payload = last
    if kind == "need_info":
        return {"kind": "need_info", "info": _clean(payload)}
    value = parse_number(payload)
    if value is None:
        return {"kind": "unparsable", "raw": _clean(payload)}
    return {"kind": "answer", "value": value, "raw": _clean(payload)}


def within(value: float, key: float, tol: dict[str, float]) -> bool:
    allowed = max(float(tol.get("abs", 0.0)), float(tol.get("rel", 0.0)) * abs(key))
    return abs(value - key) <= allowed + 1e-9


def _result(passed: bool, kind: str | None, parsed: dict, expected: Any,
            diagnosis: list[str] | None = None, detail: str = "") -> dict[str, Any]:
    return {
        "passed": passed,
        "failure_kind": None if passed else kind,
        "diagnosis": diagnosis or [],
        "parsed": parsed,
        "expected": expected,
        "detail": detail,
    }


def _trap_names(value: float, task: dict, tol: dict) -> list[str]:
    names = [t["name"] for t in task.get("traps", []) if within(value, t["wrong_answer"], tol)]
    return names


def grade_numeric(task: dict, parsed: dict) -> dict[str, Any]:
    g = task["grader"]
    key, tol = g["answer"], g.get("tolerance", {})
    kind = parsed["kind"]
    if kind == "answer":
        value = parsed["value"]
        if within(value, key, tol):
            return _result(True, None, parsed, key)
        diag = _trap_names(value, task, tol)
        for factor in _SCALE_FACTORS:
            if within(value * factor, key, tol):
                diag.append(f"scale_error_x{factor:g}")
        return _result(False, "wrong_answer", parsed, key, diag,
                       f"got {value:g}, expected {key:g}")
    if kind == "need_info":
        return _result(False, "unnecessary_abstain", parsed, key, [],
                       "asked for more information on a fully specified question")
    if kind == "unparsable":
        return _result(False, "unparsable_answer", parsed, key, [],
                       f"could not read a number from: {parsed['raw'][:60]!r}")
    return _result(False, "no_final_answer", parsed, key, [], "no FINAL ANSWER line")


def grade_abstain(task: dict, parsed: dict) -> dict[str, Any]:
    g = task["grader"]
    kind = parsed["kind"]
    expected = "NEED MORE INFO"
    if kind == "need_info":
        info = parsed["info"]
        if any(re.search(p, info, re.IGNORECASE) for p in g["must_mention_any"]):
            return _result(True, None, parsed, expected)
        return _result(False, "vague_clarification", parsed, expected, [],
                       "asked for more information but not for any of the missing facts")
    if kind == "answer":
        value = parsed["value"]
        diag = _trap_names(value, task, {"rel": 0.001})
        return _result(False, "answered_instead_of_asking", parsed, expected, diag,
                       f"gave a confident figure ({value:g}) instead of asking")
    if kind == "unparsable":
        return _result(False, "unparsable_answer", parsed, expected, [], "unreadable final line")
    return _result(False, "no_final_answer", parsed, expected, [], "no final line")


GRADERS = {"numeric": grade_numeric, "abstain": grade_abstain}


def grade(task: dict, response_text: str) -> dict[str, Any]:
    parsed = parse_response(response_text)
    return GRADERS[task["grader"]["type"]](task, parsed)
