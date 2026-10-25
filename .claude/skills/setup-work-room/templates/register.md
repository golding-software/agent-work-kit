# Register: live state of this room's work

One block per piece of work, headed by its key. Each session edits only its own blocks (an `Edit`,
never a whole-file rewrite), re-reads the file before every edit, and removes a block only after the
work is appended to `worklog.md`. Format:

```markdown
## <KEY> — <short summary>
- status: investigating | implementing | pr-open | review-loop | blocked | verifying
- repo / worktree: <absolute path>
- branch: <name> (pushed: yes/no)
- PR: <number or none>
- workers: <agent> (running | returned, commit <sha>)
- blocked on: <the question for the user, or nothing>
- next: <the single next action>
```
