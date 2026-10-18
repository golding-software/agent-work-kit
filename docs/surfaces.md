# Using the plugins on each Claude surface

The **skills** are the portable part: each is a folder with a `SKILL.md`, Python scripts that use
only the standard library, and paths relative to the skill folder. The **agents** (orchestrator,
implementer, workers) are Claude Code subagents; Managed Agents gets generated equivalents.

| | Claude Code | Agent SDK | Messages API | Managed Agents |
|---|---|---|---|---|
| Skills | plugin | plugin (`plugins` option) | Skills API upload + `container.skills` | Skills API upload, or `.claude/skills/` in a mounted repo |
| Orchestrator + workers | plugin agents | plugin agents | none (no subagents; use the orchestrator text as your system prompt) | `managed-agents/` coordinator + roster |
| Room files (`AGENTS.md`, settings) | read automatically | `setting_sources=["project"]` | not read: put rules in the system prompt | read from the mounted repo (the agent is told to) |
| Network, local tools | the user's machine | your host | **none**: sandbox, no network, no installs | the environment's networking settings |
| Asking the user | `AskUserQuestion` | `AskUserQuestion` (your app answers it) | plain text | end the turn with the question |
| Tested | yes (every skill, 2026-10-10) | yes (`review-pr`, plugin and agent loading, 2026-10-10) | not yet | not yet |

## Claude Code

```sh
claude plugin marketplace add golding-software/agent-work-kit
claude plugin install work-room@golding-work
claude plugin install pr-review@golding-work
```

## Agent SDK

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

PLUGINS = "/path/to/claude-plugins/plugins"   # a clone of this repo

async def main():
    options = ClaudeAgentOptions(
        cwd="/path/to/your/project",
        plugins=[{"type": "local", "path": f"{PLUGINS}/work-room"},
                 {"type": "local", "path": f"{PLUGINS}/pr-review"}],
        setting_sources=["project"],   # read the room's .claude/settings.json and CLAUDE.md
    )
    async for message in query(prompt="/pr-review:review-pr Review this branch against main.", options=options):
        print(message)

asyncio.run(main())
```

Check the `init` system message: `plugins`, `skills` and `agents` list what loaded, and
`plugin_errors` says why something did not.

## Messages API

Upload the skills once (they are shared across the workspace), then reference them per request.
Skills on the API run in the code-execution sandbox: no network and no package installs, so give the
skill its inputs (a diff, a ticket) as files or in the message.

```python
import anthropic
from anthropic.lib import files_from_dir

client = anthropic.Anthropic()

# once per skill (re-upload to publish a new version)
skill = client.skills.create(files=files_from_dir(".claude/skills/review-pr"))

response = client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    betas=["code-execution-2025-08-25"],
    container={"skills": [{"type": "custom", "skill_id": skill.id, "version": "latest"}]},
    tools=[{"type": "code_execution_20260521", "name": "code_execution"}],
    messages=[{"role": "user", "content": "Review this diff against the ticket below.\n\n<diff>...</diff>\n\n<ticket>...</ticket>"}],
)
```

`dist/skills/*.zip` (from `python3 scripts/build.py --zip`) suits the Console upload and claude.ai.

## Managed Agents

Two ways to give a Managed Agent these skills:

1. **Mount the repository** that holds them: a session's `github_repository` resource makes the
   repo's root `.claude/skills/<name>/` available to the agent at session start. This repo's own
   `.claude/skills/` is laid out that way, and a project that copies them there gets the same.
2. **`ant apply` the definitions** in `managed-agents/`, which uploads the skills and creates the
   agents (needs the `ant` CLI, 1.30 or later):

```sh
ant apply --dry-run managed-agents/agents     # review the plan
ant apply --yes managed-agents/agents         # create or update; writes claude-lock.json
```

`work-room` is a coordinator whose roster is `implementer`, `worker-sonnet` and `worker-haiku`; its
environment allows package managers and no other hosts until you list them in
`managed-agents/agents/work-room/environment.yaml`. Start sessions with the project repository
mounted, so the agent can read the room's `AGENTS.md` and register.
