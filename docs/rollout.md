# Rolling the work room and PR review out to an organisation

A runbook for whoever sets up an organisation (a consultant, a platform lead). Steps marked
**(org)** need someone at the organisation; the rest you can do with admin access to its GitHub.

## What the organisation needs

| Account | Used for | Notes |
|---|---|---|
| **Claude Team or Enterprise** organisation, with Claude Code seats | the developers' sessions; managed settings that enforce the room, cap usage and set privacy options | Team is the minimum for central enforcement (Organization settings → Claude Code → Managed settings needs an **Owner**). Individual Pro/Max accounts cannot be managed. |
| **Anthropic Console** (API) organisation | the CI PR review | One API key for GitHub Actions, billed to the organisation; set a monthly spend limit. |
| **GitHub** organisation admin access | the `work-room` repo, the review workflow, branch protection | |

## 1. Organisation settings **(org)**

Most of these are already the default on commercial plans; confirm each, and record the answers
for the organisation.

| Setting | Where | Recommended |
|---|---|---|
| Training on the organisation's data | Commercial terms | Off by default on Team, Enterprise and API: Anthropic does not train on Claude Code prompts or code. Keep the **Development Partner Program** opt-in **off** (Console, organisation settings). |
| Data retention | Plan | Standard 30 days on Team, Enterprise and API. **Zero data retention** exists only for Enterprise, enabled per organisation by the Anthropic account team after an eligibility check: ask for it if the organisation's policy requires it. |
| Product feedback | Admin console, if offered | Off. Otherwise the managed `env` below. |
| Login pinned to the organisation | Managed settings | `forceLoginMethod: "claudeai"` and `forceLoginOrgUUID: "<org uuid>"`, so developers can't run Claude Code on the organisation's code from a personal account (on whose plan training may be on). |
| SSO, domain capture, SCIM | Admin console (Enterprise) | On where available; offboarding then removes access. |
| Seats and extra usage | Admin console | Seats only for people who use Claude Code; decide whether extra usage beyond the plan is allowed and its cap. |
| Analytics | Admin console → Claude Code | Review monthly: who uses what, cost per developer. |

Privacy and safety settings to include in the managed settings (step 3):

```json
{
  "env": {
    "DISABLE_FEEDBACK_COMMAND": "1",
    "CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY": "1",
    "DISABLE_ERROR_REPORTING": "1"
  },
  "cleanupPeriodDays": 30,
  "permissions": {
    "deny": ["Read(**/.env)", "Read(**/.env.*)", "Read(~/.ssh/**)", "Read(~/.aws/credentials)", "Read(~/.config/gcloud/**)"]
  }
}
```

- `DISABLE_FEEDBACK_COMMAND` stops `/feedback`, `/bug` and `/share` from sending transcripts (code
  included) to Anthropic, where they are kept for 5 years. `CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY`
  removes the survey whose follow-up offers to upload a session transcript.
- Leave `DISABLE_TELEMETRY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` **off** unless the
  organisation requires them: the metrics contain no code, prompts or file paths, and both settings
  also disable feature flags, which turns off Remote Control.
- `cleanupPeriodDays` is how long transcripts stay on each developer's disk (default 30).
- Repository `.env` files and personal credentials stay unreadable to every session.

## 2. The organisation's work room

1. Create a **private** `<Org>/work-room` repository from
   [`templates/org-work-room`](../templates/org-work-room): rename `acme`, fill in the conventions
   skill (tracker, specs, environments, branch/commit/PR conventions, AI-attribution policy), and for
   Jira/Confluence rename `plugin/mcp.example.json` to `plugin/.mcp.json`.
2. In a clone (`~/work/<org>/work-room`), run `/work-room:setup-work-room` and choose **org room**:
   it writes the room's rules, permissions (including access to the sibling repositories) and
   `.claude/repos.md`, the organisation's repository list. Commit.
3. `claude plugin validate --strict .` and `… plugin`, then push.

Each developer then clones `<Org>/work-room` into `~/work/<org>/`, opens `claude` there, accepts the
trust prompt, and runs `/work-room:sync-repos`: the repositories are cloned next to the room.

## 3. Keep the organisation's accounts on its own work **(org)**

When the organisation pays for the seats, the room is for the organisation's repositories only. The
**org guard** enforces it from the organisation's managed settings, so a developer's own settings
can't switch it off:

- A session opened anywhere that is not a clone of one of the organisation's repositories gets every
  prompt refused, with the reason and the way forward: new work for the organisation, a proof of
  concept included, starts by creating its repository in the organisation
  (`gh repo create <Org>/<name> --private --clone`), then opening Claude there.
- File tools (read, edit, write, search) aimed outside the organisation's repositories are denied,
  and so is a shell command run from, moving into (`cd`, `git -C`) or naming a home-folder path
  outside them. Claude Code's own folders and system paths stay usable.
- "The organisation's repositories": a git working tree (worktrees included) whose `origin` is the
  organisation on its git host and which the host confirms exists (`git ls-remote`, cached for a day),
  so pointing a personal folder's remote at the organisation is not enough.

