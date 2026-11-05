"""Offline fake models, used to test the harness end to end without spending money.

Model names select the behaviour: mock-oracle, mock-naive, mock-abstain,
mock-chatty, mock-truncated, mock-error.
"""
from __future__ import annotations

from .runner import Completion

STRATEGIES = ("oracle", "naive", "abstain", "chatty", "truncated", "error")


def is_mock(model: str) -> bool:
    return model.startswith("mock-") and model[5:] in STRATEGIES


class MockClient:
    def __init__(self, cases):
        self._by_prompt = {c.prompt: c for c in cases}

    def complete(self, model, prompt, *, temperature=0.0, max_tokens=4096) -> Completion:
        case = self._by_prompt.get(prompt)
        if case is None:
            return Completion("", error="mock: prompt does not belong to a known case")
        strategy = model[5:] if model.startswith("mock-") else "oracle"
        g = case.task["grader"]
        numeric = g["type"] == "numeric"
        key = g.get("answer")

        if strategy == "error":
            return Completion("", error="mock: simulated API failure")
        if strategy == "truncated":
            return Completion("First, let me work out the daily load. The fridge draws", "length")
        if strategy == "abstain":
            return Completion("I need more details first.\nNEED MORE INFO: please give me more details.", "stop")
        if strategy == "naive":
            wrong = case.task["traps"][0]["wrong_answer"]
            return Completion(f"Quick estimate.\nFINAL ANSWER: {wrong}", "stop")
        if strategy == "chatty":
            if numeric:
                return Completion(
                    "**Working**\nFirst pass gives FINAL ANSWER: 1 but let me recheck.\n\n"
                    f"**FINAL ANSWER:** ₦{key:,.2f} naira", "stop")
            return Completion(f"**NEED MORE INFO:** {g['example_valid_request']}", "stop")
        # oracle
        if numeric:
            return Completion(f"Worked through the rules.\nFINAL ANSWER: {key}", "stop")
        return Completion(f"This cannot be answered as asked.\nNEED MORE INFO: {g['example_valid_request']}", "stop")
