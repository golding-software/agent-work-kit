# work-room

A Claude Code room for one client or project.

- **`/work-room:setup-work-room`**: a short interview, then the room's files: `AGENTS.md`
  (the rules, with the one that matters most first), `.claude/settings.json` (permissions matching
  your push and PR policy), and `.claude/state/register.md` + `worklog.md`.
- **`work-room:orchestrator`** (the room's main agent): sizes each request as routine, medium or
  epic and runs the lightest loop that fits; claims work in the register before starting, so
  several sessions can work one project; keeps implementer stints short.
- **Worker ladder**: `implementer` (one ticket, end to end), `worker-haiku`, `worker-sonnet`,
  `worker-opus`. The rule: the cheapest rung whose result is cheap to check, never a rung above the
  orchestrator's own model, and escalate one rung on a failed review with the failed attempt attached.

Other Claude surfaces: [docs/surfaces.md](../../../docs/surfaces.md).

## First run: restart once

A plugin that is enabled by the project's or the organisation's settings installs in the background during the first session on a machine, so that first session may start without it (for example as the default agent, not `work-room:orchestrator`). Exit (`/exit`) and run `claude` again in the same folder: the second session has the plugin. This happens once per machine.

