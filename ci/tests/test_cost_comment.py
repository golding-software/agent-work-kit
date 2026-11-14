"""Tests for ci/cost_comment.py (the review cost on the summary comment), and for the generated workflow that inlines it."""
import subprocess, sys, tempfile, unittest
from pathlib import Path

CI = Path(__file__).resolve().parent.parent
ROOT = CI.parent
sys.path.insert(0, str(CI))
import cost_comment as cc  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "pr-review.yml"
SUMMARY = ("**Verdict: ready** (0 blockers, 0 majors, 1 findings in all).\n\n## Summary\nLooks good.\n\n"
           "<sub>Review of commit abc1234 (full review). This comment is updated on every push.</sub>")


class PartsTests(unittest.TestCase):
    def test_good_blank_and_junk_lines(self):
        text = "1-review 0.00113\n\n   \nnonsense\n2-confirm 0.011\nthree fields here\n2-confirm x\n"
        self.assertEqual(cc.read_parts(text), [("1-review", 0.00113), ("2-confirm", 0.011)])

    def test_order_is_kept(self):
        self.assertEqual(cc.read_parts("2-confirm 0.5\n1-review 0.1\n"), [("2-confirm", 0.5), ("1-review", 0.1)])


    def test_nan_inf_and_negative_values_are_skipped(self):
        text = "1-review nan\n2-confirm inf\n3-x -inf\n4-y -0.5\n5-ok 0.002\n"
        self.assertEqual(cc.read_parts(text), [("5-ok", 0.002)])
        self.assertEqual(cc.format_line(cc.read_parts("1-review nan\n")), "Review cost: not recorded for this run")


class FormatTests(unittest.TestCase):
    def test_two_parts(self):
        self.assertEqual(cc.format_line([("1-review", 0.0013), ("2-confirm", 0.011)]),
                         "Review cost: $0.0123 (1-review $0.001, 2-confirm $0.011)")

    def test_one_part(self):
        self.assertEqual(cc.format_line([("1-review", 0.0011)]), "Review cost: $0.0011 (1-review $0.001)")

    def test_no_parts(self):
        self.assertEqual(cc.format_line([]), "Review cost: not recorded for this run")


class WithCostTests(unittest.TestCase):
    def test_fresh_summary_keeps_the_body_and_ends_with_one_cost_line(self):
        line = "Review cost: $0.0123 (1-review $0.001, 2-confirm $0.011)"
        out = cc.with_cost(SUMMARY, line)
        self.assertEqual(out, SUMMARY + "\n\n" + cc.MARK + "\n" + line + "\n")
        self.assertEqual(out.count(cc.MARK), 1)

    def test_incremental_push_leaves_only_the_new_line(self):
        old = cc.with_cost(SUMMARY, "Review cost: $0.0100 (1-review $0.010)")
        new = "Review cost: $0.0200 (1-review $0.020)"
        out = cc.with_cost(old, new)
        self.assertEqual(out.count(cc.MARK), 1)
        self.assertNotIn("$0.0100", out)
        self.assertEqual(out, cc.with_cost(SUMMARY, new))

    def test_trailing_text_after_an_old_cost_line_is_replaced(self):
        old = cc.with_cost(SUMMARY, "Review cost: $0.0100 (1-review $0.010)") + "\nText added after the cost line\n"
        new = "Review cost: $0.0200 (1-review $0.020)"
        out = cc.with_cost(old, new)
        self.assertEqual(out.count(cc.MARK), 1)
        self.assertNotIn("Text added after", out)
        self.assertEqual(out, cc.with_cost(SUMMARY, new))


class CliTests(unittest.TestCase):
    def run_cli(self, parts_text=None):
        with tempfile.TemporaryDirectory() as d:
            body = Path(d) / "body.md"
            body.write_text(SUMMARY, encoding="utf-8")
            parts = Path(d) / "parts.txt"
            if parts_text is not None:
                parts.write_text(parts_text, encoding="utf-8")
            r = subprocess.run([sys.executable, str(CI / "cost_comment.py"), "--body-file", str(body),
                                "--parts-file", str(parts)], capture_output=True, text=True, encoding="utf-8")
        return r

    def test_missing_parts_file_means_no_parts_and_exit_0(self):
        r = self.run_cli()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, cc.with_cost(SUMMARY, "Review cost: not recorded for this run"))

    def test_parts_file_gives_the_cost_line(self):
        r = self.run_cli("1-review 0.00130\n2-confirm 0.011\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, cc.with_cost(SUMMARY, "Review cost: $0.0123 (1-review $0.001, 2-confirm $0.011)"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.wf = WORKFLOW.read_text(encoding="utf-8")

    def step(self, name):
        head = f"      - name: {name}\n"
        self.assertEqual(self.wf.count(head), 1, name)
        start = self.wf.index(head)
        end = self.wf.find("\n      - name:", start + len(head))
        return self.wf[start:end if end != -1 else len(self.wf)]

    def test_input_cost_in_comment_defaults_to_true(self):
        self.assertEqual(self.wf.count("      cost-in-comment:\n"), 1)
        block = self.wf.split("      cost-in-comment:\n", 1)[1].split("      incremental:\n", 1)[0]
        self.assertIn("        type: boolean\n        default: true\n", block)

    def test_new_step_is_gated_by_the_input_and_not_shadow(self):
        step = self.step("Add the cost to the review summary")
        if_line = next(l for l in step.splitlines() if l.strip().startswith("if:"))
        self.assertIn("inputs.cost-in-comment", if_line)
        self.assertIn("!inputs.shadow", if_line)

    def test_new_step_comes_right_after_cost_of_this_run(self):
        cost = self.wf.index("      - name: Cost of this run\n")
        add = self.wf.index("      - name: Add the cost to the review summary\n")
        self.assertGreater(add, cost)
        self.assertEqual(self.wf.count("      - name:", cost, add), 1)

    def test_inlined_module_is_the_file_and_has_no_expression_or_eof(self):
        src = (CI / "cost_comment.py").read_text(encoding="utf-8")
        self.assertNotIn("COST_EOF", src)
        self.assertNotIn("${{", src)
        step = self.step("Add the cost to the review summary")
        for line in src.rstrip("\n").splitlines():
            if line.strip():
                self.assertIn("          " + line + "\n", step)


if __name__ == "__main__":
    unittest.main()
