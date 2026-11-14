---
name: resume-topic
description: Picks up a piece of work in a fresh session from its register block's RESUME: header and resume file, in a work room. Use when the user says resume, pick up or continue a topic's KEY, or when a session starts from a resume prompt that an earlier session wrote at its hand-off.
---

# Resume a topic in a fresh session

A **topic** is one block of the room's `.claude/state/register.md`, headed `## KEY — summary`. Its
`RESUME:` header says where the work stands, what comes next and what it waits on. If the last
session stopped with the work unfinished, it also left `.claude/state/resume/KEY.md`: a ready-to-paste
prompt. This skill reads both, checks them against the real repositories, and records that this
session took the topic over.

The script is `scripts/topic.py`, relative to **this skill's directory** (the folder that holds this
SKILL.md). Run it from anywhere inside the room.

1. **Which topic.** If no KEY was given, run `python3 <skill dir>/scripts/topic.py list`, then ask
   which topic with `AskUserQuestion` (one option per block), or with a numbered list where that tool
   does not exist. A block shown as `-` has no header and cannot be resumed.
2. **Read it.** Run `python3 <skill dir>/scripts/topic.py show KEY`. If it exits 3 (no such block) or
   4 (no `RESUME:` header), relay its message and stop. Do not rebuild the state from the history, and
   do not write a header for another session's block.
3. **Verify before trusting the header.** Check every item the `verify:` list names:
   - each PR: `gh pr view N --json state,mergedAt,headRefName,reviewDecision` (or the host's equivalent);
   - each branch: `git branch --list <name>` and `git ls-remote --heads origin <name>`;
   - each worktree: `git worktree list`.
   - A worker the header marks *running* belonged to the old session and is gone. Treat its work as
     not returned, unless a commit shows it.
   - List each mismatch between the header and what you found.
4. **Claim the topic.** Re-read the block, then `Edit` only its `- last session:` line to this
   session's name and today's date. Then run `python3 <skill dir>/scripts/topic.py mark KEY --session NAME`,
   which appends one dated history line to the block and touches nothing else.
5. **Report** in a few lines: the status, what you verified and what did not match, and the next
   action. Ask what to take next: the header's next action, or something else. Start no work before
   the answer.

## On other surfaces

The script needs a filesystem with the room in it. Where there is none, read `.claude/state/register.md`
and `.claude/state/resume/KEY.md` from the mounted repository by hand, and do the same checks and the
same claim by hand, with the same edit rules.
