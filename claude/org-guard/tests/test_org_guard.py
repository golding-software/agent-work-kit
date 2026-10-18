import io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import org_guard as g  # noqa: E402

PAT = g.remote_pattern(["Acme"], None)


def repo(path, origin=None):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
    return path


class PatternTest(unittest.TestCase):
    def test_urls(self):
        for u in ["https://github.com/Acme/api.git", "https://github.com/acme/api", "git@github.com:Acme/api.git",
                  "ssh://git@github.com/Acme/api", "https://x-access-token@github.com/Acme/api.git"]:
            self.assertTrue(PAT.match(u), u)
        for u in ["https://github.com/Acme-Evil/api.git", "https://github.com/someone/api.git",
                  "https://gitlab.com/Acme/api.git", "https://github.com/Acme/api/extra/path", "https://github.com.evil.io/Acme/x"]:
            self.assertFalse(PAT.match(u), u)


class RepoTest(unittest.TestCase):
    def setUp(self):
        self.t = Path(tempfile.mkdtemp())
        self.p = mock.patch.object(g, "verified", lambda url: "nonexistent" not in url)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_cases(self):
        org = repo(self.t / "api", "https://github.com/Acme/api.git")
        self.assertTrue(g.in_org_repo(org, PAT)[0])
        (org / "src").mkdir()
        self.assertTrue(g.in_org_repo(org / "src" / "new_file.py", PAT)[0])      # a file about to be created
        self.assertFalse(g.in_org_repo(repo(self.t / "mine", "https://github.com/me/x.git"), PAT)[0])
        self.assertFalse(g.in_org_repo(repo(self.t / "noremote"), PAT)[0])
        plain = self.t / "plain"; plain.mkdir()
        self.assertFalse(g.in_org_repo(plain, PAT)[0])
        fake = repo(self.t / "fake", "https://github.com/Acme/nonexistent.git")    # remote that doesn't exist
        self.assertFalse(g.in_org_repo(fake, PAT)[0])
        subprocess.run(["git", "-C", str(org), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        wt = self.t / "wt"
        subprocess.run(["git", "-C", str(org), "worktree", "add", "-q", str(wt)], check=True)
        self.assertTrue(g.in_org_repo(wt, PAT)[0])

    def run_hook(self, event):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["org_guard.py", "--org", "Acme"]), \
             mock.patch.object(sys, "stdin", io.StringIO(json.dumps(event))), mock.patch.object(sys, "stdout", out):
            g.main()
        return json.loads(out.getvalue()) if out.getvalue().strip() else None

    def test_hook(self):
        org = repo(self.t / "api", "https://github.com/Acme/api.git")
        mine = repo(self.t / "mine", "https://github.com/me/x.git")
        (mine / "notes.txt").write_text("x")
        self.assertIsNone(self.run_hook({"hook_event_name": "UserPromptSubmit", "cwd": str(org), "prompt": "hi"}))
        r = self.run_hook({"hook_event_name": "UserPromptSubmit", "cwd": str(mine), "prompt": "hi"})
        self.assertEqual(r["decision"], "block"); self.assertIn("gh repo create Acme/", r["reason"])
        r = self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Read", "tool_input": {"file_path": str(mine / "notes.txt")}})
        self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Edit", "tool_input": {"file_path": str(org / "a.py")}}))
        r = self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Bash", "tool_input": {"command": f"cd {mine} && ls"}})
        self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")
        r = self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Bash", "tool_input": {"command": f"git -C {mine} log"}})
        self.assertEqual(r["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Bash", "tool_input": {"command": "python3 -m pytest -q && ls /usr/bin"}}))
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(org), "tool_name": "Read", "tool_input": {"file_path": str(Path.home() / ".claude" / "x.md")}}))
        self.assertIsNone(self.run_hook({"hook_event_name": "PreToolUse", "cwd": str(mine), "tool_name": "WebSearch", "tool_input": {}}))


if __name__ == "__main__":
    unittest.main()
