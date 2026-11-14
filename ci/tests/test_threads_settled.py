"""Tests for ci/threads_settled.py (the threads-settled check), its generated workflow, and the caller files.

Offline only: the CLI runs with --threads-file and --comments-file, and the no-token check fails before any socket opens.
"""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent
sys.path.insert(0, str(CI))
import threads_settled as ts  # noqa: E402

HEAD = "a" * 40
OLD = "b" * 40
NEW = "c" * 40
MAL = "d" * 40
URL = "https://example.test/pr/5#discussion_r1"
GENERATED = ROOT / ".github" / "workflows" / "threads-settled.yml"
CALLER = ROOT / ".github" / "workflows" / "threads.yml"
TEMPLATE = ROOT / "skills" / "setup-pr-review" / "templates" / "threads-settled.yml"

try:
    import yaml
except ImportError:  # the yaml assertions are skipped without PyYAML
    yaml = None


def node(login, body="", url=URL):
    """A comment node as GraphQL returns it; login None is a deleted user (a null author)."""
    return {"url": url, "body": body, "author": None if login is None else {"login": login}}


def marker(sha):
    return f"<!-- pr-review:fixed sha={sha} -->"


def thread(*comments, resolved=False, outdated=False):
    """A review thread: the first comment is the opening one, the last one is judged."""
    return {"isResolved": resolved, "isOutdated": outdated, "path": "a.py",
            "opening": {"nodes": [comments[0]]}, "last": {"nodes": [comments[-1]]}}


def issue_comment(login, body):
    """A REST issue comment; login None gives a null user."""
    return {"user": None if login is None else {"login": login}, "body": body}


def state(sha):
    return f"<!-- pr-review:state sha={sha} -->"


class JudgeTests(unittest.TestCase):
    def test_resolved_thread_passes(self):
        t = thread(node("alice", "nit"), resolved=True)
        self.assertEqual(ts.evaluate([t], HEAD, None), [])

    def test_marker_at_head_passes_for_each_bot_login(self):
        for login in ("github-actions", "github-actions[bot]", "claude[bot]"):
            with self.subTest(login=login):
                t = thread(node("alice", "please fix"), node(login, marker(HEAD)))
                self.assertEqual(ts.evaluate([t], HEAD, None), [])
                self.assertEqual(ts.settled_count([t], HEAD, None), 1)

    def test_older_marker_passes_when_head_is_reviewed(self):
        t = thread(node("alice", "please fix"), node("github-actions", marker(OLD)))
        self.assertEqual(ts.evaluate([t], HEAD, HEAD), [])
        self.assertEqual(ts.settled_count([t], HEAD, HEAD), 1)

    def test_older_marker_with_older_review_is_unsettled(self):
        t = thread(node("alice", "please fix"), node("github-actions", marker(OLD)))
        for reviewed in (OLD, None):
            with self.subTest(reviewed=reviewed):
                [(url, reason)] = ts.evaluate([t], HEAD, reviewed)
                self.assertEqual(url, URL)
                self.assertIn("has not been reviewed since", reason)

    def test_human_reply_after_marker_is_unsettled(self):
        t = thread(node("alice", "please fix"), node("github-actions", marker(HEAD)), node("alice", "still broken"))
        [(_, reason)] = ts.evaluate([t], HEAD, HEAD)
        self.assertEqual(reason, "last comment is from alice")

    def test_later_non_marker_bot_comment_is_unsettled(self):
        t = thread(node("alice", "please fix"), node("github-actions", marker(HEAD)), node("claude", "thanks"))
        [(_, reason)] = ts.evaluate([t], HEAD, HEAD)
        self.assertEqual(reason, "the bot's last comment is not a settled reply")

    def test_open_thread_without_marker_is_unsettled(self):
        t = thread(node("alice", "please fix"), node("github-actions", "a finding, no marker"))
        [(_, reason)] = ts.evaluate([t], HEAD, HEAD)
        self.assertEqual(reason, "the bot's last comment is not a settled reply")

    def test_human_posting_marker_text_is_unsettled(self):
        t = thread(node("alice", "please fix"), node("alice", marker(HEAD)))
        [(_, reason)] = ts.evaluate([t], HEAD, HEAD)
        self.assertEqual(reason, "last comment is from alice")

    def test_null_author_on_last_comment_is_unsettled(self):
        t = thread(node("alice", "please fix"), node(None, marker(HEAD)))
        [(_, reason)] = ts.evaluate([t], HEAD, HEAD)
        self.assertEqual(reason, "last comment is from a deleted user")

    def test_outdated_open_thread_is_ignored(self):
        t = thread(node("alice", "please fix"), node("alice", "still here"), outdated=True)
        self.assertEqual(ts.evaluate([t], HEAD, None), [])
        self.assertEqual(ts.judge(t, HEAD, None)[0], "outdated")

    def test_url_falls_back_to_last_comment(self):
        t = {"isResolved": False, "isOutdated": False, "opening": {"nodes": []},
             "last": {"nodes": [node("alice", "hi", url="https://example.test/last")]}}
        self.assertEqual(ts.judge(t, HEAD, None)[1], "https://example.test/last")

    def test_thread_without_comments_is_unsettled(self):
        t = {"isResolved": False, "isOutdated": False, "opening": {"nodes": []}, "last": {"nodes": []}}
        [(url, reason)] = ts.evaluate([t], HEAD, None)
        self.assertIsNone(url)
        self.assertEqual(reason, "the thread has no comments")

    def test_settled_count_counts_only_settled_threads(self):
        threads = [
            thread(node("alice", "x"), node("github-actions", marker(HEAD))),
            thread(node("alice", "x"), resolved=True),
            thread(node("alice", "x"), node("bob", "y")),
        ]
        self.assertEqual(ts.settled_count(threads, HEAD, None), 1)
        self.assertEqual(len(ts.evaluate(threads, HEAD, None)), 1)


