# pr-review

PR review that checks the change against its ticket as well as the code, approving clean PRs.

**Nobody needs to install this plugin for CI.** The review runs as a shared GitHub Actions workflow
in this repository, [`.github/workflows/pr-review.yml`](../../.github/workflows/pr-review.yml); a
client repository calls it with a short caller file pinned to a version tag:

```yaml
jobs:
  pr-review:
    uses: golding-software/agent-work-kit/.github/workflows/pr-review.yml@v1
    with: {model: sonnet, auto-approve: true, jira-base-url: ""}
    secrets: {anthropic-api-key: "${{ secrets.ANTHROPIC_API_KEY }}"}
```

Every PR gets inline comments (at most 10, changed lines only) and one summary: verdict, the ticket's
requirements marked met / partly met / not met / not verifiable, out-of-scope changes, findings by
severity. Tickets come from Jira (`jira-base-url` set) or the GitHub issue the PR closes. A
repository's own `.github/pr-review/rubric.md` replaces the built-in rubric.

**Models: a cascade** (caller settings). `model` (Haiku) reviews every PR below the large tier and
posts the comments. Only when it would approve does `confirm-model` (Sonnet) review the PR again,
silently, and the approval needs both; if Sonnet disagrees, its summary is posted instead. A PR of at
least `large-min-lines` (400) or `large-min-files` (15) is reviewed by `large-model` (Sonnet) with a
read-only `context-reader` subagent on `reader-model` (Haiku) for bulk reading. `max-budget-usd` caps
each review's spend (default US$5).

**Cost controls** (caller settings). `effort` (default `medium`) and `max-turns` (default 30) bound each
review; `trivial-push-lines` (default 0 = off) skips re-reviewing a push of fewer changed lines than that
on an already-reviewed PR (a human re-approves; the label `review:full` forces a review). Each run's
cost is written to the run summary. Draft and bot PRs are skipped. Not yet implemented: reviewing only
the commits since the last review, and an `@claude review` comment trigger.

