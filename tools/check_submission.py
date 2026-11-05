#!/usr/bin/env python3
"""Pre-submission checker and zip builder.

    python tools/check_submission.py          # report problems
    python tools/check_submission.py --zip    # also write ../naira_eval_submission.zip if clean

Checks the brief's rules: README present with the required sections and a video link,
no unfilled <<FILL>> markers, no secrets, no cache/binary junk, size under 50 MB.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 50 * 1024 * 1024
SKIP_DIRS = {"__pycache__", ".git"}
SECTIONS = ["Short description", "Video walkthrough", "Domain and expertise", "What it tests",
            "Setup and run", "Models tested and results", "Failure analysis", "Prior work"]
SECRET_RE = re.compile(r"sk-or-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|OPENROUTER_API_KEY\s*=\s*(?![.<\s$]|your|<)[A-Za-z0-9_-]{12,}")


def files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.suffix != ".pyc":
            yield p


def check() -> list[str]:
    problems = []
    readme = ROOT / "README.md"
    if not readme.exists():
        return ["README.md missing at the zip root"]
    text = readme.read_text(encoding="utf-8")
    for s in SECTIONS:
        if not re.search(rf"^#+\s.*{re.escape(s)}", text, re.IGNORECASE | re.MULTILINE):
            problems.append(f"README has no heading for: {s}")
    if "<<FILL" in text:
        problems.append(f"README still has {text.count('<<FILL')} unfilled <<FILL ...>> marker(s)")
    if not re.search(r"https?://\S*(youtu|loom|vimeo|drive\.google)\S*", text, re.IGNORECASE):
        problems.append("README has no video link (YouTube, Loom, Vimeo or Google Drive)")
    for need in (".env.example", "requirements.txt"):
        if not (ROOT / need).exists():
            problems.append(f"{need} missing")
    results = [p for p in (ROOT / "results").glob("*.jsonl")] if (ROOT / "results").exists() else []
    if not results:
        problems.append("results/ has no .jsonl file: include raw model outputs from a real run")
    total = 0
    for p in files():
        total += p.stat().st_size
        if p.name == ".env":
            problems.append(f"{p.relative_to(ROOT)} must not be in the zip")
        if p.suffix in {".py", ".md", ".json", ".jsonl", ".csv", ".txt", ".example"} and p.name != "check_submission.py":
            if SECRET_RE.search(p.read_text(encoding="utf-8", errors="ignore")):
                problems.append(f"possible API key in {p.relative_to(ROOT)}")
    if total > MAX_BYTES:
        problems.append(f"zip contents are {total / 1e6:.1f} MB, over the 50 MB limit")
    return problems


def main(argv) -> int:
    problems = check()
    if problems:
        print("NOT READY:")
        for p in problems:
            print(" -", p)
    else:
        print("ok: no problems found")
    if "--zip" in argv:
        if problems:
            print("not writing a zip while problems remain", file=sys.stderr)
            return 1
        out = ROOT.parent / "naira_eval_submission.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files():
                z.write(p, p.relative_to(ROOT))  # README.md ends up at the zip root
        print(f"wrote {out} ({out.stat().st_size / 1e3:.0f} KB)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