class ReviewedShaTests(unittest.TestCase):
    def test_last_bot_state_comment_wins(self):
        comments = [issue_comment("github-actions[bot]", state(NEW)),
                    issue_comment("github-actions[bot]", state(OLD))]
        self.assertEqual(ts.reviewed_sha(comments), OLD)

    def test_human_mallory_and_null_user_state_comments_are_ignored(self):
        comments = [issue_comment("github-actions[bot]", state(OLD)),
                    issue_comment("mallory", state(MAL)),
                    issue_comment(None, state(MAL)),
                    issue_comment("alice", state(MAL))]
        self.assertEqual(ts.reviewed_sha(comments), OLD)

    def test_claude_bot_state_comment_counts(self):
        self.assertEqual(ts.reviewed_sha([issue_comment("claude[bot]", state(NEW))]), NEW)

    def test_none_without_a_bot_state_comment(self):
        self.assertIsNone(ts.reviewed_sha([]))
        self.assertIsNone(ts.reviewed_sha([issue_comment("mallory", state(MAL)), issue_comment(None, "hi")]))


class PendingRunsTests(unittest.TestCase):
    RUNS = [
        {"id": 1, "name": "PR review", "status": "in_progress"},
        {"id": 2, "name": "PR review", "status": "completed"},
        {"id": 3, "name": "threads-settled", "status": "queued"},
        {"id": 4, "name": "PR review", "status": "queued"},
    ]

    def test_filters_by_name_excludes_own_run_and_drops_completed(self):
        pending = ts.pending_runs(self.RUNS, "PR review", 4)
        self.assertEqual([r["id"] for r in pending], [1])

    def test_own_run_id_compares_as_string(self):
        self.assertEqual([r["id"] for r in ts.pending_runs(self.RUNS, "PR review", "1")], [4])
        self.assertEqual([r["id"] for r in ts.pending_runs(self.RUNS, "PR review", 1)], [4])

    def test_no_own_run_id_excludes_nothing(self):
        self.assertEqual([r["id"] for r in ts.pending_runs(self.RUNS, "PR review", "")], [1, 4])


