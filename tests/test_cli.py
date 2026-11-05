import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cli(*args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(ROOT / "run_eval.py"), *args], capture_output=True, text=True,
                          cwd=ROOT, env=env, timeout=60)


class CliTests(unittest.TestCase):
    def test_list_and_validate(self):
        self.assertEqual(cli("validate").stdout.strip(), "ok: 8 tasks, 16 cases")
        out = cli("list").stdout
        self.assertEqual(len(out.strip().splitlines()), 8)
        self.assertIn("solar_battery_sizing", out)

    def test_dry_run_counts_calls_and_spends_nothing(self):
        r = cli("run", "--models", "a/b,c/d", "--samples", "3", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn("2 model(s) x 16 case(s) x 3 sample(s) = 96 call(s)", r.stdout)

    def test_real_run_without_key_fails_cleanly(self):
        r = cli("run", "--models", "a/b", "--out", os.devnull)
        self.assertEqual(r.returncode, 2)
        self.assertIn("OPENROUTER_API_KEY", r.stderr)

    def test_mock_flag_rejects_real_model_names(self):
        r = cli("run", "--mock", "--models", "vendor/real-model")
        self.assertEqual(r.returncode, 2)
        self.assertIn("mock-*", r.stderr)

    def test_unknown_task_and_variant(self):
        self.assertNotEqual(cli("run", "--mock", "--models", "mock-oracle", "--tasks", "nope").returncode, 0)
        self.assertEqual(cli("run", "--mock", "--models", "mock-oracle", "--variants", "slang").returncode, 2)

    def test_end_to_end_run_then_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / "r" / "run.jsonl")
            run = cli("run", "--mock", "--models", "mock-oracle,mock-naive", "--out", out)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("32 call(s) made", run.stdout)
            md, csv_path = str(Path(tmp) / "r.md"), str(Path(tmp) / "r.csv")
            rep = cli("report", out, "--md", md, "--csv", csv_path)
            self.assertEqual(rep.returncode, 0, rep.stderr)
            self.assertIn("| mock-oracle |", rep.stdout)
            self.assertTrue(Path(md).read_text().startswith("# Results"))
            self.assertEqual(len(Path(csv_path).read_text().splitlines()), 33)
            again = cli("run", "--mock", "--models", "mock-oracle,mock-naive", "--out", out)
            self.assertIn("0 call(s) made, 32 already complete", again.stdout)


if __name__ == "__main__":
    unittest.main()
