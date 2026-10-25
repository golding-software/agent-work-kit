---
name: acme-conventions
description: How work is done at Acme - where tickets and specs live, how to read a ticket's scope and acceptance criteria, the environments and which are off-limits, and Acme's commit, branch and PR conventions. Use at the start of any ticket, PR or investigation in an Acme repository, and whenever a ticket key, wiki page or environment name comes up.
---

# Working at Acme

<!-- Fill this in for the client. Keep it to what is true for EVERY Acme repository; a single
repository's rules belong in its own AGENTS.md. -->

## Tickets and scope

- Tracker: <GitHub issues in each repo | Jira project KEY at https://acme.atlassian.net>.
- A ticket's scope is its description plus <the "Acceptance criteria" field | the checklist>. Read it
  before starting; quote the criteria in the PR description.
- <Jira only> Read tickets with the Atlassian MCP server this plugin configures (`.mcp.json`); never
  paste a token into a command.

## Specs and decisions

- <Confluence space KEY | docs/ in each repo | none>.

## Environments

| Environment | Use |
|---|---|
| <dev> | free to use for testing |
| <staging> | read and test; deploys only through CI |
| <production> | **read-only**; changes only through CI/CD |

## Conventions

- Branches: <feature/KEY-123-slug>. Commits: <KEY-123: imperative summary>. PRs: <title format,
  template>.
- AI attribution: <banned | allowed>.
