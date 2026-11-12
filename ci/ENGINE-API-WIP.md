# WIP: `engine: api` build plan (delete before the PR is raised)

Base: v1.0.2 (b1fc17f). Steps in ci/pr-review.yml.in today (line numbers at b1fc17f): gate 160, threads 313, ticket 340,
Install Claude Code 418, Install Bun 442, Review 494, Explain/Recover 567/598, reviewed 613, summary 629, decide 663,
confirm 708, cost 754, resprep/resolve 784/806, final 827, approve 902/924, record 974, shadow 989.

## Plan
- New source `ci/api_review.py` (stdlib + pinned `anthropic`), inlined into the generated workflow by build.py like fetch-ticket.sh.
  Subcommands: `review` (first/large pass) and `confirm`. Writes the same result JSON the claude steps produce
  (`verdict, blockers, majors, findings, resolved[], report` + `comments[]`) and a transcript-like usage file for the cost step.
- Tools for the model (strict schemas, tool_choice auto): read_file(path, start_line, end_line), grep(pattern, path_glob),
  list_dir(path). Confined to the checkout: realpath under GITHUB_WORKSPACE, no symlink escape, size caps (lines/bytes per call),
  .git excluded. No shell, no network, no writes.
- Final answer via `output_config.format` json_schema (works together with tools). Models: claude-haiku-5-5 / claude-sonnet-5-5
  (aliases haiku/sonnet mapped), adaptive thinking (default), effort from the existing inputs (medium).
- Caching: system = rubric + instructions (stable); first user message = ticket + PR meta + diff, `cache_control` on it;
  the tool loop appends after. Confirm = other model -> its own cache.
- Budget: max-turns = loop iterations; max-budget-usd checked from `usage` after every call; Haiku >100K-token prompt price
  ($0.50/$2.50) accounted; tool output capped so prompts stay small.
- Engine branch in the workflow: `engine: api` skips Install Claude Code / Bun / the claude-code-action steps and runs
  setup-python + `pip install anthropic==<pin>` (hash-pinned) + the script. Same step ids/outputs downstream
  (`steps.reviewed.outputs.result/ok`, confirm structured output) so decide/final/approve are unchanged.
- Inline comments: the workflow (not the model) posts them: changed lines only (validated against the diff), at most 10,
  as one review (event COMMENT) with the workflow token -> author github-actions[bot] (matched by the thread filter).
- Thread resolution without the Claude App: try resolveReviewThread with the workflow token; if GitHub refuses
  ("Resource not accessible by integration"), reply on the thread with a marker `<!-- pr-review:fixed sha=<head> -->`
  and treat a thread whose LAST comment is the bot's marker as settled in both thread queries (threads step + final live
  check). Verify in the trial which path GitHub takes.
- Cost line: same `review cost: $X (1-review:$a/Nt 2-confirm:$b/Mt)`.
- Shadow: unchanged input; with engine api it posts nothing.
- Tests: tests for api_review.py with a fake client (path confinement, comment/diff validation, cost maths, schema parse,
  budget stop) in check.yml; build.py --check.
- Docs: pr-review README (engine section, secret, permissions), caller template, setup skill.

## Trial (HG 2026-11-12)
- Repos: golding-software/all-bubbles, attn, goldingsoftware.com.au, agent-trading. Real reviewer (not shadow), auto-approve on,
  approve-with-open-minor-threads on, effort medium both passes, fallbacks off. Secret: repo-level ANTHROPIC_API_KEY (GS API org).
- Never point the claude engine at the GS key (Claude Code is not covered by the promotional credit).
- Credit check (confirmation only): first api-engine run -> HG sees the promotional credit move, not the purchased balance.
