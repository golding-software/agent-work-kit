#!/usr/bin/env python3
"""Build every tool- and surface-specific copy from the tool-neutral sources.

Sources: skills/<name>/ (Agent Skills standard: Claude and Codex both read SKILL.md folders), ci/ (the
PR review), claude/plugins/*/agents and manifests (Claude-only). This script derives the rest and
checks the rules every surface shares:

  1. validate   every SKILL.md against the strictest rules (Claude API Skills: name <= 64 chars of
                [a-z0-9-] without "claude"/"anthropic", description 1..1024 chars, no XML tags),
                unique skill names across plugins, no ${CLAUDE_PLUGIN_ROOT} in skill content (only
                Claude Code substitutes it), files that must stay identical are identical.
  2. mirror     skills/<name>/ -> claude/plugins/<plugin>/skills/<name>/ (what the Claude plugins ship),
                .claude/skills/<name>/ (Claude Managed Agents on a mounted repo, `ant apply`) and
                .agents/skills/<name>/ (Codex's repository skill folder); tests/ and caches left out.
  3. agents     claude/plugins/*/agents/*.md -> managed-agents/agents/<name>/agent.md (+ environment.yaml),
                the files `ant apply` turns into Managed Agents: the orchestrator as a coordinator
                with its workers as the roster.
  4. workflow   ci/pr-review.yml.in + ci/fetch-ticket.sh + the review-pr rubric ->
                .github/workflows/pr-review.yml, the shared (workflow_call) PR review.
  5. --zip      dist/skills/<name>.zip for the Skills API console upload or claude.ai.

Usage: scripts/build.py            write everything
       scripts/build.py --check    write nothing; exit 1 if anything is stale or invalid (CI)
       scripts/build.py --zip      also write dist/skills/*.zip
Standard library only.
"""
import filecmp, os, re, shutil, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
PLUGINS = ROOT / "claude" / "plugins"
# Which Claude plugin ships which skill.
SKILL_PLUGIN = {"setup-work-room": "work-room", "sync-repos": "work-room",
                "setup-pr-review": "pr-review", "review-pr": "pr-review"}
MIRRORS = {".claude/skills": ROOT / ".claude" / "skills", ".agents/skills": ROOT / ".agents" / "skills"}
MA = ROOT / "managed-agents" / "agents"
WORKFLOW = ROOT / ".github" / "workflows" / "pr-review.yml"
SKIP = {"tests", "__pycache__", ".pytest_cache"}
SAME = [  # files kept identical in two skills, because each skill must be self-contained
    ("skills/review-pr/rubric.md", "skills/setup-pr-review/templates/rubric.md"),
]

# Managed Agents: one entry per plugin agent that has a Managed Agents counterpart. worker-opus is
# left out: it exists for orchestrators running above Opus, and the coordinator here runs on Opus.
MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}
AGENTS = {
    "work-room": dict(src="work-room/agents/orchestrator.md", model="opus",
                      skills=["setup-work-room", "sync-repos", "review-pr"],
                      roster=["implementer", "worker-haiku", "worker-sonnet"], environment=True),
    "implementer": dict(src="work-room/agents/implementer.md", model="sonnet"),
    "worker-sonnet": dict(src="work-room/agents/worker-sonnet.md", model="sonnet"),
    "worker-haiku": dict(src="work-room/agents/worker-haiku.md", model="haiku"),
}
MA_PREFACE = """You are running as a Claude Managed Agent, not inside Claude Code. Differences that matter:

- The project's repository is mounted in your container; its path is in the session's resources.
  Read its rules (`AGENTS.md`, or `.claude/CLAUDE.md` in older rooms) and `.claude/state/register.md`.
- Your workers are your roster{roster}. Delegate with the delegation tools you were given (one
  self-contained brief per task, the worktree path included); they cannot delegate further.
- There is no `AskUserQuestion` tool: when you wait on the user, end your turn with one clear
  question and the options.
- Pushing branches and opening PRs needs the credentials and MCP servers the session was given; if
  they are missing, prepare the branch and tell the user what is left.

"""

errors = []


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    fm, key = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            fm[key] = "" if val in (">-", ">", "|", "|-") else val
        elif key and line.startswith((" ", "\t")):
            fm[key] = (fm[key] + " " + line.strip()).strip()
    return fm, text[m.end():]


def skills():
    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        yield skill_md.parent


def validate():
    seen = {}
    for d in skills():
        rel = d.relative_to(ROOT)
        fm, body = frontmatter((d / "SKILL.md").read_text())
        if fm is None:
            errors.append(f"{rel}: SKILL.md has no frontmatter"); continue
        name, desc = fm.get("name", ""), fm.get("description", "")
        if name != d.name:
            errors.append(f"{rel}: name '{name}' must equal the directory name")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name) or re.search(r"claude|anthropic", name):
            errors.append(f"{rel}: name '{name}' breaks the API rules ([a-z0-9-], <= 64, no claude/anthropic)")
        if not 0 < len(desc) <= 1024:
            errors.append(f"{rel}: description is {len(desc)} chars (1..1024)")
        if re.search(r"<[A-Za-z/][^>]*>", name + desc):
            errors.append(f"{rel}: XML-like tag in name or description")
        if name not in SKILL_PLUGIN:
            errors.append(f"{rel}: add '{name}' to SKILL_PLUGIN in scripts/build.py (which Claude plugin ships it)")
        if name in seen:
            errors.append(f"{rel}: skill name '{name}' also used by {seen[name]}")
        seen[name] = rel
        for f in d.rglob("*"):
            if f.is_file() and not (SKIP & set(f.relative_to(d).parts)) and f.suffix in (".md", ".sh", ".py", ".yml", ".yaml", ".json"):
                if "CLAUDE_PLUGIN_ROOT" in f.read_text(errors="ignore"):
                    errors.append(f"{f.relative_to(ROOT)}: ${{CLAUDE_PLUGIN_ROOT}} only resolves in Claude Code; use a path relative to the skill directory")
    for a, b in SAME:
        if not filecmp.cmp(ROOT / a, ROOT / b, shallow=False):
            errors.append(f"{a} and {b} must be identical (copy one over the other)")