Generate the block with the organisation's name(s) and merge its `hooks` into the policy below:

```sh
python3 scripts/managed-guard.py --org <Org> [--org <OtherOrg>] [--host gitlab.example.com]
```

Limits to tell the organisation: it needs `python3` on developer machines (a hook that cannot start
does not block, so check it on one machine first: a prompt in a non-org folder must be refused); it is
client-side, so a determined developer can work around it, and review of Claude Code analytics
remains the backstop; it covers Claude Code, not claude.ai chat.

## 4. Enforce it **(org)**

An Owner pastes the policy into Organization settings → Claude Code → Managed settings: the
privacy block (step 1), the org guard's `hooks` (step 3), plus

```json
{
  "extraKnownMarketplaces": {
    "golding-work": { "source": { "source": "github", "repo": "golding-software/agent-work-kit" }, "autoUpdate": true },
    "<org>":        { "source": { "source": "github", "repo": "<Org>/work-room" }, "autoUpdate": true }
  },
  "enabledPlugins": {
    "<org>-conventions@<org>": true,
    "work-room@golding-work": true
  },
  "forceLoginMethod": "claudeai",
  "forceLoginOrgUUID": "<org uuid>",
  "availableModels": ["opus", "sonnet", "haiku"],
  "maxEffortLevel": "high",
  "workflowSizeGuideline": "small"
}
```

- `enabledPlugins: true` installs both plugins for everyone at their next session; users cannot
  disable them.
- **Usage**: `availableModels` limits the models anyone can pick, for the main session and every
  subagent; `maxEffortLevel` caps effort; `"disableWorkflows": true` turns off dynamic workflows
  and ultracode, the biggest single source of runaway usage; `workflowSizeGuideline` is the softer
  alternative.
- **Optional lockdown**: `"strictKnownMarketplaces"` (an allowlist of marketplace sources) plus
  `"disableSideloadFlags": true`.

Check on one developer machine: `/status` lists "Enterprise managed settings"; `/plugin` shows both
plugins installed by policy.

## 5. Each repository

Run `/work-room:setup-work-room` (repository room) in a repository when sessions will also be opened
inside it, and merge the files it writes. Sessions opened in the org room don't need this.

## 6. Automated PR review

1. **(org)** In the Console, create an API key for CI with a spend limit.
2. Install the Claude GitHub App on the repositories: https://github.com/apps/claude.
3. Secrets: `gh secret set ANTHROPIC_API_KEY --org <Org> --repos <repo1>,<repo2>` (or per repo). Jira
   organisations also `JIRA_EMAIL` and `JIRA_API_TOKEN` (a service account with read-only access).
4. In each repository, run `/pr-review:setup-pr-review` (or copy
   [`caller.yml`](../skills/setup-pr-review/templates/caller.yml) to
   `.github/workflows/pr-review.yml`). Choose per repository:
   - `auto-approve`: `true` in most repositories; `false` where a person must always approve (a public
     repository, infrastructure);
   - `require-ticket`: `true` in most repositories, so tickets come first, with detail; Jira
     organisations also set `jira-projects`;
   - the cost tiers and `max-budget-usd` (default 5).
   Merge it before anything else: a PR that edits it skips its own review.
5. With auto-approve: `gh api -X PUT repos/<Org>/<repo>/actions/permissions/workflow -F
   can_approve_pull_request_reviews=true` (the organisation-level setting must allow it too).
6. Branch protection as a ruleset on the default branch:

   ```sh
   gh api -X POST repos/<Org>/<repo>/rulesets --input - <<'EOF'
   {
     "name": "main protection", "target": "branch", "enforcement": "active",
     "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
     "rules": [
       { "type": "deletion" }, { "type": "non_fast_forward" },
       { "type": "pull_request", "parameters": {
           "required_approving_review_count": 1, "dismiss_stale_reviews_on_push": true,
           "require_code_owner_review": false, "require_last_push_approval": false,
           "required_review_thread_resolution": false } },
       { "type": "required_status_checks", "parameters": {
           "strict_required_status_checks_policy": false,
           "required_status_checks": [ { "context": "pr-review / review" } ] } }
     ]
   }
   EOF
   ```

   With one required approval, the review's automatic approval is enough for a clean PR. Where
   `auto-approve` is `false`, the one approval has to come from a person.
7. **Pilot**: open a small PR that references a real ticket. Expect inline comments, one summary with
   the ticket-scope table, and an approval only if the verdict is `ready`. Push a commit afterwards:
   the approval is dismissed and a new review runs. Open one PR without a ticket: the check fails with
   a comment explaining what to add.

## 7. After rollout

- The generic room updates by itself (auto-update on the `golding-work` marketplace). Pin a version
  instead with `"version": "~0.1"` on the conventions plugin's dependency.
- The review updates when a repository's caller moves to a newer tag.
- Review usage monthly: Claude Code analytics in the admin console, and the Console's usage page for
  the CI key.
