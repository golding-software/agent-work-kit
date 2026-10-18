# {{PROJECT}}: work room rules

These rules bind every session in this room and every worker it starts, whichever coding agent runs
it: Codex reads this file directly, and Claude Code through the one-line `CLAUDE.md` beside it. They
are yours to edit: the room gets better each time a mistake becomes a line here.

## {{TOP_RULE_TITLE}}: the rule that matters most here

{{TOP_RULE}}

<!-- Keep the most important rule FIRST: a rule buried mid-document loses to default behaviour.
State it as a finishing step where you can ("before reporting the change as finished, re-read your
diff and check X"), and give the reason: a rule with a "why" survives paraphrase. If a rule keeps
being ignored however well it is written, enforce it with a hook instead of rewording it. -->

## Boundaries

{{BOUNDARIES}}

- **Organisation work only.** {{ORG_ONLY}}
- **Credentials are the user's.** Never print, copy or commit a secret value; refer to variables by
  name. Anything that needs a new credential, a login or a security setting: stop and ask.

## Authentication

<!-- For each credential this project needs, record: the exact command, what it authenticates as,
and which failure looks like which (expired, wrong account and locked agent all read as "auth
failed"). Say what needs the user and what does not, so a session never loops on something it
cannot fix. -->

{{AUTH}}

## Git and pull requests

- **Hosting**: {{GIT_HOST}}. Base branch: `{{BASE_BRANCH}}`. Branch names: `{{BRANCH_PATTERN}}`.
- **Push and PR autonomy**: {{PUSH_POLICY}}
- **Merging**: {{MERGE_POLICY}}
- **AI attribution**: {{ATTRIBUTION}}
- **Commit messages**: {{COMMIT_STYLE}} If a repo ships its own commit or PR skill, or a
  commit-message hook, use it; it wins over this line for that repo.
- **Never** `git push --force` or `-f` (only `--force-with-lease`, and only with the user's word),
  `git reset --hard`, `git clean`, `git stash drop`/`clear`, a bare `git stash pop`, or
  `git checkout -- .`/`git restore` over changes you did not make. Other sessions keep uncommitted
  work and stashes here; nothing deleted is recoverable.
- **Stage explicitly** (`git add <path>`), never `git add -A`, `git add .` or `git commit -a`.

## Always work in a worktree; worktrees go when the PR is raised

Every change happens on a branch in its own worktree, never in the main checkout, which another
session may be using. Before creating one, check what already exists:
`git branch -a | grep -i <KEY>`, `git worktree list`; adopt an existing branch rather than
re-creating it. **The moment the PR is raised, remove the worktree** (`git worktree remove <path>`,
then `git worktree prune`; never `rm -rf`). The branch stays. Review changes: re-create the worktree
from the branch, push, remove it again. A worktree that refuses to go still holds changes: stop and
report the files, never `--force`.

## When a PR is merged: verify, then clean up

1. **Verify the merge**: `gh pr view <N> --json state,mergedAt` (or your host's equivalent) must show
   it merged. Deleting the head branch of a PR that is *not* merged closes the PR. If you cannot
   verify, delete nothing and say what blocked you.
2. Remove the worktree if it still exists (never `--force` on a dirty tree).
3. Delete the local branch (`git branch -D`, safe only after step 1).
4. Append the item to `.claude/state/worklog.md`, then remove its register block.

## Tickets

- **Tracker**: {{TRACKER}}. Keys look like `{{TICKET_KEY}}`.
- **What the room may write there**: {{TRACKER_WRITES}}

## Claim before you start: several sessions, one register

Before implementation, a PR or an incident response on a ticket, in this order:

1. **The register**: `grep -n "<KEY>" .claude/state/register.md`.
2. **An existing PR**: `gh pr list --state all --search "<KEY>"` in the repo.
3. **The tracker's assignee**, where you can read it.

If any shows another session on it, stop and say so in one line. If all are clear, **write your
register block first** (`status: investigating`), then start. The block *is* the claim.

## Out-of-scope discoveries: fix small, ticket big

- **Small** (minutes, low risk, the area you are already in): fix it in the current change and
  mention it in the PR description.
- **Too big to absorb**: propose a ticket (a title and a description sharp enough to act on without
  this conversation) and create it only after the user approves.
- Never drop the finding silently.

## Waiting on the user

Ask **one** question with `AskUserQuestion`, the options being the decision, rather than a question
in chat text: it is what reaches someone who is away from the session. One question per wait; none
for routine progress.

## Pacing

{{PACING}}

## Things that have cost real time here

<!-- The highest-value section of this file. Each entry is a mistake already paid for once: what
happened, the rule that prevents it, and why. Add one every time a session wastes an hour. -->

- (none yet)
