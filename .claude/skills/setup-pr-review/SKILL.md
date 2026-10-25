---
name: setup-pr-review
description: Sets up automated pull-request review for a GitHub repository using the shared Golding Software PR review workflow - every PR is reviewed against its ticket (Jira or the GitHub issue it closes) and a rubric, gets inline comments and one summary, and is approved automatically when the verdict is ready. Writes a short caller workflow and an optional rubric, and lists the repository settings to apply. Use when someone wants Claude to review PRs in CI, auto-approve clean PRs, or check PRs against their tickets.
---

# Set up automated PR review

The review itself is a **shared workflow** in github.com/golding-software/agent-work-kit
(`.github/workflows/pr-review.yml`). A repository calls it with a short caller file pinned to a
version tag, so improvements arrive by moving the tag; nothing is copied. Paths below
(`templates/…`) are relative to **this skill's directory** (the folder that holds this SKILL.md).
Files are written into the **repository root**.

## 1. Look before writing

Check for `.github/workflows/pr-review.yml`, `.github/pr-review/rubric.md`, and any other workflow
using `anthropics/claude-code-action`. **Never overwrite**: write `<name>.proposed` beside an
existing file and show the difference.

## 2. Ask (one message; `AskUserQuestion` where it exists, otherwise a numbered list)

1. **Claude credential for CI**: the organisation's Anthropic API key (secret `ANTHROPIC_API_KEY`,
   billed to its Console account) [default], or a subscription token (`CLAUDE_CODE_OAUTH_TOKEN`).
2. **Ticket context**: GitHub issues (the PR body says `Closes #12`) [default], or Jira (the site
   URL; an account email and API token become secrets).
3. **Auto-approve** when the verdict is "ready" with no blocker or major findings [yes; choose no
   for a repository where a person must always approve, such as a public one].
4. **Require a ticket** on every PR [yes]: a PR with no Jira key (title or branch) and no linked or
   closing GitHub issue, or whose ticket cannot be read, fails the check without a review, and a
   ticket without enough detail to review against is a major finding. Jira users: the project keys
   (`jira-projects`, e.g. `KAN`) so keys anywhere in the title, body or branch count.
5. **Models** [keep the defaults: Haiku reviews every PR, Sonnet confirms before any approval, PRs of
   400+ lines or 15+ files go to Sonnet with a Haiku context-reader], and **approve-on-minor** [no]. **Version tag** [the latest release of golding-software/agent-work-kit].
6. **A tailored rubric**: start from the built-in one and adapt it to this repo [no].

## 3. Write the files

- `templates/caller.yml` → `.github/workflows/pr-review.yml`, replacing `{{VERSION}}`, `{{MODEL}}`,
  `{{AUTO_APPROVE}}` and `{{REQUIRE_TICKET}}` (`true`/`false`), `{{JIRA_BASE_URL}}`; uncomment the tier lines the user
  changed (the URL, or `""` for GitHub issues
  only) and `{{AUTH_SECRET}}` with `anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}` or
  `claude-code-oauth-token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`. Drop the two `jira-*` secret
  lines when Jira is not used.
- Only if a tailored rubric was asked for: `templates/rubric.md` → `.github/pr-review/rubric.md`,
  adapted to the repo's language, test framework and the mistakes its team cares about; keep its
  section headings and its rules section.

## 4. Settings only the repository admin can apply

Credentials belong to the organisation: never ask for a key or token value, never set a secret
yourself. Give these as commands to run:

1. Install the Claude GitHub App on the repository: https://github.com/apps/claude (or
   `/install-github-app` in Claude Code).
2. Secrets: `gh secret set ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`); for Jira also
   `gh secret set JIRA_EMAIL` and `gh secret set JIRA_API_TOKEN`.
3. For auto-approve: Settings → Actions → General → **Allow GitHub Actions to create and approve
   pull requests** (`gh api -X PUT repos/<owner>/<repo>/actions/permissions/workflow -F
   can_approve_pull_request_reviews=true`).
4. Branch protection (or a ruleset) on the default branch: require a pull request; require the
   status check **pr-review / review**; **dismiss stale approvals when new commits are pushed**; and
   decide whether a human approval is also required (the automated approval counts as one).
5. Merge the caller workflow first: a PR that edits it skips its own review, because the Claude App
   only runs a workflow that matches the default branch.

## How approval stays safe

- Claude cannot approve. It returns a structured result `{verdict, blockers, majors}`; a plain
  workflow step approves only when the verdict is `ready` with zero blockers and majors, the PR
  touches nothing under the never-approve paths (default `.github/`), and the head commit is still
  the one reviewed.
- The PR title, body and branch reach a bash step through environment variables only; just the
  validated ticket key reaches the prompt, and the ticket text is a file the prompt labels as data.
- A Jira or GitHub failure degrades to a code-only review with a visible warning.

## On other surfaces

This skill only writes files, so it runs wherever skills run; the review runs on GitHub Actions. For
an on-demand review in a session, use `review-pr`.
