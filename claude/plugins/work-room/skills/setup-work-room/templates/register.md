# Register: live state of this room's work

One block per piece of work, headed by its key. Each session edits only its own blocks (an `Edit`,
never a whole-file rewrite), re-reads the file before every edit, and removes a block only after the
work is appended to `worklog.md`. The `RESUME:` header is rewritten (an `Edit` of those lines) after
every step, history lines are only appended, and a block without a header can't be resumed with the
resume-topic skill. Format:

```markdown
## <KEY> — <short summary>
RESUME: (rewritten after every step; the history below only grows)
- status: investigating | implementing | pr-open | review-loop | blocked | verifying — <one line on where it stands>
- next: <the single next action>
- waiting on: <whom or what, or nothing>
- in flight: repo/worktree <absolute path>; branch <name> (pushed: yes/no); PR <number or none>; workers <agent> (running | returned, commit <sha>)
- last session: <session name>, <YYYY-MM-DD>

History:
- <YYYY-MM-DD> <one line per step, newest last>
```