class WaitTests(unittest.TestCase):
    """wait_for_review with fetch_runs and sleep replaced: it must not pass before the review's run exists."""

    def run_wait(self, batches, appear=180, minutes=20):
        calls = []
        def fake_fetch(repo, head):
            calls.append(1)
            return batches[min(len(calls), len(batches)) - 1]
        saved = (ts.fetch_runs, ts.time.sleep, ts.APPEAR_SECONDS)
        ts.fetch_runs, ts.time.sleep, ts.APPEAR_SECONDS = fake_fetch, (lambda s: None), appear
        try:
            with open(os.devnull, "w") as null:
                old, sys.stdout = sys.stdout, null
                try:
                    return ts.wait_for_review("o/r", "a" * 40, "PR review", "99", minutes), len(calls)
                finally:
                    sys.stdout = old
        finally:
            ts.fetch_runs, ts.time.sleep, ts.APPEAR_SECONDS = saved

    def test_waits_until_the_review_run_appears_and_completes(self):
        own = {"id": 99, "name": "Threads settled", "status": "in_progress"}
        batches = [[own], [own, {"id": 1, "name": "PR review", "status": "queued"}],
                   [own, {"id": 1, "name": "PR review", "status": "completed"}]]
        self.assertEqual(self.run_wait(batches), (True, 3))

    def test_no_review_run_at_all_checks_as_is_after_the_grace(self):
        self.assertEqual(self.run_wait([[]], appear=0), (True, 1))

    def test_a_review_still_running_at_the_deadline_fails(self):
        ok, _ = self.run_wait([[{"id": 1, "name": "PR review", "status": "in_progress"}]], minutes=0)
        self.assertFalse(ok)

    def test_no_wait_when_no_workflow_is_named(self):
        self.assertTrue(ts.wait_for_review("o/r", "a" * 40, "", "1", 20))


