#!/usr/bin/env python3
"""List, check and clone an organisation's repositories for a work room.

The room's `.claude/repos.md` lists the repositories: a Markdown table whose columns include
"Repo" and "Clone URL" (any other columns, such as "Purpose", are kept for people and Claude).
Repositories are cloned side by side in the clone root, which is, in order:
  1. the WORK_ROOM_CLONE_ROOT environment variable (a developer's own layout),
  2. a `clone-root: <path>` line in repos.md,
  3. `..`: the folder that holds the room, so the room and the repos are siblings.
A relative path is relative to the room (the folder that holds `.claude/repos.md`).

Usage (run from anywhere inside the room):
  repos.py status [--fetch] [--json]   one line per repo: cloned?, branch, changed files, ahead/behind
  repos.py clone [REPO ...]            clone the missing ones (all, or the named ones); never touches
                                       a folder that already exists
  repos.py where                       print the room and the clone root
Read-only except `clone` (and `status --fetch`, which runs `git fetch`). Never pulls, resets or
deletes. Standard library only.
"""
import json, os, re, subprocess, sys
from pathlib import Path


def find_room(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".claude" / "repos.md").is_file():
            return d
    sys.exit("repos.py: no .claude/repos.md here or above; run /work-room:setup-work-room in the org room first")


def parse_manifest(text: str):
    clone_root, rows, header = None, [], None
    for line in text.splitlines():
        m = re.match(r"^\s*clone-root:\s*(\S.*?)\s*$", line, re.I)
        if m:
            clone_root = m.group(1).strip("`\"'")
            continue
        if not line.strip().startswith("|"):
            header = None if not line.strip() else header
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        low = [c.lower() for c in cells]
        if "repo" in low and any("url" in c for c in low):
            header = {"repo": low.index("repo"), "url": next(i for i, c in enumerate(low) if "url" in c)}
            continue
        if header and len(cells) > max(header.values()):
            name, url = cells[header["repo"]], cells[header["url"]]
            name = re.sub(r"^\[([^\]]+)\]\(.*\)$", r"\1", name)
            if name and url and not name.startswith("<"):
                rows.append({"repo": name, "url": url, "row": cells})
    return clone_root, rows


def resolve_root(room: Path, manifest_root):
    raw = os.environ.get("WORK_ROOM_CLONE_ROOT") or manifest_root or ".."
    p = Path(os.path.expanduser(raw))
    return (p if p.is_absolute() else room / p).resolve()


def git(path: Path, *args):
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def status_of(path: Path, fetch: bool):
    if not (path / ".git").exists():
        return {"cloned": False}
    if fetch:
        git(path, "fetch", "--quiet", "--prune")
    _, branch = git(path, "branch", "--show-current")
    _, dirty = git(path, "status", "--porcelain")
    rc, counts = git(path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    behind, ahead = (counts.split() + ["?", "?"])[:2] if rc == 0 else ("-", "-")
    _, worktrees = git(path, "worktree", "list", "--porcelain")
    return {"cloned": True, "branch": branch or "(detached)", "changed": len([l for l in dirty.splitlines() if l]),
            "ahead": ahead, "behind": behind, "worktrees": max(0, worktrees.count("worktree ") - 1)}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    room = find_room(Path.cwd())
    clone_root, rows = parse_manifest((room / ".claude" / "repos.md").read_text())
    root = resolve_root(room, clone_root)
    if cmd == "where":
        print(f"room: {room}\nclone root: {root}"); return 0
    if cmd == "status":
        out = [{"repo": r["repo"], "path": str(root / r["repo"]), **status_of(root / r["repo"], "--fetch" in rest)} for r in rows]
        if "--json" in rest:
            print(json.dumps(out, indent=2)); return 0
        print(f"clone root: {root}")
        for s in out:
            if not s["cloned"]:
                print(f"  {s['repo']:<28} not cloned"); continue
            print(f"  {s['repo']:<28} {s['branch']:<24} changed {s['changed']:<3} ahead {s['ahead']:<3} behind {s['behind']:<3} worktrees {s['worktrees']}")
        return 0
    if cmd == "clone":
        wanted = set(rest)
        unknown = wanted - {r["repo"] for r in rows}
        if unknown:
            print("not in repos.md: " + ", ".join(sorted(unknown)), file=sys.stderr); return 2
        root.mkdir(parents=True, exist_ok=True)
        failed = 0
        for r in rows:
            if wanted and r["repo"] not in wanted:
                continue
            dest = root / r["repo"]
            if dest.exists():
                print(f"  {r['repo']:<28} exists, left alone"); continue
            rc = subprocess.run(["git", "clone", "--quiet", r["url"], str(dest)]).returncode
            print(f"  {r['repo']:<28} {'cloned' if rc == 0 else 'CLONE FAILED'}")
            failed += rc != 0
        return 1 if failed else 0
    print(f"repos.py: unknown command {cmd!r}; see --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
