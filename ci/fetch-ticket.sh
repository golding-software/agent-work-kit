#!/usr/bin/env bash
# fetch-ticket.sh: find the PR's tickets (Jira keys and/or GitHub issues) and write them to a file
# the review reads as DATA. Part of the shared pr-review workflow (.github/workflows/pr-review.yml in
# github.com/golding-software/agent-work-kit), inlined into it by scripts/build.py.
#
# Inputs (environment; the PR title, body and branch are author-controlled, so they only ever
# travel through env vars and are never interpolated into a command or into Claude's prompt):
#   PR_TITLE, PR_BODY, PR_HEAD_REF, PR_NUMBER, GITHUB_REPOSITORY, OUT (file to write),
#   TICKET_PATTERN (Jira key regex, default [A-Z][A-Z0-9]+-[0-9]+), JIRA_PROJECTS (optional,
#   comma-separated project keys: keys of these projects are also found anywhere in the title, body
#   or branch), JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN (optional), GH_TOKEN, GITHUB_OUTPUT.
# Outputs (GITHUB_OUTPUT): keys=<comma list>, count=<n found>, fetched=<n read>,
#   status=ok|none|not-found|fetch-failed|jira-not-configured, detail=<one line for humans>
set -uo pipefail
OUT="${OUT:-${RUNNER_TEMP:-/tmp}/ticket.md}"
PATTERN="${TICKET_PATTERN:-[A-Z][A-Z0-9]+-[0-9]+}"
MAX=5
out() { echo "$1=$2" >> "${GITHUB_OUTPUT:-/dev/null}"; }
: > "$OUT"

