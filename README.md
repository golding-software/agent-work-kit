# Agent work kit

Two plugins for doing client work with Claude, from the setup we run at our own clients:

| Plugin | What it gives you |
|---|---|
| [**work-room**](claude/plugins/work-room) | One room per client or project: an orchestrator that sizes each request and runs the lightest loop that fits, a Haiku/Sonnet/Opus worker ladder, a shared register so parallel sessions don't collide, and rules you own in `AGENTS.md`. |
| [**pr-review**](claude/plugins/pr-review) | PR review that checks the change against its **ticket** (Jira or GitHub issue) as well as the code, and approves clean PRs: every requirement marked met, partly met or not met, out-of-scope changes flagged, findings with severity and line. A shared GitHub Actions workflow any repository calls by version tag, plus an on-demand skill. |

## Install (Claude Code)

```sh
claude plugin marketplace add golding-software/agent-work-kit
claude plugin install work-room@golding-work
claude plugin install pr-review@golding-work
```

Then, in the project: `/work-room:setup-work-room` (a short interview, then the room's files). For CI
review, `/pr-review:setup-pr-review` writes the caller workflow.

## Rolling it out to an organisation

Three layers, so the generic room keeps updating while each organisation customises freely:

1. **work-room** from this marketplace (never forked);
2. the organisation's **`<org>/work-room`** repository: the folder developers open Claude in, with the
   organisation's rules, the list of its repositories (cloned next to it), and a small conventions
   plugin that depends on work-room ([template](templates/org-work-room));
3. each repository's committed `AGENTS.md` and `.claude/settings.json`, for sessions opened
   inside a repository.

Managed settings in the organisation's Claude Team or Enterprise account enforce the plugins, cap
usage, set the privacy options and, when the organisation pays for the seats, keep those accounts on
the organisation's repositories ([org guard](claude/org-guard/org_guard.py): work outside them is
refused, and new work starts by creating its repository in the organisation). Step by step: [docs/rollout.md](docs/rollout.md).

## Works across Claude surfaces

The skills are written to one common standard (paths relative to the skill, Python standard
library only, no Claude Code-only tools assumed), so the same content runs on:

| Surface | How to load it |
|---|---|
| **Claude Code** | the plugins above |
| **Claude Agent SDK** | `plugins=[{"type": "local", "path": ".../plugins/work-room"}, ...]` plus `setting_sources=["project"]` to read the room's `.claude/` files ([example](docs/surfaces.md#agent-sdk)) |
| **Claude API (Messages)** | upload a skill from [`.claude/skills/`](.claude/skills) or `dist/skills/*.zip` with the Skills API, then pass it in `container.skills` with the code execution tool ([example](docs/surfaces.md#messages-api)) |
| **Claude Managed Agents** | `ant apply` the [`managed-agents/`](managed-agents) definitions (the orchestrator as a coordinator with its workers as the roster), or mount your repo: Managed Agents discovers `.claude/skills/` in a mounted GitHub repository ([details](docs/surfaces.md#managed-agents)) |

What differs per surface, and what was tested where: [docs/surfaces.md](docs/surfaces.md).

## Contributing

The plugins under `plugins/` are the source. `.claude/skills/` and `managed-agents/` are generated:
run `python3 scripts/build.py` after any change (CI runs `--check`).

MIT licensed. Made by [Golding Software](https://goldingsoftware.com.au).

## Built with Claude

This kit was designed, written and tested by Horacio Golding together with Claude (Anthropic's Claude Code). It is a team effort and every commit says so with a `Co-Authored-By` trailer. The claims in this repository are limited to what was measured; the evaluation numbers come from our own small evaluations, described in `docs/competitive-analysis.md` and the plugin READMEs.
