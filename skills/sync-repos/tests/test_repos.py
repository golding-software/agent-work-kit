import os, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import repos  # noqa: E402

MANIFEST = """# Repositories

clone-root: ../code

| Repo | Clone URL | Purpose |
|---|---|---|
| api | git@github.com:acme/api.git | backend |
| [web](https://github.com/acme/web) | `https://github.com/acme/web.git` | front end |
| <name> | <url> | template row, ignored |
"""


class ParseTest(unittest.TestCase):
    def test_parse(self):
        root, rows = repos.parse_manifest(MANIFEST)
        self.assertEqual(root, "../code")
        self.assertEqual([r["repo"] for r in rows], ["api", "web"])
        self.assertEqual(rows[1]["url"], "https://github.com/acme/web.git")

    def test_root_order(self):
        room = Path("/w/acme/work-room")
        os.environ.pop("WORK_ROOM_CLONE_ROOT", None)
        self.assertEqual(repos.resolve_root(room, None), Path("/w/acme"))
        self.assertEqual(repos.resolve_root(room, "../code"), Path("/w/acme/code"))
        os.environ["WORK_ROOM_CLONE_ROOT"] = "/src"
        try:
            self.assertEqual(repos.resolve_root(room, "../code"), Path("/src"))
        finally:
            del os.environ["WORK_ROOM_CLONE_ROOT"]


class CloneStatusTest(unittest.TestCase):
    def test_clone_then_status(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / "origin" / "api"
            src.mkdir(parents=True)
            run = lambda *a, cwd=src: subprocess.run(a, cwd=cwd, check=True, capture_output=True)
            run("git", "init", "-q", "-b", "main")
            (src / "a.txt").write_text("x")
            run("git", "add", ".")
            run("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
            room = t / "acme" / "work-room"
            (room / ".claude").mkdir(parents=True)
            (room / ".claude" / "repos.md").write_text(f"| Repo | Clone URL |\n|---|---|\n| api | {src} |\n")
            cwd = os.getcwd()
            os.chdir(room)
            try:
                self.assertEqual(repos.main(["clone"]), 0)
                self.assertTrue((t / "acme" / "api" / "a.txt").exists())
                self.assertEqual(repos.main(["clone"]), 0)          # second run leaves it alone
                s = repos.status_of(t / "acme" / "api", fetch=False)
                self.assertEqual((s["cloned"], s["branch"], s["changed"]), (True, "main", 0))
                self.assertEqual(repos.main(["clone", "nope"]), 2)
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
