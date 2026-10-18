# Competitive analysis (2026-10-18)

Evidence level: vendor documentation and READMEs read on 2026-10-18; nothing was run against the other tools. Rows marked UNVERIFIED were not read.

## work-room (room setup)

| What exists | What it covers | What it does not |
|---|---|---|
| Subagent frontmatter (`model`, `effort`, `maxTurns`, `autoCompactWindow`, `isolation: worktree`) | Per-agent model and limits, a worktree per run | Which rung to use, when to escalate |
| Subagent nesting (up to 3 layers) | Delegation inside one session | Coordination across sessions |
| Agent teams (experimental, interactive, env-gated) | Shared task list, mailbox, hooks, inside one team | Independent sessions, nested teams, unattended rooms |
| Agent view / `--bg` background sessions, Remote Control spawn modes | Many sessions, one place to watch them | A shared register or lock between them |
| Cross-session messaging (`ListAgents`, `SendMessage`) | Messages between sessions and machines | Locks, registers, work logs |
| Worktrees | File isolation per session | Anything about who is doing what |
| Managed settings (`extraKnownMarketplaces` + `enabledPlugins`) | Pushes a plugin to every machine in a Team/Enterprise org | The plugin's content |

**Verdict:** Anthropic's parallel-session features provide the mechanism (more sessions, worktrees, messaging). They do not provide the policy: the worker ladder with escalation, the sizing of work, the register, the deploy lock, the work log, `sync-repos`/`setup-work-room`, or the org guard. The room setup stays relevant, and it is more useful with parallel sessions than without, because parallel sessions are what make a register and a lock necessary. Where it overlaps (per-agent model and effort, plugin distribution) it should use the built-ins and say so, not reimplement them.

The open-source survey (15 projects, README level) found no project combining a model ladder, a shared register/lock and an org guard. That is "no match found", not "nobody has built it".

## pr-review (CI review)

| Product | Cost model | Approves? | Notable |
|---|---|---|---|
| Anthropic Code Review (Team/Enterprise) | tokens; docs say reviews average $15-25 | never approves or blocks | find/verify/rank/post stages, severity markers, depth levels, spend cap, auto-resolve |
| `claude-code-action` + code-review plugin | tokens | no | four parallel agents, confidence threshold 80/100, skips drafts |
| GitHub Copilot review | credits, ~$0.05-$5 per review | no | suggested fixes |
| CodeRabbit | $24-72/user/month | no | path instructions, learns rules from feedback |
| Greptile / Qodo / Bugbot / Graphite / Codex | seat or credit pricing (Bugbot ~$1-1.50 average) | UNVERIFIED | UNVERIFIED rule mechanics for Greptile, Bugbot, Graphite |

**Verdict:** the individual ideas are not new (a cheap first pass, confidence thresholds, never-approve paths). What none of the documented products does is the combination: a cheap model reviews, a stronger model must confirm before an approval is posted, the approval is bound to the reviewed head SHA, there is a ticket requirement and a per-PR dollar cap, and everything runs in the team's own CI with its own key. The nearest commercial product (Anthropic's) deliberately never approves.

**Cost evidence:** Haiku 5.5 lists at $0.10/$0.50 per MTok (prompts up to 100K tokens; $0.50/$2.50 above) against Sonnet 5.5 at $2/$10. Our own eval: Haiku found 39/40 planted bugs against Sonnet's 40/40 at about a tenth of the cost. Published third-party benchmarks are for Haiku 4.5, not 5.5; there is no independent PR-review evidence for Haiku 5.5. A cascade that has Sonnet confirm every approval is the hedge.

## Ideas adopted (or to adopt) from others

- Incremental review of only the new commits on a push; skip trivial pushes; `review:full` label to force a full pass (client-proven workflow).
- Effort and turn cap per event (`--effort`, `--max-turns`), `--exclude-dynamic-system-prompt-sections` for cache hits.
- A per-run cost line in the verdict comment.
- Severity labels including "pre-existing" (Anthropic, Codex); skip drafts/closed PRs (plugin); `@claude review` on-demand trigger.
- README caveat on prompt injection through PR content.

## Not claimed

No claim that this is faster or more accurate than any commercial product: only the cost structure and the approval gate are different, and the accuracy numbers come from our own small eval.