def copy_skill(src, dst):
    shutil.copytree(src, dst, ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith(".pyc")])


def build_mirror(out, plugin=None):
    out.mkdir(parents=True, exist_ok=True)
    for d in skills():
        if plugin is None or SKILL_PLUGIN.get(d.name) == plugin:
            copy_skill(d, out / d.name)


def build_agents(out):
    for name, spec in AGENTS.items():
        fm, body = frontmatter((PLUGINS / spec["src"]).read_text())
        lines = ["---", f"# Generated by scripts/build.py from claude/plugins/{spec['src']}: edit that file, then rebuild.", f"name: {name}", f"description: >-\n  {fm.get('description', '').strip()}",
                 f"model: {MODELS[spec['model']]}", "tools:", "  - type: agent_toolset_20260401",
                 "    default_config: {permission_policy: {type: auto}}", "    configs:",
                 "      - {name: web_search, enabled: false}", "      - {name: web_fetch, enabled: false}"]
        if spec.get("skills"):
            lines.append("skills:")
            lines += [f"  - ../../../.claude/skills/{s}" for s in spec["skills"]]
        if spec.get("roster"):
            lines.append("multiagent:\n  type: coordinator\n  agents:")
            lines += [f"    - ../{r}/agent.md" for r in spec["roster"]]
        lines.append("---")
        roster = ": " + ", ".join(f"`{r}`" for r in spec["roster"]) if spec.get("roster") else " (none: you do the work yourself)"
        preface = MA_PREFACE.format(roster=roster) if spec.get("roster") else (
            "You are running as a Claude Managed Agent worker. The project repository is mounted in the "
            "container; its path is in the session's resources and in your brief.\n\n")
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "agent.md").write_text("\n".join(lines) + "\n\n" + preface + body.lstrip())
        if spec.get("environment"):
            (d / "environment.yaml").write_text(
                "# Generated by scripts/build.py. Package installs on, the open internet off: list the\n"
                "# hosts the room needs (git host, tracker, registries) under allowed_hosts.\n"
                "config: {type: cloud, networking: {type: limited, allow_package_managers: true, allowed_hosts: []}}\n")


def build_workflow():
    indent = lambda text: "\n".join(("          " + l) if l.strip() else "" for l in text.rstrip("\n").splitlines())
    tpl = (ROOT / "ci" / "pr-review.yml.in").read_text()
    script = (ROOT / "ci" / "fetch-ticket.sh").read_text().split("\n", 1)[1]   # drop the shebang
    rubric = (SKILLS / "review-pr" / "rubric.md").read_text()
    if "RUBRIC_EOF" in rubric:
        errors.append("rubric.md must not contain the line RUBRIC_EOF")
    return tpl.replace("@@FETCH_TICKET@@", indent(script)).replace("@@RUBRIC@@", indent(rubric))


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(same_tree(Path(a) / s, Path(b) / s) for s in cmp.common_dirs)


def main():
    check, zips = "--check" in sys.argv, "--zip" in sys.argv
    validate()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        build_agents(tmp / "agents")
        targets = [(tmp / "agents", MA, "managed-agents/agents")]
        for label, target in MIRRORS.items():
            build_mirror(tmp / label.replace("/", "_"))
            targets.append((tmp / label.replace("/", "_"), target, label))
        for plugin in sorted(set(SKILL_PLUGIN.values())):
            build_mirror(tmp / f"plugin-{plugin}", plugin)
            targets.append((tmp / f"plugin-{plugin}", PLUGINS / plugin / "skills", f"claude/plugins/{plugin}/skills"))
        for built, target, label in targets:
            if check:
                if not target.exists() or not same_tree(built, target):
                    errors.append(f"{label} is stale: run scripts/build.py")
            else:
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(built, target)
    wf = build_workflow()
    if check:
        if not WORKFLOW.exists() or WORKFLOW.read_text() != wf:
            errors.append(".github/workflows/pr-review.yml is stale: run scripts/build.py")
    else:
        WORKFLOW.parent.mkdir(parents=True, exist_ok=True)
        WORKFLOW.write_text(wf)
    if zips and not errors:
        dist = ROOT / "dist" / "skills"
        dist.mkdir(parents=True, exist_ok=True)
        for d in skills():
            with zipfile.ZipFile(dist / f"{d.name}.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(d.rglob("*")):
                    rel = f.relative_to(d)
                    if f.is_file() and not (SKIP & set(rel.parts)) and f.suffix != ".pyc":
                        z.write(f, Path(d.name) / rel)
    for e in errors:
        print("ERROR:", e, file=sys.stderr)
    if not errors:
        print("ok:", ", ".join(d.name for d in skills()), "|", ", ".join(AGENTS), "| workflow", "| check" if check else "")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
