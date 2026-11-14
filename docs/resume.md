# Resume a topic in a fresh session

Sessions get lost or grow large. A work room can carry a piece of work from one session to the next:
the register says where it stands, and a resume file holds the prompt for the next session.

## The header

Each block in `.claude/state/register.md` starts with a `RESUME:` header: the status, the next action,
what the work waits on, what is in flight (worktree, branch, PR, workers) and the last session. The
session rewrites it after every step. The history lines below it only grow.

## The resume file

When a session must stop with the work unfinished, it also writes `.claude/state/resume/<KEY>.md`: a
ready-to-paste prompt that says which block to read, what is done, the next action, what to verify
before trusting the register, and the open questions. The file is replaced at each hand-off and deleted
with the block when the work is done.

## Picking it up

In Claude Code, run `/work-room:resume-topic <KEY>`. Without a key the skill lists the blocks and asks
which one. It reads the header and the resume file, checks the PRs, branches and worktrees they name,
records the claim in the block's history, and reports before any work starts. On other surfaces, paste
the resume file, or follow the skill's steps by hand.

## Optional: the context-size check

The work-room plugin has a hook that checks the session's context size after each prompt and tool
call. It is off by default. To turn it on, add this to the room's `.claude/settings.json`:

```json
{ "env": { "WORK_ROOM_CONTEXT_GUARD": "on" } }
```

Each session gets one reminder when its context reaches the threshold: 300,000 tokens by default, or
95,000 for a Haiku model, whose price steps up above 100,000 tokens. Set `WORK_ROOM_CONTEXT_TOKENS` or
`WORK_ROOM_CONTEXT_TOKENS_HAIKU` in the same `env` block to change them. A missing or bad value falls back
to the default. The reminder is a note in the conversation; the session decides what to do with it.

## Out of scope

The kit does not start, stop or replace sessions. A session writes its own resume file when it stops.
