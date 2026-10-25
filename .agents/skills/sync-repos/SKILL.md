---
name: sync-repos
description: Lists, checks and clones the organisation's repositories for an org work room, from the room's .claude/repos.md - which repos exist, where they are cloned (next to the room by default), their branch, uncommitted changes and ahead/behind state - and clones the missing ones. Use when starting work in an org room, when a request names a repository that may not be cloned yet, or when asked which repos the room covers or what state they are in.
---

# Sync the room's repositories

An **org work room** is a folder (usually the organisation's `work-room` repository) whose
`.claude/repos.md` lists the organisation's repositories. They are cloned side by side in the
**clone root**: by default the folder that holds the room, so the room and the repos are siblings
(`~/work/acme/work-room`, `~/work/acme/api`, `~/work/acme/web`). A developer can put them elsewhere
with the `WORK_ROOM_CLONE_ROOT` environment variable; repos.md can set `clone-root:` for everyone.

The script is `scripts/repos.py`, relative to **this skill's directory** (the folder that holds
this SKILL.md). Run it from anywhere inside the room.

- **Where and what**: `python3 <skill dir>/scripts/repos.py where`, then `… status` (add `--fetch` to
  update ahead/behind from the remotes; it runs `git fetch`, nothing else).
- **Clone what is missing**: `… clone` (all) or `… clone api web` (named). It never touches a folder
  that already exists, and never pulls, resets or deletes.
- **A repo not in repos.md**: add a row (`| name | clone URL | purpose |`) in a PR to the room
  repository, rather than cloning it ad hoc, so every developer's room knows it.

The room reaches the clones because its `.claude/settings.json` adds the clone root as an
additional directory (`"additionalDirectories": [".."]` for the default layout). If a developer
moved the clone root, they add that path in their own `.claude/settings.local.json`.

Report the status as a short table, and say what you cloned. Changes inside a repository still
follow the room's rules: a branch and a worktree per ticket, never the repository's main checkout.
