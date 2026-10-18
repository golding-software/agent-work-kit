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
