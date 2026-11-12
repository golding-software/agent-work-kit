"""Tests for ci/api_review.py, with a fake Claude client (no network, no anthropic package needed)."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import api_review as ar  # noqa: E402

DIFF = """diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 import os
-x = 1
+x = 2
+++y = 3
 def f():
     return x
diff --git a/old.txt b/old.txt
deleted file mode 100644
--- a/old.txt
+++ /dev/null
@@ -1 +0,0 @@
-gone
diff --git a/new.md b/new.md
new file mode 100644
--- /dev/null
+++ b/new.md
@@ -0,0 +1,2 @@
+# New
+text
"""


def usage(i=1000, o=200, rd=0, wr=0):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=rd, cache_creation_input_tokens=wr)


def text(t):
    return NS(type="text", text=t)


def tool_use(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def msg(*content, stop="end_turn", u=None, details=None):
    return NS(content=list(content), stop_reason=stop, usage=u or usage(), stop_details=details)


class FakeClient:
    """Plays back scripted responses and keeps what each request sent."""

    class Err(Exception):
        def __init__(self, status, message):
            super().__init__(message); self.status_code, self.message = status, message

    api_errors = (Err,)

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
        self.messages = self

    def stream(self, **kw):
        self.requests.append(json.loads(json.dumps(kw, default=lambda o: o.__dict__)))
        nxt = self.responses.pop(0)
        client = self

        class S:
            def __enter__(self):
                if isinstance(nxt, Exception):
                    raise nxt
                return self

            def __exit__(self, *a):
                return False

            def get_final_message(self):
                return nxt
        return S()


REVIEW_OK = {"verdict": "ready", "blockers": 0, "majors": 0, "findings": 1, "resolved": ["PRRT_a"],
             "report": "**Verdict: ready**",
             "comments": [{"path": "src/app.py", "line": 2, "severity": "minor", "body": "Name it."},
                          {"path": "src/app.py", "line": 40, "severity": "major", "body": "Off the diff."}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ws = self.dir / "repo"
        (self.ws / "src").mkdir(parents=True)
        (self.ws / "src" / "app.py").write_text("".join(f"line {n}\n" for n in range(1, 1201)))
        (self.ws / "AGENTS.md").write_text("Use tabs.\n")
        (self.ws / "bin.dat").write_bytes(b"\x00\x01\x02")
        subprocess.run(["git", "init", "-q", str(self.ws)], check=True)
        (self.ws / ".git" / "config").write_text((self.ws / ".git" / "config").read_text() + "\n# token=secret\n")
        subprocess.run(["git", "-C", str(self.ws), "add", "-A"], check=True)
        (self.dir / "outside.txt").write_text("secret\n")
        os.symlink(self.dir / "outside.txt", self.ws / "link.txt")
        (self.dir / "rubric.md").write_text("# Rubric\nBe strict.\n")
        (self.dir / "pr.diff").write_text(DIFF)
        (self.dir / "threads.json").write_text('[{"id": "PRRT_a", "comment": "**minor:** x"}]')
        self.args = ["--model", "haiku", "--rubric-file", str(self.dir / "rubric.md"), "--diff-file", str(self.dir / "pr.diff"),
                     "--threads-file", str(self.dir / "threads.json"), "--workspace", str(self.ws), "--head-sha", "a" * 40,
                     "--out", str(self.dir / "out.json"), "--usage", str(self.dir / "usage.json"),
                     "--max-turns", "10", "--max-budget-usd", "1"]
        os.environ.pop("GITHUB_OUTPUT", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, cmd, responses, extra=()):
        client = FakeClient(responses)
        rc = ar.main([cmd, *self.args, *extra], client=client)
        return rc, client


class WorkspaceTests(Base):
    def test_reads_inside_with_line_numbers_and_caps(self):
        w = ar.Workspace(self.ws)
        out = w.read_file("src/app.py", 10, 12)
        self.assertIn("src/app.py lines 10-12 of 1200", out)
        self.assertIn("    11\tline 11", out)
        out = w.read_file("src/app.py", 0, 0)
        self.assertIn(f"lines 1-{ar.READ_MAX_LINES} of 1200 (more: call again with start_line {ar.READ_MAX_LINES + 1})", out)

    def test_refuses_escapes(self):
        w = ar.Workspace(self.ws)
        for bad in ["../outside.txt", str(self.dir / "outside.txt"), "link.txt", ".git/config", "src/../.git/config", "bin.dat", "nope.txt"]:
            with self.assertRaises(ar.ToolError, msg=bad):
                w.read_file(bad)

    def test_list_dir_hides_git(self):
        out = ar.Workspace(self.ws).list_dir(".")
        self.assertIn("src/", out)
        self.assertNotIn(".git", out)
        with self.assertRaises(ar.ToolError):
            ar.Workspace(self.ws).list_dir("..")

    def test_grep(self):
        w = ar.Workspace(self.ws)
        self.assertIn("src/app.py:7:line 7", w.grep("^line 7$"))
        self.assertIn("AGENTS.md:1:Use tabs.", w.grep("tabs", "*.md"))
        self.assertEqual(w.grep("tabs", "src/**"), "no matches")
        self.assertNotIn("secret", w.grep("secret"))
        for bad in [":(exclude)x", "/etc/*", "../*"]:
            with self.assertRaises(ar.ToolError):
                w.grep("x", bad)


class DiffTests(unittest.TestCase):
    def test_right_lines(self):
        r = ar.diff_right_lines(DIFF)
        self.assertEqual(r["src/app.py"], {1, 2, 3, 4, 5})   # context, added, the "+++y" content line, context
        self.assertEqual(r["new.md"], {1, 2})
        self.assertNotIn("old.txt", r)

    def test_place_comments(self):
        comments = [{"path": "./src/app.py", "line": 2, "severity": "minor", "body": "**major:** relabelled"},
                    {"path": "src/app.py", "line": 99, "severity": "blocker", "body": "off the diff"},
                    {"path": ".github/x.yml", "line": 1, "severity": "nit", "body": "unknown file"}]
        comments += [{"path": "new.md", "line": 1, "severity": "question", "body": f"q{n}"} for n in range(12)]
        payload, rest = ar.place_comments(comments, DIFF, "b" * 40)
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(payload["commit_id"], "b" * 40)
        self.assertEqual(len(payload["comments"]), ar.MAX_INLINE_COMMENTS)
        self.assertEqual(payload["comments"][0], {"path": "src/app.py", "line": 2, "body": "**minor:** relabelled", "side": "RIGHT"})
        self.assertEqual(rest[0]["body"], "**blocker:** off the diff")
        self.assertEqual(rest[1]["path"], ".github/x.yml")
        self.assertEqual(rest[1]["body"], "**question:** unknown file")   # an unknown severity is a question
        self.assertEqual(len(rest), 2 + 3)


class CostTests(unittest.TestCase):
    def test_prices(self):
        self.assertAlmostEqual(ar.call_cost("claude-sonnet-5-5", usage(1_000_000, 100_000)), 2 + 1)
        self.assertAlmostEqual(ar.call_cost("claude-sonnet-5-5", usage(0, 0, rd=1_000_000, wr=1_000_000)), 0.2 + 2.5)
        self.assertAlmostEqual(ar.call_cost("claude-haiku-5-5", usage(50_000, 10_000)), 0.005 + 0.005)
        # over 100K prompt tokens (input + cache), the whole call is billed at Haiku's long-prompt price
        self.assertAlmostEqual(ar.call_cost("claude-haiku-5-5", usage(10_000, 10_000, rd=95_000)), (10_000 * 0.5 + 10_000 * 2.5 + 95_000 * 0.05) / 1e6)
        self.assertEqual(ar.resolve_model("sonnet"), "claude-sonnet-5-5")
        self.assertEqual(ar.resolve_model("claude-opus-5-5"), "claude-opus-5-5")


class LoopTests(Base):
    def test_review_with_a_tool_call(self):
        rc, client = self.run_main("review", [
            msg(tool_use("t1", "read_file", path="src/app.py", start_line=1, end_line=2),
                tool_use("t2", "read_file", path="../outside.txt", start_line=0, end_line=0), stop="tool_use"),
            msg(text(json.dumps(REVIEW_OK)), u=usage(500, 300, rd=900)),
        ], ["--comments", str(self.dir / "comments.json")])
        self.assertEqual(rc, 0)
        first = client.requests[0]
        self.assertEqual(first["model"], "claude-haiku-5-5")
        self.assertEqual(first["cache_control"], {"type": "ephemeral"})
        self.assertEqual(first["output_config"]["effort"], "medium")
        self.assertEqual(first["output_config"]["format"]["schema"], ar.REVIEW_SCHEMA)
        self.assertNotIn("thinking", first)          # adaptive thinking is the default
        self.assertNotIn("tool_choice", first)        # forced tool choice is a 400 on these models
        self.assertTrue(all(t["strict"] for t in first["tools"]))
        self.assertIn("Be strict.", first["system"])
        self.assertNotIn("Use tabs.", first["messages"][0]["content"][0]["text"])   # conventions not preloaded
        self.assertIn("+x = 2", first["messages"][0]["content"][0]["text"])
        results = client.requests[1]["messages"][2]["content"]   # both results in ONE user message
        self.assertEqual([r["tool_use_id"] for r in results], ["t1", "t2"])
        self.assertIn("line 2", results[0]["content"])
        self.assertTrue(results[1]["is_error"])
        out = json.loads((self.dir / "out.json").read_text())
        self.assertEqual(out["resolved"], ["PRRT_a"])
        self.assertIn("Comments that could not be placed", out["report"])
        self.assertIn("`src/app.py:40`: **major:** Off the diff.", out["report"])
        payload = json.loads((self.dir / "comments.json").read_text())
        self.assertEqual([c["line"] for c in payload["comments"]], [2])
        rec = json.loads((self.dir / "usage.json").read_text())[0]
        self.assertEqual((rec["type"], rec["subtype"], rec["is_error"], rec["num_turns"]), ("result", "success", False, 2))
        m = rec["modelUsage"]["claude-haiku-5-5"]
        self.assertEqual((m["inputTokens"], m["outputTokens"], m["cacheReadInputTokens"], m["priced"]), (1500, 500, 900, True))
        self.assertAlmostEqual(m["costUSD"], ar.call_cost("claude-haiku-5-5", usage()) + ar.call_cost("claude-haiku-5-5", usage(500, 300, rd=900)), 6)

    def test_shadow_posts_no_comments(self):
        rc, _ = self.run_main("review", [msg(text(json.dumps(REVIEW_OK)))], ["--shadow", "true", "--comments", str(self.dir / "c.json")])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads((self.dir / "c.json").read_text())["comments"], [])
        self.assertNotIn("could not be placed", json.loads((self.dir / "out.json").read_text())["report"])

    def test_confirm_and_preloaded_conventions(self):
        res = {"verdict": "ready", "blockers": 0, "majors": 0, "findings": 0, "summary": "ok"}
        rc, client = self.run_main("confirm", [msg(text(json.dumps(res)))], ["--model", "sonnet", "--preload-conventions", "true"])
        self.assertEqual(rc, 0)
        self.assertEqual(client.requests[0]["model"], "claude-sonnet-5-5")
        self.assertEqual(client.requests[0]["output_config"]["format"]["schema"], ar.CONFIRM_SCHEMA)
        self.assertIn("=== AGENTS.md ===\nUse tabs.", client.requests[0]["messages"][0]["content"][0]["text"])
        self.assertEqual(json.loads((self.dir / "out.json").read_text())["summary"], "ok")

    def test_turn_limit_closes_tools_then_fails(self):
        calls = [msg(tool_use(f"t{n}", "list_dir", path="."), stop="tool_use") for n in range(20)]
        rc, client = self.run_main("review", calls, ["--max-turns", "3"])
        self.assertEqual(rc, 1)
        self.assertEqual(len(client.requests), 3 + ar.GRACE_CALLS)
        last_results = client.requests[-1]["messages"][-1]["content"]
        self.assertTrue(last_results[0]["is_error"])
        self.assertIn("Limit reached", last_results[-1]["text"])
        rec = json.loads((self.dir / "usage.json").read_text())[0]
        self.assertEqual((rec["subtype"], rec["is_error"]), ("error_max_turns", True))

    def test_budget_stop(self):
        big = usage(0, 0, wr=400_000)   # $0.05 per call on Haiku
        calls = [msg(tool_use(f"t{n}", "list_dir", path="."), stop="tool_use", u=big) for n in range(40)]
        rc, client = self.run_main("review", calls, ["--max-budget-usd", "0.2", "--max-turns", ""])
        self.assertEqual(rc, 1)
        rec = json.loads((self.dir / "usage.json").read_text())[0]
        self.assertEqual(rec["subtype"], "error_max_budget_usd")
        self.assertLessEqual(rec["total_cost_usd"], 0.2 + 0.05 + 1e-9)   # never more than one call past the cap

    def test_invalid_json_gets_one_nudge(self):
        rc, client = self.run_main("review", [msg(text("I think it is fine.")), msg(text(json.dumps(REVIEW_OK)))])
        self.assertEqual(rc, 0)
        self.assertIn("Return the JSON result now", client.requests[1]["messages"][-1]["content"][0]["text"])
        rc, _ = self.run_main("review", [msg(text("no")), msg(text("still no"))])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads((self.dir / "usage.json").read_text())[0]["subtype"], "error_no_result")

    def test_refusal_and_api_error(self):
        rc, _ = self.run_main("review", [msg(stop="refusal", details=NS(category="cyber", explanation="declined"))])
        self.assertEqual(rc, 1)
        rec = json.loads((self.dir / "usage.json").read_text())[0]
        self.assertEqual(rec["subtype"], "refusal")
        self.assertIn("cyber", rec["result"])
        rc, _ = self.run_main("review", [msg(tool_use("t1", "list_dir", path="."), stop="tool_use"),
                                         FakeClient.Err(400, "Your credit balance is too low")])
        self.assertEqual(rc, 1)
        rec = json.loads((self.dir / "usage.json").read_text())[0]
        self.assertEqual((rec["subtype"], rec["num_turns"]), ("error_api", 1))   # the call before the error is still counted
        self.assertIn("API error 400: Your credit balance is too low", rec["result"])

    def test_long_diff_gets_read_diff(self):
        long = DIFF + "".join(f"+pad {n}\n" for n in range(60_000))
        (self.dir / "pr.diff").write_text(long)
        rc, client = self.run_main("review", [
            msg(tool_use("t1", "read_diff", start_line=3, end_line=4), stop="tool_use"),
            msg(text(json.dumps(REVIEW_OK)))])
        self.assertEqual(rc, 0)
        self.assertIn("read_diff", [t["name"] for t in client.requests[0]["tools"]])
        self.assertIn("read the rest with read_diff", client.requests[0]["messages"][0]["content"][0]["text"])
        self.assertIn("--- a/src/app.py", client.requests[1]["messages"][2]["content"][0]["content"])

    def test_github_outputs(self):
        gho = self.dir / "gho"
        os.environ["GITHUB_OUTPUT"] = str(gho)
        try:
            self.run_main("review", [msg(text(json.dumps(REVIEW_OK)))])
        finally:
            os.environ.pop("GITHUB_OUTPUT")
        out = gho.read_text()
        self.assertIn("execution_file<<APIREVIEW_", out)
        self.assertIn('structured_output<<APIREVIEW_', out)
        self.assertIn('"verdict":"ready"', out)


if __name__ == "__main__":
    unittest.main()
