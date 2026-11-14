#!/usr/bin/env python3
"""Context check for a work room: one reminder per session to hand the topic off to a fresh session.

Off unless the room's .claude/settings.json sets `"env": {"WORK_ROOM_CONTEXT_GUARD": "on"}` (or 1 or true).
When it is on, it reads the session's context size from the transcript (the last assistant turn of the
main thread: input + cache-read + cache-creation tokens). At or above the threshold, once per session, it
adds a note to the conversation that tells the session to finish its step, rewrite its register header and
write a resume prompt. Thresholds: WORK_ROOM_CONTEXT_TOKENS (300000 for every model) and
WORK_ROOM_CONTEXT_TOKENS_HAIKU (95000 for a Haiku model, whose price steps up above 100K tokens).

Runs on UserPromptSubmit and PostToolUse. Standard library only. It never fails a session: any error
exits 0 with no output.
"""
import json, os, re, sys
from pathlib import Path

DEFAULT_TOKENS = 300000
DEFAULT_HAIKU_TOKENS = 95000
TAIL_BYTES = 2 * 1024 * 1024
ON = {"on", "1", "true"}
EVENTS = {"UserPromptSubmit", "PostToolUse"}
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
MESSAGE = ("CONTEXT CHECK: this session is at {k}K tokens of context ({model}; the hand-off mark is {m}K). "
           "Finish the step you are on and don't start another. Then rewrite the RESUME: header of your block "
           "in .claude/state/register.md, write a resume prompt to .claude/state/resume/<KEY>.md (what is done, "
           "the next action, what to verify first, open questions), and tell the user in one line that this work "
           "should continue in a fresh session with `/work-room:resume-topic <KEY>`.")


def threshold(env, name, default):
    try:
        value = int(env.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def last_usage(path: Path):
    """(tokens, model) of the newest main-thread assistant turn with usage in the transcript's last 2 MB, or None."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        data = f.read()
    for line in reversed(data.decode("utf-8", errors="replace").splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:      # the first line of a cut tail, or any other partial line
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant" or obj.get("isSidechain") is True:
            continue
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        tokens = sum(count(usage.get(k)) for k in USAGE_KEYS)
        if tokens > 0:
            return tokens, str(message.get("model") or "")
    return None


def marker_for(session_id: str):
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    safe = re.sub(r"[^A-Za-z0-9-]", "", session_id)
    return base / "work-room" / "context-guard" / safe if safe else None


def main(stdin, env):
    if (env.get("WORK_ROOM_CONTEXT_GUARD") or "").strip().lower() not in ON:
        return
    data = json.load(stdin)
    if not isinstance(data, dict) or data.get("hook_event_name") not in EVENTS:
        return
    marker = marker_for(str(data.get("session_id") or ""))
    transcript = data.get("transcript_path")
    if marker is None or not transcript:
        return
    got = last_usage(Path(os.path.expanduser(str(transcript))))
    if got is None:
        return
    tokens, model = got
    limit = threshold(env, "WORK_ROOM_CONTEXT_TOKENS", DEFAULT_TOKENS)
    if "haiku" in model.lower():
        limit = threshold(env, "WORK_ROOM_CONTEXT_TOKENS_HAIKU", DEFAULT_HAIKU_TOKENS)
    if tokens < limit:
        return
    try:                        # once per session: the marker is created first, and exclusively
        marker.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return
    msg = MESSAGE.format(k=tokens // 1000, m=limit // 1000, model=model or "unknown model")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": data["hook_event_name"], "additionalContext": msg}}))


if __name__ == "__main__":
    try:
        main(sys.stdin, os.environ)
    except Exception:
        pass
    sys.exit(0)
