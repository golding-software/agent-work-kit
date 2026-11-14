#!/usr/bin/env python3
"""Show and mark the register blocks of a work room, so a fresh session can pick a topic up.

The room's `.claude/state/register.md` holds one block per piece of work, headed `## <KEY> — <summary>`.
A block that can be resumed starts with a `RESUME:` header (the format is in the register itself) and
then its history lines. The resume prompt, if the last session wrote one, is `.claude/state/resume/<KEY>.md`.

Usage (run from anywhere inside the room; --register PATH overrides the search):
  topic.py list                                  one line per block: KEY | status | last session
  topic.py show KEY [--history N] [--json]       the header, the resume file, the last N history lines,
                                                 and what to verify (PRs, branches, paths)
  topic.py mark KEY --session NAME [--date D]    append "resumed in a fresh session (NAME)" to the block
Exit codes: 0 ok, 2 bad key or no register, 3 no block for KEY, 4 block without a RESUME: header.
Messages go to stderr. Only `mark` writes, and only inside the one block, atomically. Standard library only.
"""
import argparse, datetime, json, os, re, stat, sys, tempfile
from pathlib import Path

KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BLOCK_RE = re.compile(r"^## (\S+)")
PR_RE = re.compile(r"PR #?(\d+)")
BRANCH_RE = re.compile(r"branch (\S+)")
PATH_RE = re.compile(r"(?<![\w/.~-])(/[^\s;,)]+)")   # not the slash inside 'repo/worktree' or 'feature/x'
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(code, msg):
    print(f"topic.py: {msg}", file=sys.stderr)
    return code


def find_register(start: Path):
    for d in [start, *start.parents]:
        p = d / ".claude" / "state" / "register.md"
        if p.is_file():
            return p
    return None


def read_lines(reg: Path):
    with open(reg, encoding="utf-8", newline="") as f:
        return f.read().splitlines(keepends=True)


def parse_blocks(lines):
    """[{key, start, end}]: start is the '## ' line, end is the index after the block's last line."""
    blocks, cur, fenced = [], None, False
    for i, raw in enumerate(lines):
        t = raw.rstrip("\r\n")
        if t.lstrip().startswith(("```", "~~~")):   # a '## ' line inside a code fence (the format example) is not a block
            fenced = not fenced
            continue
        if not fenced and t.startswith("## "):
            if cur is not None:
                cur["end"] = i
                blocks.append(cur)
                cur = None
            m = BLOCK_RE.match(t)
            if m:
                cur = {"key": m.group(1).rstrip(":"), "start": i, "end": len(lines)}
    if cur is not None:
        blocks.append(cur)
    return blocks


def find_block(blocks, key):
    for b in blocks:
        if b["key"].lower() == key.lower():
            return b
    return None


def block_text(lines, b):
    return [l.rstrip("\r\n") for l in lines[b["start"]:b["end"]]]


def header_span(bl):
    """(start, end) of the RESUME: line and the '- ' lines right after it, relative to the block; or None."""
    for i, t in enumerate(bl):
        if t.startswith("RESUME:"):
            j = i + 1
            while j < len(bl) and bl[j].startswith("- "):
                j += 1
            return i, j
    return None


def history_index(bl, hs):
    """Index of the 'History:' line after the header, or None."""
    for i in range(hs[1], len(bl)):
        if bl[i].strip() == "History:":
            return i
    return None


def history_of(bl, hs):
    h = history_index(bl, hs)
    if h is not None:
        return [l for l in bl[h + 1:] if l.startswith("- ")]
    return [l for i, l in enumerate(bl) if l.startswith("- ") and not (hs[0] <= i < hs[1])]


def field(header_lines, name):
    for l in header_lines:
        if l.startswith(f"- {name}:"):
            return l[2:].strip()
    return "-"


def uniq(items):
    seen = []
    for x in items:
        if x not in seen:
            seen.append(x)
    return seen


def verify_items(header_lines):
    prs, branches, paths = [], [], []
    for l in header_lines:
        prs += PR_RE.findall(l)
        branches += BRANCH_RE.findall(l)
        paths += PATH_RE.findall(l)
    return {"prs": [int(p) for p in uniq(prs)], "branches": uniq(branches), "paths": uniq(paths)}


def cmd_list(reg):
    lines = read_lines(reg)
    blocks = parse_blocks(lines)
    if not blocks:
        print("(no blocks)")
        return 0
    for b in blocks:
        bl = block_text(lines, b)
        hs = header_span(bl)
        if hs is None:
            print(f"{b['key']} | - | -")
        else:
            head = bl[hs[0]:hs[1]]
            print(f"{b['key']} | {field(head, 'status')} | {field(head, 'last session')}")
    return 0


