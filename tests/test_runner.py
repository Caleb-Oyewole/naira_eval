import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from evalkit.mock import MockClient
from evalkit.report import collect, render_markdown, write_csv
from evalkit.runner import OpenRouterClient, run_cases
from evalkit.tasks import expand_cases, load_tasks

ROOT = Path(__file__).resolve().parent.parent
TASKS = load_tasks(ROOT / "tasks" / "tasks.json")
CASES = expand_cases(TASKS)
OK_BODY = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 1, "completion_tokens": 2}}


class FakeOpenRouter:
    """A local HTTP server that replays scripted (status, headers, body) replies."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append({"path": self.path, "headers": dict(self.headers.items()),
                                       "body": json.loads(self.rfile.read(length))})
                status, headers, body = outer.script.pop(0) if outer.script else (500, {}, {"oops": 1})
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/api/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def client_for(fake, sleeps, **kw):
    no_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return OpenRouterClient(api_key="test-key", base_url=fake.url, sleep=sleeps.append, opener=no_proxy, **kw)


class OpenRouterClientTests(unittest.TestCase):
    def run_client(self, script, **kw):
        fake = FakeOpenRouter(script)
        self.addCleanup(fake.close)
        sleeps = []
        comp = client_for(fake, sleeps, **kw).complete("vendor/m", "the prompt", temperature=0.3, max_tokens=99)
        return comp, fake, sleeps

    def test_success_and_request_shape(self):
        comp, fake, _ = self.run_client([(200, {}, OK_BODY)])
        self.assertEqual((comp.text, comp.finish_reason, comp.error), ("hi", "stop", None))
        self.assertEqual(comp.usage["completion_tokens"], 2)
        req = fake.requests[0]
        self.assertEqual(req["path"], "/api/v1/chat/completions")
        self.assertEqual(req["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(req["body"], {"model": "vendor/m", "messages": [{"role": "user", "content": "the prompt"}],
                                       "temperature": 0.3, "max_tokens": 99})

    def test_retries_429_then_succeeds(self):
        comp, fake, sleeps = self.run_client([(429, {"Retry-After": "7"}, {"error": "slow down"}), (200, {}, OK_BODY)])
        self.assertEqual(comp.text, "hi")
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(sleeps, [7.0])  # honoured Retry-After

    def test_does_not_retry_a_400(self):
        comp, fake, sleeps = self.run_client([(400, {}, {"error": "bad model"}), (200, {}, OK_BODY)])
        self.assertIn("http 400", comp.error)
        self.assertEqual((comp.text, len(fake.requests), sleeps), ("", 1, []))

    def test_gives_up_after_max_retries(self):
        comp, fake, sleeps = self.run_client([(503, {}, {})] * 5, max_retries=2)
        self.assertIn("gave up after 3 attempts", comp.error)
        self.assertEqual((len(fake.requests), len(sleeps)), (3, 2))

    def test_200_with_retryable_error_body_is_retried(self):
        comp, fake, _ = self.run_client([(200, {}, {"error": {"code": 502, "message": "upstream"}}), (200, {}, OK_BODY)])
        self.assertEqual((comp.text, len(fake.requests)), ("hi", 2))

    def test_200_with_fatal_error_body_is_returned(self):
        comp, fake, _ = self.run_client([(200, {}, {"error": {"code": 401, "message": "no key"}})])
        self.assertIn("no key", comp.error)
        self.assertEqual(len(fake.requests), 1)

    def test_no_choices(self):
        comp, _, _ = self.run_client([(200, {}, {"choices": []})])
        self.assertEqual(comp.error, "response had no choices")

    def test_content_parts_and_truncation_flag(self):
        body = {"choices": [{"message": {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
                             "finish_reason": "length"}]}
        comp, _, _ = self.run_client([(200, {}, body)])
        self.assertEqual((comp.text, comp.finish_reason), ("ab", "length"))

    def test_api_key_is_never_in_the_error_text(self):
        comp, _, _ = self.run_client([(400, {}, {"error": "bad"})])
        self.assertNotIn("test-key", comp.error)

    def test_missing_key_is_a_clear_error(self):
        import os
        old = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            with self.assertRaisesRegex(RuntimeError, "OPENROUTER_API_KEY"):
                OpenRouterClient(api_key=None)
        finally:
            if old is not None:
                os.environ["OPENROUTER_API_KEY"] = old


class RunAndReport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "run.jsonl"
        self.log = []

    def run_models(self, models, **kw):
        return run_cases(CASES, models, MockClient(CASES), out_path=self.out, workers=3, log=self.log.append, **kw)

    def rows(self):
        return collect(self.out, TASKS)

    def rate(self, model):
        rs = [r for r in self.rows() if r["model"] == model]
        return sum(r["status"] == "pass" for r in rs), sum(r["status"] in ("pass", "fail") for r in rs)

    def test_oracle_and_chatty_pass_everything(self):
        self.run_models(["mock-oracle", "mock-chatty"])
        self.assertEqual(self.rate("mock-oracle"), (16, 16))
        self.assertEqual(self.rate("mock-chatty"), (16, 16))

    def test_naive_and_abstainer_pass_nothing(self):
        self.run_models(["mock-naive", "mock-abstain"])
        self.assertEqual(self.rate("mock-naive"), (0, 16))
        self.assertEqual(self.rate("mock-abstain"), (0, 16))

    def test_errors_and_truncation_are_excluded_not_counted_as_failures(self):
        self.run_models(["mock-error", "mock-truncated"])
        statuses = {(r["model"], r["status"]) for r in self.rows()}
        self.assertEqual(statuses, {("mock-error", "error"), ("mock-truncated", "truncated")})
        self.assertEqual(self.rate("mock-error"), (0, 0))
        self.assertEqual(self.rate("mock-truncated"), (0, 0))

    def test_report_leaves_invalid_runs_out_of_the_rates(self):
        self.run_models(["mock-truncated", "mock-error", "mock-oracle"])
        md = render_markdown(self.rows(), TASKS)
        self.assertIn("16 API error(s), 16 truncated reply(ies)", md)
        wording = {line.split("|")[1].strip(): line for line in md.splitlines()
                   if line.startswith("| mock-")}
        self.assertEqual(wording["mock-truncated"].split("|")[2:5], [" - ", " - ", " - "])
        self.assertEqual(wording["mock-error"].split("|")[2:5], [" - ", " - ", " - "])
        self.assertIn("100% (16/16)", wording["mock-oracle"])

    def test_rerun_skips_finished_calls(self):
        first = self.run_models(["mock-oracle"])
        second = self.run_models(["mock-oracle"])
        self.assertEqual((first["planned"], second["planned"], second["skipped"]), (16, 0, 16))
        self.assertEqual(len(self.out.read_text().splitlines()), 16)

    def test_rerun_retries_errors_and_latest_record_wins(self):
        self.run_models(["mock-error"])
        self.assertEqual(len(self.out.read_text().splitlines()), 16)
        # same model name cannot change behaviour, so append a good record by hand for one case
        good = json.loads(self.out.read_text().splitlines()[0])
        good.update(error=None, response="FINAL ANSWER: 4", finish_reason="stop")
        with self.out.open("a") as fh:
            fh.write(json.dumps(good) + "\n")
        again = self.run_models(["mock-error"])
        self.assertEqual(again["planned"], 15)  # the repaired case is not redone
        keys = {(r["case_id"], r["sample"]) for r in self.rows() if r["model"] == "mock-error"}
        self.assertEqual(len(keys), 16)

    def test_survives_half_written_last_line(self):
        self.run_models(["mock-oracle"])
        with self.out.open("a") as fh:
            fh.write('{"model": "mock-oracle", "case_i')
        again = self.run_models(["mock-oracle"])
        self.assertEqual(again["planned"], 0)
        self.assertEqual(len(self.rows()), 16)

    def test_task_and_variant_filters(self):
        subset = expand_cases(TASKS, variants=["plain"], task_ids=["solar_battery_sizing"])
        self.assertEqual([c.case_id for c in subset], ["solar_battery_sizing:plain"])
        with self.assertRaisesRegex(ValueError, "unknown task id"):
            expand_cases(TASKS, task_ids=["nope"])

    def test_samples_multiply_calls(self):
        stats = self.run_models(["mock-oracle"], samples=3)
        self.assertEqual(stats["planned"], 48)

    def test_report_contents_and_csv(self):
        self.run_models(["mock-oracle", "mock-naive", "mock-error"])
        md = render_markdown(self.rows(), TASKS, "run.jsonl")
        for needle in ("## Pass counts by task", "mock-oracle", "16/16", "0/16",
                       "assumed_12pct_per_year", "Invalid runs", "discriminates"):
            self.assertIn(needle, md)
        csv_path = Path(self.tmp.name) / "r.csv"
        write_csv(self.rows(), csv_path)
        lines = csv_path.read_text().splitlines()
        self.assertEqual(len(lines), 1 + 48)
        self.assertTrue(lines[0].startswith("model,case_id"))

    def test_task_health_flags(self):
        self.run_models(["mock-oracle", "mock-chatty"], samples=2)  # 8 valid runs per task, all passing
        md = render_markdown(self.rows(), TASKS)
        self.assertIn("every run passed: no signal yet", md)
        self.out.unlink()
        self.run_models(["mock-naive", "mock-abstain"], samples=2)
        md = render_markdown(self.rows(), TASKS)
        self.assertIn("every run failed: read the replies by hand", md)


if __name__ == "__main__":
    unittest.main()