**Lessons from production use** (a client's review, 2026-10-18). (1) The first, small-model review does not load the repository's CLAUDE.md (`first-review-loads-claude-md`, off by default): with a ~60K-token CLAUDE.md, Haiku 5.5 hit "Autocompact is thrashing" and ended with no review; it reads CLAUDE.md on demand. (2) The run summary prices each stage from its token counts at list price, because the SDK's own cost figure for Haiku 5.5 was about 30x too high. (3) Approvals are posted by `github-actions[bot]` with the workflow token, which needs the repository setting "Allow GitHub Actions to create and approve pull requests"; if your branch rulesets only accept the Claude App's identity, post the verdict and approval from a small extra `claude-code-action` step instead (`claude-code-action` revokes its App token when each step ends), as the client's workflow does.

**Shadow mode** (`shadow: true`). To compare this review with another one on the same PRs (for example before replacing an existing review), run it as a shadow next to it: the full cascade (first review, second review) runs, but nothing is written to the PR: no comments, no inline threads, no state comment, no approval, no thread resolution, no failing check. The review goes to the run summary and to the job log (lines starting `SHADOW|`), the cost line as usual, and the last reviewed commit to an artifact (so pushes are still reviewed incrementally). It does not triage earlier threads, so it cannot touch another reviewer's threads.

**Jira with a service-account token.** An Atlassian service-account token is a Bearer token and the site URL (`https://<site>.atlassian.net`) answers it with 403. Set `jira-base-url` to the gateway `https://api.atlassian.com/ex/jira/<cloud id>` and leave `jira-email` unset: the ticket step then uses Bearer (tested against a real project, 2026-10-20).

**API credit.** The review runs Claude Code through `claude-code-action`. On a new Anthropic Console organisation the free promotional credit (for example the US$200 that comes with a Team plan) may be refused for it: the review step then fails after a fraction of a second with "Credit balance is too low" while the same key still works for a plain `claude -p` call from a terminal. Buy a small amount of purchased credit on the Console organisation (a few dollars lasts for hundreds of reviews), or use a Claude Code OAuth token (`claude-code-oauth-token`) from a plan that includes Claude Code. The workflow prints the API error line when the review step fails; for the full output set `show-full-output: true` for one debugging run.

**Prompt injection.** The diff, the PR text and the ticket are untrusted input to a model that can
comment and approve. The reviewer is told to treat them as data and the workflow decides the approval
from a structured verdict, not from the model's tool calls; but no prompt is a guarantee. Keep
`never-approve-paths` for CI, infrastructure and secrets-handling code, and require a human review on
repositories where an unreviewed merge is costly.

Why (two evaluation rounds, 2026-10-11, the second on pallets/click with multi-bug and cross-file PRs
up to ~245 lines): Haiku 5.5 never let a bad PR through and found the planted bugs in 39 of 40 runs
(Sonnet 5.5: 40 of 40), at about a tenth of the cost (US$0.006-0.009 per review against
US$0.071-0.086); it is stricter on clean PRs and rarely says plain "ready", so Sonnet confirming its
would-approve verdicts gives Sonnet-level approvals while paying for Sonnet only on PRs heading for
approval.

**Tickets** (`require-ticket`, on by default): every PR must reference one or more tickets: Jira
keys leading the title (`KAN-1, KAN-2: …`) or in the branch name, keys of the `jira-projects`
anywhere, or GitHub issues the PR links or closes. Without one, or when a ticket can't be read, the
check fails before any review runs (no cost) and the PR gets one comment saying what to add. A ticket
too thin to review against is a major finding, which blocks approval: tickets come first, with detail.

**Auto-approve** (on by default; `auto-approve: false` where a person must always approve): Claude returns `{verdict, blockers, majors}`; a plain workflow step
approves only a `ready` verdict with no blocker or major findings, on the exact commit reviewed, and
never for changes under `.github/` (input `never-approve-paths`). Claude itself has no approve
permission. Pair it with branch protection that dismisses stale approvals on new pushes.
**One summary comment per PR**: the reviewer returns its summary in the result's `report`; the workflow posts it as a single comment (marker
`<!-- pr-review:summary -->`) and edits that same comment on every push, with a footer naming the reviewed commit. The reviewer cannot run
`gh pr comment` any more; it posts only inline comments. Older per-push comments stay as history.
**Middle gate** (`approve-max-findings: N`, default -1 = off): approve when the verdict is `ready` or `ready_after_minor_fixes`, there is no blocker or major
finding, and the findings in all (minors and questions included) are at most N; the confirming review must meet the same bound. When set it
replaces `approve-on-minor` (0 = only a review with no findings, like the default).
**Open threads block approval** (`approve-requires-no-open-threads`, default true): the bot never approves while one of its own earlier review threads
is still open: the open ones minus the ones the reviewer says the new code fixed must be zero when the decision is taken, and after the resolving
step no thread of the bot's may be open (read live, so a failed resolve counts). Independent of the finding thresholds above.
The workflow installs Claude Code itself with six attempts and a jittered backoff before it calls the action (the installer rate-limits
bursts of concurrent runs with HTTP 429); if that fails too, the action tries its own install as before.
The review itself is always complete; when a PR changes a path from `never-approve-paths`, one comment on the PR (updated on every push) says
"Human review needed because of changes in these folders: …", naming the folders, so the person who must review them knows.

The plugin's two skills are for the person setting it up, and for on-demand reviews:

- **`/pr-review:setup-pr-review`** writes the caller workflow (and an optional tailored rubric) and
  lists the repository settings to apply: Claude GitHub App, secrets, "allow GitHub Actions to approve
  pull requests", branch protection.
- **`/pr-review:review-pr`** runs the same review in a session on a PR or local branch, and posts only
  when asked.

Hardening: the PR title, body and branch reach a bash step through environment variables only; only
the validated ticket key reaches the prompt, and the ticket text is passed as a file marked as data.
The job always reports a status (drafts, bots and workflow edits pass with a notice), so it can be a
required check.
