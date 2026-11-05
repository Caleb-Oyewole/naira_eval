#!/usr/bin/env python3
"""Command-line entry point.

    python run_eval.py list
    python run_eval.py validate
    python run_eval.py run --mock --models mock-oracle,mock-naive --out results/demo.jsonl
    python run_eval.py run --models vendor/model-a,vendor/model-b --samples 1 --out results/pilot1.jsonl
    python run_eval.py report results/pilot1.jsonl --md results/pilot1.md --csv results/pilot1.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evalkit.mock import MockClient, is_mock
from evalkit.report import collect, render_markdown, write_csv
from evalkit.runner import OpenRouterClient, run_cases
from evalkit.tasks import VARIANTS, expand_cases, load_tasks

DEFAULT_TASKS = Path(__file__).with_name("tasks") / "tasks.json"


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


def cmd_list(args) -> int:
    tasks = load_tasks(args.tasks_file)
    for t in tasks:
        print(f"{t['id']:<34} {t['domain']:<12} {t['family']:<16} {t['grader']['type']:<8} {t['title']}")
    return 0


def cmd_validate(args) -> int:
    tasks = load_tasks(args.tasks_file)
    print(f"ok: {len(tasks)} tasks, {len(tasks) * len(VARIANTS)} cases")
    return 0


def cmd_run(args) -> int:
    tasks = load_tasks(args.tasks_file)
    variants = _csv(args.variants) or list(VARIANTS)
    bad = [v for v in variants if v not in VARIANTS]
    if bad:
        print(f"unknown variant(s): {', '.join(bad)}", file=sys.stderr)
        return 2
    cases = expand_cases(tasks, variants, _csv(args.tasks))
    models = _csv(args.models) or []
    if not models:
        print("--models is required", file=sys.stderr)
        return 2
    calls = len(models) * len(cases) * args.samples
    print(f"{len(models)} model(s) x {len(cases)} case(s) x {args.samples} sample(s) = {calls} call(s)")
    if args.samples > 1 and args.temperature == 0:
        print("warning: --samples > 1 with --temperature 0 will mostly repeat the same reply", file=sys.stderr)
    if args.dry_run:
        return 0
    if args.mock:
        wrong = [m for m in models if not is_mock(m)]
        if wrong:
            print(f"--mock only accepts mock-* model names, got: {', '.join(wrong)}", file=sys.stderr)
            return 2
        client = MockClient(cases)
    else:
        try:
            client = OpenRouterClient(referer=args.referer)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 2
    stats = run_cases(cases, models, client, out_path=args.out, samples=args.samples,
                      temperature=args.temperature, max_tokens=args.max_tokens, workers=args.workers)
    print(f"done: {stats['planned']} call(s) made, {stats['skipped']} already complete, {stats['errors']} error(s)")
    print(f"next: python run_eval.py report {args.out}")
    return 0


def cmd_report(args) -> int:
    tasks = load_tasks(args.tasks_file)
    rows = collect(args.run_file, tasks)
    if not rows:
        print("no records found in that file", file=sys.stderr)
        return 1
    md = render_markdown(rows, tasks, source=Path(args.run_file).name)
    print(md)
    if args.md:
        Path(args.md).write_text(md + "\n", encoding="utf-8")
    if args.csv:
        write_csv(rows, args.csv)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Everyday-money-decisions eval harness")
    ap.add_argument("--tasks-file", default=str(DEFAULT_TASKS), help="path to tasks.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list tasks").set_defaults(fn=cmd_list)
    sub.add_parser("validate", help="validate tasks.json").set_defaults(fn=cmd_validate)

    r = sub.add_parser("run", help="call models and save raw replies (resumable)")
    r.add_argument("--models", help="comma-separated OpenRouter model ids (or mock-* with --mock)")
    r.add_argument("--tasks", help="comma-separated task ids (default: all)")
    r.add_argument("--variants", help=f"comma-separated, from: {', '.join(VARIANTS)} (default: both)")
    r.add_argument("--samples", type=int, default=1)
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--max-tokens", type=int, default=4096)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--out", default="results/run.jsonl")
    r.add_argument("--referer", help="optional HTTP-Referer header for OpenRouter")
    r.add_argument("--mock", action="store_true", help="use offline fake models instead of OpenRouter")
    r.add_argument("--dry-run", action="store_true", help="print the number of calls and stop")
    r.set_defaults(fn=cmd_run)

    p = sub.add_parser("report", help="grade a run file and print the results tables")
    p.add_argument("run_file")
    p.add_argument("--md", help="also write the markdown report here")
    p.add_argument("--csv", help="also write a per-run CSV here")
    p.set_defaults(fn=cmd_report)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
