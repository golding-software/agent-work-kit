# Repositories this room covers

Cloned side by side in the clone root: by default the folder that holds this room, so the room and
the repositories are siblings. A developer can choose another place with the WORK_ROOM_CLONE_ROOT
environment variable (and add it to `additionalDirectories` in their `.claude/settings.local.json`).
Add a row in a PR when the organisation adds a repository. `/work-room:sync-repos` clones and checks
them.

clone-root: ..

| Repo | Clone URL | Purpose |
|---|---|---|
{{ROWS}}
