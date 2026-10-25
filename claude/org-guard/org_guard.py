#!/usr/bin/env python3
"""org_guard: keep an organisation-paid Claude Code account on the organisation's repositories.

Installed as a MANAGED hook (scripts/managed-guard.py prints the managed-settings block), so a
developer's own settings cannot switch it off. Two events:

- UserPromptSubmit: if the session's working directory is not inside one of the organisation's
  repositories, the prompt is blocked with an explanation. New work for the organisation starts by
  creating its repository in the organisation (`gh repo create <Org>/<name> --private --clone`).
- PreToolUse: a file tool (Read, Edit, Write, MultiEdit, NotebookEdit, Glob, Grep) aimed at a path
  outside the organisation's repositories, or a Bash command run from such a folder, is denied.

"The organisation's repositories": a git working tree (worktrees included) whose `origin` remote
points at the organisation on its git host, AND which the remote confirms exists (`git ls-remote`,
cached for a day), so pointing a personal folder's remote at the organisation is not enough. Claude
Code's own folders (~/.claude, the config dir, its /tmp scratchpads) stay readable so skills work.

Usage (as the hook command): org_guard.py --org <Org> [--org <Org2>] [--host github.com]
Standard library and git only. Client-side enforcement raises the bar; it is not tamper-proof:
review Claude Code analytics as well.
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

FILE_TOOLS = {"Read": "file_path", "Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path", "Glob": "path", "Grep": "path"}
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "org-guard" / "verified.json"
CACHE_TTL = 24 * 3600


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", action="append", required=True, help="organisation / group name on the git host")
    ap.add_argument("--host", action="append", help="git host, default github.com")
    return ap.parse_args()


def remote_pattern(orgs, hosts):
    h = "|".join(re.escape(x) for x in (hosts or ["github.com"]))
    o = "|".join(re.escape(x) for x in orgs)
    # https://host/Org/repo(.git), git@host:Org/repo, ssh://git@host/Org/repo, with optional user@
    return re.compile(rf"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|[^@/\s]+@)?(?:{h})[:/](?:{o})/[^/\s]+?(?:\.git)?/?$", re.I)


def git(path, *a, timeout=10):
    try:
        r = subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def verified(url):
    try:
        data = json.loads(CACHE.read_text())
    except Exception:
        data = {}
    if time.time() - data.get(url, 0) < CACHE_TTL:
        return True
    rc, _ = git(".", "ls-remote", "--exit-code", "-q", url, "HEAD", timeout=20)
    if rc in (0, 2):          # 2 = reachable but no HEAD (an empty new repository)
        data[url] = time.time()
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(data))
        except Exception:
            pass
        return True
    return False


def claude_dirs():
    home = Path.home()
    dirs = [home / ".claude", Path("/tmp"), Path(os.environ.get("TMPDIR", "/tmp"))]
    if os.environ.get("CLAUDE_CONFIG_DIR"):
        dirs.append(Path(os.environ["CLAUDE_CONFIG_DIR"]))
    return [d.resolve() for d in dirs if str(d)]


def is_claude_dir(p: Path):
    home = Path.home().resolve()
    if home in p.parents and p.relative_to(home).parts[0].startswith("."):
        return True                       # ~/.claude, ~/.local/bin, ~/.nvm ...: tools and config, not projects
    for d in claude_dirs():
        if d == Path("/tmp").resolve():
            if re.match(r"^/tmp/claude-[^/]+(/|$)", str(p)):   # Claude Code's scratchpads only
                return True
            continue
        if p == d or d in p.parents:
            return True
    return False


def in_org_repo(path: Path, pat):
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent                      # a file about to be created: judge its folder
    if not p.is_dir():
        p = p.parent
    rc, top = git(p, "rev-parse", "--show-toplevel")
    if rc != 0:
        return False, "not inside a git repository"
    rc, url = git(top, "config", "--get", "remote.origin.url")
    if rc != 0 or not url:
        return False, f"{top} has no origin remote"
    if not pat.match(url):
        return False, f"{top} belongs to {url}"
    if not verified(url):
        return False, f"{url} could not be confirmed with the git host"
    return True, top


def bash_paths(cmd, cwd: Path):
    """Paths a shell command moves into or names inside the home folder."""
    home = Path.home().resolve()
    out = []
    for m in re.finditer(r"(?:^|[;&|(\s])(?:cd|pushd)\s+([^\s;&|)]+)|git\s+-C\s+([^\s;&|)]+)", cmd):
        raw = (m.group(1) or m.group(2) or "").strip("'\"")
        if raw and raw != "-":
            p = Path(raw).expanduser()
            out.append((cwd / p if not p.is_absolute() else p).resolve())
    for tok in re.findall(r"(?:(?<=\s)|^)(~[^\s;&|)'\"]*|/[^\s;&|)'\"]+)", cmd):
        p = Path(tok).expanduser()
        try:
            p = p.resolve()
        except Exception:
            continue
        if (p == home or home in p.parents) and p.exists():
            out.append(p)
    return out


def message(orgs, why):
    org = orgs[0]
    return (f"This Claude Code account is provided by {', '.join(orgs)} for work in {org}'s repositories only "
            f"({why}). Open Claude in a clone of one of {org}'s repositories. New work for {org}, a proof of "
            f"concept included, starts by creating its repository in {org} first, for example: "
            f"`gh repo create {org}/<name> --private --clone`. Personal projects need your own Claude account.")


def main():
    a = args()
    pat = remote_pattern(a.org, a.host)
    try:
        ev = json.load(sys.stdin)
    except Exception:
        return 0
    name = ev.get("hook_event_name")
    cwd = Path(ev.get("cwd") or os.getcwd()).expanduser()
    if name == "UserPromptSubmit":
        ok, why = in_org_repo(cwd, pat)
        if not ok:
            print(json.dumps({"decision": "block", "reason": message(a.org, why)}))
        return 0
    if name == "PreToolUse":
        tool = ev.get("tool_name", "")
        ti = ev.get("tool_input") or {}
        if tool in FILE_TOOLS:
            raw = ti.get(FILE_TOOLS[tool]) or ""
            target = (Path(raw).expanduser() if raw else cwd)
            target = (cwd / target if not target.is_absolute() else target).resolve()
            if is_claude_dir(target):
                return 0
        elif tool == "Bash":
            target = cwd.resolve()
            # Where the command goes or what it touches in the home folder must be org repositories too.
            # (System paths outside $HOME are not checked: tools and packages live there.)
            for p in bash_paths(ti.get("command") or "", cwd):
                ok, why = in_org_repo(p, pat)
                if not ok and not is_claude_dir(p):
                    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                             "permissionDecisionReason": message(a.org, why)}}))
                    return 0
        else:
            return 0
        ok, why = in_org_repo(target, pat)
        if not ok:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": message(a.org, why)}}))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
