#!/usr/bin/env python3
"""Print the managed-settings block that keeps an organisation-paid Claude Code account on the
organisation's repositories (claude/org-guard/org_guard.py, inlined so it needs no installed file).

  scripts/managed-guard.py --org Acme [--org AcmeLabs] [--host github.com] [--host gitlab.example.com]

Merge the printed "hooks" into the organisation's managed settings (Organization settings ->
Claude Code -> Managed settings). Managed hooks can't be switched off from a developer's own settings.
"""
import json, shlex, sys
from pathlib import Path

argv = sys.argv[1:]
if not argv or "--org" not in argv:
    sys.exit(__doc__)
code = (Path(__file__).resolve().parent.parent / "claude" / "org-guard" / "org_guard.py").read_text()
cmd = "python3 -c " + shlex.quote(code) + " " + " ".join(shlex.quote(a) for a in argv)
hook = {"type": "command", "command": cmd, "timeout": 30}
print(json.dumps({"hooks": {
    "UserPromptSubmit": [{"hooks": [hook]}],
    "PreToolUse": [{"matcher": "Read|Edit|Write|MultiEdit|NotebookEdit|Glob|Grep|Bash", "hooks": [hook]}],
}}, indent=2))