def lookup(reg, key):
    """(lines, block, block lines, header span) or an exit code."""
    if not KEY_RE.match(key):
        return fail(2, f"invalid key '{key}': use letters, digits, '.', '_' or '-'")
    lines = read_lines(reg)
    blocks = parse_blocks(lines)
    b = find_block(blocks, key)
    if b is None:
        names = ", ".join(x["key"] for x in blocks) or "(none)"
        return fail(3, f"no block for {key} in {reg}; blocks: {names}")
    bl = block_text(lines, b)
    hs = header_span(bl)
    if hs is None:
        return fail(4, f"block {b['key']} has no RESUME: header, so it can't be resumed safely. "
                       "Add the header (format in .claude/state/register.md) or read the block by hand.")
    return lines, b, bl, hs


def cmd_show(reg, key, n, as_json):
    if n < 0:
        return fail(2, "--history must be 0 or more")
    found = lookup(reg, key)
    if isinstance(found, int):
        return found
    _, b, bl, hs = found
    header = bl[hs[0]:hs[1]]
    history = history_of(bl, hs)
    history = history[max(0, len(history) - n):] if n else []
    resume = reg.parent / "resume" / f"{b['key']}.md"
    resume_text = resume.read_text(encoding="utf-8") if resume.is_file() else None
    verify = verify_items(header)
    if as_json:
        out = {"key": b["key"], "header": header, "resume_file": str(resume) if resume_text is not None else None,
               "history": history, "verify": verify}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    print("\n".join(header))
    print()
    if resume_text is not None:
        print(f"resume file: {resume}")
        print(resume_text.rstrip("\n"))
    else:
        print(f"(no resume file: .claude/state/resume/{b['key']}.md)")
    print()
    print(f"history (last {len(history)}):")
    for h in history:
        print(h)
    print()
    print("verify:")
    for p in verify["prs"]:
        print(f"  PR {p}")
    for br in verify["branches"]:
        print(f"  branch {br}")
    for p in verify["paths"]:
        print(f"  path {p}")
    return 0


def mark_lines(bl, hs, entry):
    """Lines to insert into the block (relative index, new lines): the entry goes after the last history line."""
    h = history_index(bl, hs)
    if h is not None:
        after = [i for i in range(h + 1, len(bl)) if bl[i].startswith("- ")]
        return (after[-1] if after else h) + 1, [entry]
    later = [i for i in range(hs[1], len(bl)) if bl[i].startswith("- ")]
    if later:
        return later[-1] + 1, [entry]
    # No history yet: a '- ' line straight after the header would read as part of the header.
    return hs[1], ["History:", entry]


def cmd_mark(reg, key, session, date):
    if "\n" in session or "\r" in session or not session.strip():
        return fail(2, "--session needs a one-line name")
    if not DATE_RE.match(date):
        return fail(2, "--date must be YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        return fail(2, f"--date {date} is not a real date")
    found = lookup(reg, key)
    if isinstance(found, int):
        return found
    lines, b, bl, hs = found
    at, new = mark_lines(bl, hs, f"- {date} resumed in a fresh session ({session.strip()})")
    absolute = b["start"] + at
    if absolute > 0 and not lines[absolute - 1].endswith("\n"):
        lines[absolute - 1] += "\n"
    lines[absolute:absolute] = [t + "\n" for t in new]
    fd, tmp = tempfile.mkstemp(dir=reg.parent, prefix=".register-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("".join(lines))
        os.chmod(tmp, stat.S_IMODE(reg.stat().st_mode))
        os.replace(tmp, reg)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    print(f"marked {b['key']}: {new[-1][2:]}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Show and mark a work room's register blocks for a fresh session.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "show", "mark"):
        p = sub.add_parser(name)
        p.add_argument("--register", metavar="PATH", help="the register file (default: the nearest .claude/state/register.md)")
        if name in ("show", "mark"):
            p.add_argument("key")
        if name == "show":
            p.add_argument("--history", type=int, default=5, metavar="N", help="history lines to show (default 5)")
            p.add_argument("--json", action="store_true", help="print JSON instead of text")
        if name == "mark":
            p.add_argument("--session", required=True, metavar="NAME", help="the session that resumes the topic")
            p.add_argument("--date", default=datetime.date.today().isoformat(), metavar="YYYY-MM-DD")
    a = ap.parse_args(argv)
    if a.register:
        reg = Path(a.register).expanduser().resolve()
        if not reg.is_file():
            return fail(2, f"no register at {reg}")
    else:
        reg = find_register(Path.cwd())
        if reg is None:
            return fail(2, "no .claude/state/register.md here or above; pass --register PATH")
    if a.cmd == "list":
        return cmd_list(reg)
    if a.cmd == "show":
        return cmd_show(reg, a.key, a.history, a.json)
    return cmd_mark(reg, a.key, a.session, a.date)


if __name__ == "__main__":
    sys.exit(main())
