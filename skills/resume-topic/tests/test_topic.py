import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "topic.py"

REGISTER = """# Register: live state of this room's work

One block per piece of work.

## ALPHA — first topic
RESUME: (rewritten after every step; the history below only grows)
- status: implementing — writing the parser
- next: run the tests
- waiting on: nothing
- in flight: repo/worktree /w/acme/api; branch feature/ALPHA-1 (pushed: no); PR #12; workers worker-haiku (returned, commit abc1234)
- last session: first, 2026-11-01

History:
- 2026-10-30 started
- 2026-10-31 parser drafted

## BETA — no header
- status: investigating
- repo / worktree: /w/acme/web

## GAMMA — third topic
RESUME: (rewritten after every step; the history below only grows)
- status: blocked — waiting for the client
- next: ask about the fee
- waiting on: the client
- in flight: nothing
- last session: second, 2026-11-02

History:
- 2026-11-02 blocked

"""

ALPHA_HISTORY_LAST = "- 2026-10-31 parser drafted\n"


class TopicTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.room = Path(tmp.name) / "acme" / "work-room"
        state = self.room / ".claude" / "state"
        (state / "resume").mkdir(parents=True)
        self.reg = state / "register.md"
        self.reg.write_text(REGISTER, encoding="utf-8")
        (state / "resume" / "GAMMA.md").write_text("Resume prompt for GAMMA: call the client.\n", encoding="utf-8")
        (self.room / "src" / "deep").mkdir(parents=True)

    def run_topic(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.room, capture_output=True, text=True)

    def test_list(self):
        r = self.run_topic("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], "ALPHA | status: implementing — writing the parser | last session: first, 2026-11-01")
        self.assertEqual(lines[1], "BETA | - | -")
        self.assertEqual(lines[2], "GAMMA | status: blocked — waiting for the client | last session: second, 2026-11-02")
        self.assertEqual(len(lines), 3)

    def test_list_walks_up_from_a_subfolder(self):
        r = self.run_topic("list", cwd=self.room / "src" / "deep")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BETA | - | -", r.stdout)

    def test_format_example_in_a_code_fence_is_not_a_block(self):
        template = (Path(__file__).resolve().parents[2] / "setup-work-room" / "templates" / "register.md").read_text()
        self.reg.write_text(template + "\n" + REGISTER.split("One block per piece of work.\n", 1)[1], encoding="utf-8")
        r = self.run_topic("list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([l.split(" | ")[0] for l in r.stdout.splitlines()], ["ALPHA", "BETA", "GAMMA"])

    def test_show_alpha_json(self):
        r = self.run_topic("show", "alpha", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["key"], "ALPHA")
        self.assertEqual(out["header"][0], "RESUME: (rewritten after every step; the history below only grows)")
        self.assertEqual(out["header"][-1], "- last session: first, 2026-11-01")
        self.assertEqual(out["history"], ["- 2026-10-30 started", "- 2026-10-31 parser drafted"])
        self.assertIsNone(out["resume_file"])
        self.assertEqual(out["verify"], {"prs": [12], "branches": ["feature/ALPHA-1"], "paths": ["/w/acme/api"]})

    def test_show_alpha_text_and_history_limit(self):
        r = self.run_topic("show", "ALPHA")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(no resume file: .claude/state/resume/ALPHA.md)", r.stdout)
        self.assertIn("- 2026-10-30 started", r.stdout)
        self.assertIn("  PR 12", r.stdout)
        self.assertIn("  branch feature/ALPHA-1", r.stdout)
        self.assertIn("  path /w/acme/api", r.stdout)
        r = self.run_topic("show", "ALPHA", "--history", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("- 2026-10-30 started", r.stdout)
        self.assertIn("- 2026-10-31 parser drafted", r.stdout)
        r = self.run_topic("show", "ALPHA", "--history", "1", "--json")
        self.assertEqual(json.loads(r.stdout)["history"], ["- 2026-10-31 parser drafted"])

    def test_show_gamma_includes_resume_file(self):
        r = self.run_topic("show", "GAMMA")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Resume prompt for GAMMA: call the client.", r.stdout)
        out = json.loads(self.run_topic("show", "GAMMA", "--json").stdout)
        self.assertTrue(out["resume_file"].endswith("resume/GAMMA.md"))

    def test_show_block_without_header(self):
        r = self.run_topic("show", "BETA")
        self.assertEqual(r.returncode, 4)
        self.assertIn("no RESUME: header", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_show_missing_key_lists_blocks(self):
        r = self.run_topic("show", "MISSING")
        self.assertEqual(r.returncode, 3)
        self.assertIn("no block for MISSING", r.stderr)
        self.assertIn("blocks: ALPHA, BETA, GAMMA", r.stderr)

    def test_invalid_key(self):
        for key in ["bad key", "../ALPHA", "ALPHA;rm"]:
            r = self.run_topic("show", key)
            self.assertEqual(r.returncode, 2, key)
            self.assertIn("invalid key", r.stderr)
        self.assertEqual(self.run_topic("show", "-x").returncode, 2)   # argparse refuses a leading dash

    def test_mark_alpha_touches_only_its_block(self):
        before = self.reg.read_text(encoding="utf-8")
        r = self.run_topic("mark", "ALPHA", "--session", "fresh-2", "--date", "2026-11-03")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.reg.read_text(encoding="utf-8")
        expected = before.replace(
            ALPHA_HISTORY_LAST, ALPHA_HISTORY_LAST + "- 2026-11-03 resumed in a fresh session (fresh-2)\n", 1)
        self.assertEqual(after, expected)
        beta_gamma = before[before.index("## BETA"):]
        self.assertTrue(after.endswith(beta_gamma))
        out = json.loads(self.run_topic("show", "ALPHA", "--json", "--history", "9").stdout)
        self.assertEqual(out["history"][-1], "- 2026-11-03 resumed in a fresh session (fresh-2)")

    def test_mark_beta_is_refused(self):
        before = self.reg.read_text(encoding="utf-8")
        r = self.run_topic("mark", "BETA", "--session", "x")
        self.assertEqual(r.returncode, 4)
        self.assertEqual(self.reg.read_text(encoding="utf-8"), before)

    def test_mark_header_only_block_gets_a_history_label(self):
        self.reg.write_text(self.reg.read_text(encoding="utf-8") + "\n## DELTA — header only\nRESUME:\n- status: pr-open — waiting\n",
                            encoding="utf-8")
        r = self.run_topic("mark", "DELTA", "--session", "s", "--date", "2026-11-04")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(self.run_topic("show", "DELTA", "--json").stdout)
        self.assertEqual(out["header"], ["RESUME:", "- status: pr-open — waiting"])
        self.assertEqual(out["history"], ["- 2026-11-04 resumed in a fresh session (s)"])

    def test_mark_rejects_bad_date_and_name(self):
        before = self.reg.read_text(encoding="utf-8")
        self.assertEqual(self.run_topic("mark", "ALPHA", "--session", "s", "--date", "2026-13-01").returncode, 2)
        self.assertEqual(self.run_topic("mark", "ALPHA", "--session", "a\nb").returncode, 2)
        self.assertEqual(self.reg.read_text(encoding="utf-8"), before)

    def test_no_register_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, str(SCRIPT), "list"], cwd=t, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("no .claude/state/register.md", r.stderr)

    def test_register_flag(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "list", "--register", str(self.reg)],
                           cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ALPHA |", r.stdout)


if __name__ == "__main__":
    unittest.main()
