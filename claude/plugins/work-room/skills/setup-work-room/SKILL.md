---
name: setup-work-room
description: Sets up a work room for one client or project - writes the room's rules (AGENTS.md, which Claude Code reads through a one-line CLAUDE.md and Codex reads directly), Claude permissions (.claude/settings.json), and a shared register and worklog into the project, filled in from a short interview, for the user to edit afterwards. Use when the user wants to start a work room, set up Claude for a new client or project, onboard a new engagement, or asks for the work-room rules or register.
---

# Set up a work room

A work room is one project directory (usually one client or one product) where several Claude
sessions work in parallel without colliding: an orchestrator sizes each request and delegates to a
worker ladder, every piece of work has a block in a shared register, and the project's rules live in
one file the user owns, `AGENTS.md`, which every coding agent the team uses can read. This skill
writes those files. The user edits them afterwards; the room
improves each time a mistake becomes a line in `AGENTS.md`.

The templates are in `templates/`, relative to **this skill's directory** (the folder that holds this
SKILL.md). Write the results into the **project root** (the current working directory, or the
repository mounted in the container).

## 1. Look before writing

List what already exists: `AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/settings.json`,
`.claude/state/`. **Never overwrite an existing file.** If one exists, read it, write the new content
beside it as `<name>.work-room-proposed`, and show the user the difference. Also read the repo's
README and contributing guide, and list any repo skills under `.claude/skills/`: they answer some of
the questions below without asking.

## 2. Interview: one round, defaults offered

Ask these in **one** message (use `AskUserQuestion` where it exists; otherwise a numbered list in
plain text with the default in brackets). Skip anything the repo already answered and say what you
inferred:

0. **Org room or repository room** [org room when this folder is the organisation's `work-room`
   repository, or holds no code of its own]. An org room covers several repositories, cloned next to
   it; a repository room is one repository. For an org room, also ask for the **repositories**
   (offer the list from `gh repo list <org> --limit 100 --json name,url,description` when `gh` is
   available) and keep the ones the room should cover.
1. **Project or organisation name** and, in one line, what the room works on.
2. **The rule that matters most here**: the one mistake that would hurt this client most (for
   example "production is read-only", "never commit client data", "every change needs a ticket").
3. **Boundaries**: systems or environments that are off-limits or read-only.
4. **Git host and base branch** [GitHub, `main`]. Branch pattern [`feature/<KEY>-<slug>`].
5. **Push and PR autonomy**, one of:
   - *autonomous*: the room commits, pushes branches and opens PRs on its own;
   - *push, PR on request*: pushes branches, opens a PR only when asked;
   - *nothing without asking* [default for client repos]: commits locally; pushes and PRs only on
     the user's word, per branch.
6. **Merge policy** [the user merges].
7. **AI attribution** in commits and PRs: allowed, or banned [banned for client repos that have not
   settled an AI policy].
8. **Tracker** [GitHub Issues] and its key format [`#123`; Jira `PROJ-123`], and what the room may
   write there [comments only; creating tickets after approval].
9. **Pacing**: parallel (2 to 4 implementers at once) or sequential (one ticket end to end) [sequential].
10. **Who pays for the Claude accounts** [the organisation]. When the organisation pays, `{{ORG_ONLY}}`
    reads: "Claude here is paid for by <Org>: use it only for <Org>'s repositories. New work for <Org>,
    a proof of concept included, starts by creating its repository in <Org>." (enforced by the org guard
    in the organisation's managed settings, `docs/rollout.md` step 3). Otherwise: "No restriction."

## 3. Write the files

Claude Code asks before any write into `.claude/` (it protects its own configuration); that prompt
is expected, and the user approves it once per file.

From `templates/`, with every `{{PLACEHOLDER}}` filled from the answers (write a short sentence,
not a fragment; leave the HTML comments in place as guidance for the user):

| Template | Writes | Notes |
|---|---|---|
| `AGENTS.md` | `AGENTS.md` (project root) | The rules. `{{AUTH}}`: list the credentials the user named, or keep the template comment and say "none recorded yet". |
| `CLAUDE.md` | `CLAUDE.md` (project root) | One line, `@AGENTS.md`, so Claude Code loads the same rules. If a `CLAUDE.md` or `.claude/CLAUDE.md` already exists, propose moving its rules into `AGENTS.md` and leaving the import line. |
| `settings.json` | `.claude/settings.json` | See the policy notes below. Claude Code and the Agent SDK read it; other surfaces ignore it. |
| `register.md` | `.claude/state/register.md` | |
| `worklog.md` | `.claude/state/worklog.md` | |
| `repos.md` (org room only) | `.claude/repos.md` | `{{ROWS}}`: one `\| name \| clone URL \| purpose \|` row per repository |

**Policy notes for `settings.json`** (apply them to the `permissions` lists):

- *autonomous*: add `"Bash(git push*)"` and `"Bash(gh pr create*)"` to `allow` (force pushes stay
  denied by the `deny` list).
- *push, PR on request*: add `"Bash(git push*)"` to `allow` and `"Bash(gh pr create*)"` to `ask`.
- *nothing without asking*: add `"Bash(git push*)"` and `"Bash(gh pr create*)"` to `ask`.
- The `"agent": "work-room:orchestrator"` line makes the plugin's orchestrator the room's main agent
  in Claude Code. Keep it only when the `work-room` plugin is installed; otherwise remove it.
- GitLab or another host: replace the `gh …` rules with the host's CLI equivalents (`glab mr …`).
- **Org room**: add `"additionalDirectories": [".."]` under `permissions`, so the room reaches the
  repositories cloned next to it. Say plainly that this opens the whole parent folder to the room, so
  each organisation should have its own parent folder (`~/work/<org>/`). When the room repository
  hosts the organisation's plugin marketplace (`.claude-plugin/marketplace.json`), also register it
  and enable the plugins, so the room works before managed settings do:
  `"extraKnownMarketplaces": {"golding-work": {"source": {"source": "github", "repo":
  "golding-software/agent-work-kit"}}, "<org>": {"source": {"source": "github", "repo":
  "<Org>/work-room"}}}` and `"enabledPlugins": {"work-room@golding-work": true,
  "<org>-conventions@<org>": true}`. Then offer to run `/work-room:sync-repos` to clone them.

In an org room, the room is a repository the developers share: commit `AGENTS.md`, `CLAUDE.md`,
`settings.json` and `repos.md`; keep `.claude/state/` and `.claude/settings.local.json` out of version control.
Elsewhere, keep `.claude/state/` out of version control unless the user wants it shared: suggest adding it to
`.gitignore` (do not edit `.gitignore` without asking).

## 4. Report

List every file written (or proposed beside an existing one), the choices you inferred rather than
asked, and three next steps for the user: read `AGENTS.md` and tighten the top rule; add
credentials to the "Authentication" section as they come up; start a fresh session so the rules load.

## On other surfaces

- **Claude Code / Agent SDK**: the files take effect in the next session started in the project.
- **Claude API (Messages API skills) and Managed Agents**: there is no persistent project directory
  unless one is mounted. Write the files into the mounted repository if there is one, otherwise into
  the container's output directory, and tell the user to copy them into the project. `settings.json`
  only matters to Claude Code and the Agent SDK; on Managed Agents the equivalent controls are the
  agent's tool permission policies.
