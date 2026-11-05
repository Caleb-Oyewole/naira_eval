"""Model clients (OpenRouter over plain urllib) and a resumable run loop.

Raw responses are written to JSONL and graded later (see report.py), so a grader
fix never costs another round of API calls.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

RETRYABLE = {408, 429, 500, 502, 503, 504}


@dataclass
class Completion:
    text: str
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    error: str | None = None


class OpenRouterClient:
    """Minimal chat-completions client for https://openrouter.ai (OpenAI-compatible)."""

    def __init__(self, api_key: str | None = None, base_url: str = "https://openrouter.ai/api/v1",
                 timeout: float = 120.0, max_retries: int = 4, referer: str | None = None,
                 title: str = "naira-eval", sleep: Callable[[float], None] = time.sleep,
                 opener: urllib.request.OpenerDirector | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set the OPENROUTER_API_KEY environment variable (or use --mock).")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.timeout = timeout
        self.max_retries = max_retries
        self.referer = referer
        self.title = title
        self._sleep = sleep
        self._opener = opener or urllib.request.build_opener()

    def _headers(self) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "naira-eval/0.1",
            "X-Title": self.title,
        }
        if self.referer:
            h["HTTP-Referer"] = self.referer
        return h

    def complete(self, model: str, prompt: str, *, temperature: float = 0.0,
                 max_tokens: int = 4096) -> Completion:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8")
        started = time.monotonic()
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            retry_after = None
            try:
                req = urllib.request.Request(self.url, data=payload, headers=self._headers(), method="POST")
                with self._opener.open(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                err = body.get("error")
                if err:
                    code = err.get("code") if isinstance(err, dict) else None
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    last_error = f"api error {code}: {msg}"[:300]
                    if code in RETRYABLE and attempt < self.max_retries:
                        self._sleep(min(2.0 * 2 ** attempt, 30.0))
                        continue
                    return Completion("", error=last_error, latency_s=time.monotonic() - started)
                choices = body.get("choices") or []
                if not choices:
                    return Completion("", error="response had no choices", latency_s=time.monotonic() - started)
                message = choices[0].get("message") or {}
                content = message.get("content") or ""
                if isinstance(content, list):  # some providers return content parts
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                return Completion(content, choices[0].get("finish_reason"), body.get("usage") or {},
                                  time.monotonic() - started)
            except urllib.error.HTTPError as e:
                snippet = e.read().decode("utf-8", "replace")[:200].replace("\n", " ")
                last_error = f"http {e.code}: {snippet}"
                if e.code not in RETRYABLE:
                    return Completion("", error=last_error, latency_s=time.monotonic() - started)
                ra = e.headers.get("Retry-After") if e.headers else None
                retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
                last_error = f"{type(e).__name__}: {str(e)[:150]}"
            if attempt < self.max_retries:
                self._sleep(retry_after if retry_after is not None else min(2.0 * 2 ** attempt, 30.0))
        return Completion("", error=f"gave up after {self.max_retries + 1} attempts ({last_error})",
                          latency_s=time.monotonic() - started)


def _completed_keys(path: Path) -> set[tuple[str, str, int]]:
    done: set[tuple[str, str, int]] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a half-written last line from an interrupted run
            if not rec.get("error"):
                done.add((rec["model"], rec["case_id"], rec["sample"]))
    return done


def run_cases(cases, models: list[str], client, *, out_path: str | Path, samples: int = 1,
              temperature: float = 0.0, max_tokens: int = 4096, workers: int = 4,
              log: Callable[[str], None] = print) -> dict[str, int]:
    """Call every (model, case, sample) not already completed in `out_path`. Safe to re-run."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = _completed_keys(out)
    jobs = [(m, c, s) for m in models for c in cases for s in range(samples)
            if (m, c.case_id, s) not in done]
    stats = {"planned": len(jobs), "skipped": len(done), "errors": 0}
    if not jobs:
        log("nothing to do: every requested call is already in the output file")
        return stats
    lock = threading.Lock()

    def work(job):
        model, case, sample = job
        try:
            comp = client.complete(model, case.prompt, temperature=temperature, max_tokens=max_tokens)
        except Exception as e:  # never let one bad call kill the run
            comp = Completion("", error=f"{type(e).__name__}: {str(e)[:150]}")
        rec = {
            "model": model, "case_id": case.case_id, "task_id": case.task_id, "variant": case.variant,
            "sample": sample, "prompt": case.prompt, "response": comp.text,
            "finish_reason": comp.finish_reason, "usage": comp.usage,
            "latency_s": round(comp.latency_s, 3), "error": comp.error,
            "temperature": temperature, "max_tokens": max_tokens, "ts": int(time.time()),
        }
        with lock:
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for i, rec in enumerate(ex.map(work, jobs), 1):
            if rec["error"]:
                stats["errors"] += 1
            tag = "ERROR " + rec["error"][:60] if rec["error"] else "ok"
            log(f"[{i}/{len(jobs)}] {rec['model']} {rec['case_id']} #{rec['sample']} {tag}")
    return stats