# --- 1. Jira keys ------------------------------------------------------------------------------
jira=()
add_jira() { local k; for k in "$@"; do [[ " ${jira[*]-} " == *" $k "* ]] || jira+=("$k"); done; }
# Keys leading the title: "PROJ-1: ...", "PROJ-1, PROJ-2: ...", "[PROJ-1][PROJ-2] ...". Not keys
# anywhere in the title: "UTF-8" looks like a key too.
lead="${PR_TITLE:-}"
while [[ "$lead" =~ ^[[:space:]]*[\[\(]?($PATTERN)[\]\)]?[[:space:],/:]*(.*)$ ]]; do
  add_jira "${BASH_REMATCH[1]}"; lead="${BASH_REMATCH[${#BASH_REMATCH[@]}-1]}"
  [ ${#jira[@]} -ge $MAX ] && break
done
# A key in the branch name: "feature/PROJ-123-slug".
if [[ "${PR_HEAD_REF:-}" =~ (^|/)($PATTERN)([-_/]|$) ]]; then add_jira "${BASH_REMATCH[2]}"; fi
# With known project keys, any key of those projects anywhere in the title, body or branch.
if [ -n "${JIRA_PROJECTS:-}" ]; then
  projects="$(echo "$JIRA_PROJECTS" | tr -d ' ' | tr ',' '|')"
  while read -r k; do [ -n "$k" ] && add_jira "$k"; done < <(
    printf '%s\n%s\n%s\n' "${PR_TITLE:-}" "${PR_BODY:-}" "${PR_HEAD_REF:-}" | grep -oE "\b($projects)-[0-9]+\b" | head -n $MAX)
fi

# --- 2. GitHub issues the PR closes ------------------------------------------------------------
issues=()
if [ -n "${PR_NUMBER:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  while read -r n; do [ -n "$n" ] && issues+=("$n"); done < <(
    gh pr view "$PR_NUMBER" --repo "$GITHUB_REPOSITORY" --json closingIssuesReferences \
      --jq '.closingIssuesReferences[].number' 2>/dev/null | head -n $MAX)
fi
if [ ${#issues[@]} -eq 0 ]; then   # fallback: closing keywords in the body
  while read -r n; do [ -n "$n" ] && issues+=("$n"); done < <(
    printf '%s\n' "${PR_BODY:-}" | grep -oiE '\b(close[sd]?|fix(e[sd])?|resolve[sd]?)[[:space:]]+#[0-9]+' | grep -oE '[0-9]+$' | sort -un | head -n $MAX)
fi

keys=("${jira[@]+"${jira[@]}"}"); for n in "${issues[@]+"${issues[@]}"}"; do keys+=("#$n"); done
count=${#keys[@]}
out keys "$(IFS=,; echo "${keys[*]-}")"; out count "$count"
if [ "$count" -eq 0 ]; then
  echo "No ticket found for this PR: no Jira key leading the title or in the branch name, and no GitHub issue it closes." > "$OUT"
  out fetched 0; out status none; out detail "no Jira key in the title or branch, and no linked or closed GitHub issue"; exit 0
fi

# --- 3. Fetch each ticket ----------------------------------------------------------------------
fetched=0; notfound=(); failed=(); unconfigured=()
render_adf() {   # Atlassian Document Format -> plain text (headings, paragraphs, lists, code)
  python3 - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); f = d.get("fields", {})
def text(n, depth=0):
    if isinstance(n, list): return "".join(text(x, depth) for x in n)
    if not isinstance(n, dict): return ""
    t, c = n.get("type"), n.get("content", [])
    if t == "text": return n.get("text", "")
    if t == "hardBreak": return "\n"
    if t == "heading": return "\n" + "#" * n.get("attrs", {}).get("level", 2) + " " + text(c) + "\n"
    if t == "paragraph": return text(c) + "\n"
    if t in ("bulletList", "orderedList"): return "".join("  " * depth + "- " + text(i.get("content", []), depth + 1).strip() + "\n" for i in c)
    if t == "codeBlock": return "```\n" + text(c) + "\n```\n"
    return text(c, depth)
desc = f.get("description")
body = text(desc.get("content", [])) if isinstance(desc, dict) else (desc or "")
print(f"# {sys.argv[2]}: {f.get('summary','')}")
print(f"Type: {(f.get('issuetype') or {}).get('name','?')} | Status: {(f.get('status') or {}).get('name','?')} | Labels: {', '.join(f.get('labels') or []) or '-'}\n")
print(body.strip() or "(no description)")
PY
}
for k in "${keys[@]}"; do
  if [[ "$k" == \#* ]]; then
    n="${k#\#}"
    if gh issue view "$n" --repo "${GITHUB_REPOSITORY:-}" --json number,title,body,labels,state \
         --template '# {{.title}} (#{{.number}}, {{.state}})
{{range .labels}}[{{.name}}] {{end}}

{{.body}}
' >> "$OUT" 2>/dev/null; then fetched=$((fetched + 1)); printf '\n---\n\n' >> "$OUT"
    else notfound+=("$k"); fi
    continue
  fi
  if [ -z "${JIRA_BASE_URL:-}" ] || [ -z "${JIRA_API_TOKEN:-}" ]; then unconfigured+=("$k"); continue; fi
  tmp="$(mktemp)"
  if [ -n "${JIRA_EMAIL:-}" ]; then auth=(-u "$JIRA_EMAIL:$JIRA_API_TOKEN"); else auth=(-H "Authorization: Bearer $JIRA_API_TOKEN"); fi
  code="$(curl -sS -o "$tmp" -w '%{http_code}' "${auth[@]}" -H 'Accept: application/json' \
    "${JIRA_BASE_URL%/}/rest/api/3/issue/$k?fields=summary,description,status,issuetype,labels" || echo 000)"
  case "$code" in
    200) render_adf "$tmp" "$k" >> "$OUT"; printf '\n---\n\n' >> "$OUT"; fetched=$((fetched + 1)) ;;
    404) notfound+=("$k") ;;
    *)   failed+=("$k (HTTP $code)") ;;
  esac
  rm -f "$tmp"
done
out fetched "$fetched"

if [ ${#failed[@]} -gt 0 ]; then
  echo "::warning title=Ticket fetch failed::Jira returned an error for ${failed[*]} (check JIRA_* settings or token expiry)."
  out status fetch-failed; out detail "Jira returned an error for ${failed[*]}: check the JIRA_* settings or the token's expiry"
elif [ ${#notfound[@]} -gt 0 ]; then
  out status not-found; out detail "not found: ${notfound[*]}"
elif [ ${#unconfigured[@]} -gt 0 ] && [ "$fetched" -eq 0 ]; then
  out status jira-not-configured; out detail "Jira key(s) ${unconfigured[*]} found, but Jira is not configured (jira-base-url input, JIRA_EMAIL / JIRA_API_TOKEN secrets)"
else
  out status ok; out detail "read ${fetched} of ${count}: $(IFS=,; echo "${keys[*]}")"
fi
[ -s "$OUT" ] || echo "Tickets could not be read: $(IFS=,; echo "${keys[*]}")." > "$OUT"
exit 0
