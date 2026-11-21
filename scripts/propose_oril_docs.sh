#!/usr/bin/env bash
set -euo pipefail
base=main
branch=docs/oril-generated
if [[ "${ORIL_PREVIEW:-0}" == 1 ]]; then
  base=review/oril-persistent-memory-v1
  branch=docs/oril-generated-preview
fi
git fetch origin "$base"
test "$(git rev-parse HEAD)" = "$(git rev-parse FETCH_HEAD)"
prior=$(git ls-remote origin "refs/heads/$branch" | cut -f1)
pr=$(gh pr list --base "$base" --head "$branch" --json number,isDraft)
jq -e 'all(.[]; .isDraft == true)' <<< "$pr"
git apply --index "$RUNNER_TEMP/oril-generated/docs.patch"
if git diff --cached --no-color -U0 | grep -E '^\+[^+]' | grep -E '(-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|[Bb]earer [A-Za-z0-9._/-]{20,})' > /dev/null; then
  echo "Credential pattern detected in generated additions" >&2
  exit 1
fi
changed=$(git diff --cached --name-only)
if grep -Ev '^(README\.md|docs/(status/current\.md|status/github\.json|roadmap\.md|evolution/ledger\.jsonl|memory/lessons\.jsonl|metrics/trends\.json))$' <<< "$changed"; then exit 1; fi
if test -n "$prior"; then
  git fetch origin "$prior"
  if git diff --cached --quiet "$prior"; then
    if test "$(jq length <<< "$pr")" = 0; then gh pr create --draft --base "$base" --head "$branch" --title "Sync ORIL evidence" --body "Review generated public evidence and measurements."; fi
    exit 0
  fi
  # A rebuilt proposal must retain pending append-only records.
  for path in docs/evolution/ledger.jsonl docs/memory/lessons.jsonl; do
    git show "$prior:$path" | while IFS= read -r row; do grep -Fxq -- "$row" "$path" || exit 1; done
  done
fi
git -c user.name=github-actions -c user.email=41898282+github-actions[bot]@users.noreply.github.com commit -m "Refresh ORIL public evidence"
git push --force-with-lease="refs/heads/$branch:$prior" origin "HEAD:refs/heads/$branch"
if test "$(jq length <<< "$pr")" = 0; then gh pr create --draft --base "$base" --head "$branch" --title "Sync ORIL evidence" --body "Review generated public evidence and measurements."; fi
