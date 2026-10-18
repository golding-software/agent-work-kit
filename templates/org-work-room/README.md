# Org work room template

Template for **`<org>/work-room`**: the repository every developer at the organisation clones and
opens Claude Code in. Copy this folder into a new private repository in the organisation's GitHub
(for example `acme/work-room`).

```
~/work/acme/            one parent folder per organisation
├── work-room/          this repository: open `claude` here
│   ├── AGENTS.md       the room's rules (every coding agent reads it; CLAUDE.md imports it)
│   ├── .claude/        settings.json (Claude permissions), repos.md (the org's repos)
│   ├── .claude-plugin/ the organisation's plugin marketplace
│   └── plugin/         the acme-conventions plugin (usable in any repository's sessions too)
├── api/                the repositories, cloned next to the room by /work-room:sync-repos
└── web/
```

It gives the organisation three things:

1. **A shared room.** `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` and `.claude/repos.md` are written by
   `/work-room:setup-work-room` (choose "org room") and changed through PRs like any code. Sessions
   opened here run the work-room orchestrator, read repos.md to know where each repository is, and
   reach the clones because the room's settings add the parent folder (`".."`).
2. **The organisation's conventions plugin** (`plugin/`), for sessions opened directly inside a
   repository: tracker, specs, environments, branch/commit/PR conventions, and (Jira/Confluence
   organisations) Atlassian's MCP server. It depends on `work-room@golding-work`, so installing it
   installs the generic room, which keeps updating from golding-software/agent-work-kit.
   Nothing is forked.
3. **Enforcement**: the organisation's managed settings register this repository's marketplace and
   enable `acme-conventions@acme` and `work-room@golding-work` for everyone, and (when the organisation
   pays for the seats) install the org guard, which keeps those accounts on the organisation's
   repositories: work outside them is refused, and new work starts by creating its repository in
   the organisation.

## Set up

1. Rename `acme` / `acme-conventions` in `.claude-plugin/marketplace.json`,
   `plugin/.claude-plugin/plugin.json` and `plugin/skills/acme-conventions/`, and fill in
   `plugin/skills/<org>-conventions/SKILL.md`.
2. Jira/Confluence: rename `plugin/mcp.example.json` to `plugin/.mcp.json`.
3. `claude plugin validate --strict .` and `claude plugin validate --strict plugin`, then commit.
4. Open `claude` in the folder, run `/work-room:setup-work-room` (org room), review the files it
   writes, commit them.
5. Each developer: clone into `~/work/<org>/work-room`, open `claude` there, accept the trust prompt,
   and run `/work-room:sync-repos` to clone the repositories next to it.
