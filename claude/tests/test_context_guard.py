import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "plugins" / "work-room" / "hooks" / "context_guard.py"


def usage_line(tokens, model="claude-sonnet-5-5", sidechain=False):
    obj = {"type": "assistant", "message": {"model": model, "usage": {
        "input_tokens": 1, "cache_read_input_tokens": tokens - 1, "cache_creation_input_tokens": 0}}}
    if sidechain:
        obj["isSidechain"] = True
    return json.dumps(obj) + "\n"


class GuardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.cache = self.dir / "cache"
        self.transcript = self.dir / "session.jsonl"
        self.session = "abc-123_x.y"

    def write_transcript(self, *lines):
        self.transcript.write_text("".join(lines), encoding="utf-8")

    def run_hook(self, event="UserPromptSubmit", env=None, session=None, transcript=None):
        data = {"session_id": self.session if session is None else session, "hook_event_name": event,
                "transcript_path": str(self.transcript if transcript is None else transcript),
                "cwd": str(self.dir)}
        base = {k: v for k, v in os.environ.items() if not k.startswith("WORK_ROOM_CONTEXT")}
        base["XDG_CACHE_HOME"] = str(self.cache)
        base.update(env or {})
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data), capture_output=True,
                              text=True, env=base, timeout=30)

    def test_off_by_default(self):
        self.write_transcript(usage_line(400000))
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_on_below_threshold_is_silent(self):
        self.write_transcript(usage_line(120000))
        r = self.run_hook(env={"WORK_ROOM_CONTEXT_GUARD": "on"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_above_threshold_prints_once_per_session(self):
        self.write_transcript(usage_line(310000))
        env = {"WORK_ROOM_CONTEXT_GUARD": "ON"}
        r = self.run_hook(env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertIn("CONTEXT CHECK: this session is at 310K tokens", out["additionalContext"])
        self.assertIn(".claude/state/resume/<KEY>.md", out["additionalContext"])
        self.assertIn("/work-room:resume-topic <KEY>", out["additionalContext"])
        again = self.run_hook(env=env)
        self.assertEqual((again.returncode, again.stdout), (0, ""))

    def test_haiku_threshold(self):
        self.write_transcript(usage_line(96000, model="claude-haiku-5-5"))
        r = self.run_hook(env={"WORK_ROOM_CONTEXT_GUARD": "1"})
        self.assertIn("CONTEXT CHECK", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
        self.write_transcript(usage_line(96000, model="claude-sonnet-5-5"))
        r = self.run_hook(env={"WORK_ROOM_CONTEXT_GUARD": "1"}, session="other-session")
        self.assertEqual(r.stdout, "")

    def test_token_override(self):
        self.write_transcript(usage_line(2000))
        env = {"WORK_ROOM_CONTEXT_GUARD": "true", "WORK_ROOM_CONTEXT_TOKENS": "1000"}
        r = self.run_hook(env=env)
        self.assertIn("CONTEXT CHECK", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_bad_override_falls_back_to_default(self):
        self.write_transcript(usage_line(2000))
        env = {"WORK_ROOM_CONTEXT_GUARD": "on", "WORK_ROOM_CONTEXT_TOKENS": "many"}
        self.assertEqual(self.run_hook(env=env).stdout, "")

    def test_sidechain_is_ignored(self):
        self.write_transcript(usage_line(120000), usage_line(900000, sidechain=True))
        r = self.run_hook(env={"WORK_ROOM_CONTEXT_GUARD": "on"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_missing_or_garbage_transcript_is_silent(self):
        env = {"WORK_ROOM_CONTEXT_GUARD": "on"}
        r = self.run_hook(env=env, transcript=self.dir / "nope.jsonl")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.write_transcript("not json\n{\"type\": \"assistant\"\n")
        r = self.run_hook(env=env)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = subprocess.run([sys.executable, str(HOOK)], input="garbage", capture_output=True, text=True,
                           env={"WORK_ROOM_CONTEXT_GUARD": "on", "PATH": os.environ.get("PATH", "")})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_event_name_follows_input(self):
        self.write_transcript(usage_line(310000))
        r = self.run_hook(event="PostToolUse", env={"WORK_ROOM_CONTEXT_GUARD": "on"})
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"], "PostToolUse")


if __name__ == "__main__":
    unittest.main()