class CliTests(unittest.TestCase):
    def run_cli(self, threads, comments, pr="5", summary=False):
        """Runs the script offline; returns (process, step summary text or None)."""
        with tempfile.TemporaryDirectory() as d:
            tf, cf = Path(d) / "threads.json", Path(d) / "comments.json"
            tf.write_text(json.dumps(threads))
            cf.write_text(json.dumps(comments))
            env = {k: v for k, v in os.environ.items()
                   if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_STEP_SUMMARY")}
            summary_path = Path(d) / "summary.md"
            if summary:
                env["GITHUB_STEP_SUMMARY"] = str(summary_path)
            proc = subprocess.run(
                [sys.executable, str(CI / "threads_settled.py"), "--pr", pr, "--head", HEAD,
                 "--threads-file", str(tf), "--comments-file", str(cf)],
                capture_output=True, text=True, env=env, timeout=60)
            text = summary_path.read_text() if summary and summary_path.exists() else None
        return proc, text

    def test_pass_exits_0_with_summary_line(self):
        threads = [thread(node("alice", "x"), resolved=True),
                   thread(node("alice", "x"), node("github-actions", marker(HEAD)))]
        proc, _ = self.run_cli(threads, [])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("every open review thread is resolved or settled (1 settled by the review's reply)", proc.stdout)

    def test_failure_exits_1_and_names_the_thread(self):
        url = "https://example.test/pr/5#discussion_r2"
        threads = [thread(node("alice", "x"), node("github-actions", marker(HEAD))),
                   thread(node("alice", "please fix", url=url), node("alice", "still broken", url=url))]
        proc, _ = self.run_cli(threads, [])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(f"UNSETTLED {url}: last comment is from alice", proc.stdout)
        self.assertIn("1 open thread(s) not settled", proc.stdout)

    def test_empty_pr_exits_2(self):
        proc, _ = self.run_cli([], [], pr="")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("not a pull request event", proc.stdout)

    def test_step_summary_is_written_when_set(self):
        proc, text = self.run_cli([thread(node("alice", "x"), node("bob", "y"))], [], summary=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIsNotNone(text)
        self.assertIn("### Review threads", text)
        self.assertIn(f"[{URL}]({URL}): last comment is from bob", text)
        proc, text = self.run_cli([], [], summary=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Every open review thread is resolved or settled.", text)

    def test_network_mode_without_a_token_exits_2_before_any_request(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_STEP_SUMMARY")}
        proc = subprocess.run(
            [sys.executable, str(CI / "threads_settled.py"), "--repo", "owner/name", "--pr", "5",
             "--head", HEAD, "--wait-for", ""],
            capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("no token: set GH_TOKEN or GITHUB_TOKEN", proc.stdout)


class DriftGuardTests(unittest.TestCase):
    def test_review_writes_the_markers_the_script_reads(self):
        text = (CI / "pr-review.yml.in").read_text()
        fixed = "<!-- pr-review:fixed sha=$HEAD_SHA -->"
        state_line = "<!-- pr-review:state sha=$HEAD_SHA -->"
        self.assertIn(fixed, text)
        self.assertIn(state_line, text)
        sample = "e" * 40
        m = ts.FIXED_RE.search(fixed.replace("$HEAD_SHA", sample))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), sample)
        m = ts.STATE_RE.search(state_line.replace("$HEAD_SHA", sample))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), sample)


def _code_lines(text):
    """Non-blank, non-comment lines of a YAML file."""
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


class GeneratedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = GENERATED.read_text()

    def test_is_a_reusable_workflow(self):
        self.assertIn("workflow_call", self.text)

    def test_has_no_uses_and_no_secrets(self):
        code = _code_lines(self.text)
        self.assertFalse([line for line in code if "uses:" in line], "uses: found")
        self.assertFalse([line for line in code if "secrets" in line], "secrets found")

    def test_job_permissions_are_exactly_read_only_pulls_and_actions(self):
        if yaml is None:
            self.skipTest("PyYAML is not importable")
        data = yaml.safe_load(self.text)
        jobs = data["jobs"]
        self.assertTrue(jobs)
        for name, job in jobs.items():
            with self.subTest(job=name):
                self.assertEqual(job.get("permissions"), {"pull-requests": "read", "actions": "read"})

    def test_contains_the_heredoc_lines(self):
        self.assertIn("<<'TS_EOF'", self.text)
        self.assertIn("\n" + " " * 10 + "TS_EOF\n", self.text)


class CallerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = CALLER.read_text()

    def test_triggers_include_review_comments(self):
        if yaml is None:
            self.skipTest("PyYAML is not importable")
        data = yaml.safe_load(self.text)
        triggers = data.get("on", data.get(True))
        self.assertIn("pull_request_review_comment", triggers)

    def test_permissions_are_only_read(self):
        if yaml is None:
            self.skipTest("PyYAML is not importable")
        data = yaml.safe_load(self.text)
        expected = {"pull-requests": "read", "actions": "read"}
        self.assertEqual(data.get("permissions"), expected)
        for name, job in (data.get("jobs") or {}).items():
            if "permissions" in job:
                with self.subTest(job=name):
                    self.assertEqual(job["permissions"], expected)

    def test_no_write_permission_and_no_secrets(self):
        code = _code_lines(self.text)
        self.assertFalse([line for line in code if "write" in line], "write permission found")
        self.assertFalse([line for line in code if "secrets" in line], "secrets found")


class TemplateTests(unittest.TestCase):
    def test_template_pins_the_version_placeholder(self):
        self.assertIn("@{{VERSION}}", TEMPLATE.read_text())


if __name__ == "__main__":
    unittest.main()
