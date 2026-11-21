#!/usr/bin/env bash
# Exercise the real publisher against local Git and a file-backed draft PR double.
set -euo pipefail
repo=$PWD
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export RUNNER_TEMP="$tmp"
mkdir -p "$tmp/bin" "$tmp/oril-generated"
cat > "$tmp/bin/gh" <<'GH'
#!/usr/bin/env bash
set -eu
case "$1 $2" in
  'pr list') if test -e "$RUNNER_TEMP/draft"; then echo '[{"number":1,"isDraft":true}]'; else echo '[]'; fi;;
  'pr create') [[ " $* " == *" --draft "* ]]; test ! -e "$RUNNER_TEMP/draft"; touch "$RUNNER_TEMP/draft";;
  *) exit 1;;
esac
GH
chmod +x "$tmp/bin/gh"
export PATH="$tmp/bin:$PATH"
git init --bare --quiet "$tmp/remote.git"
git clone --quiet "$tmp/remote.git" "$tmp/checkout"
cd "$tmp/checkout"
git switch -c main
mkdir -p docs/{memory,evolution}
touch docs/memory/lessons.jsonl docs/evolution/ledger.jsonl
echo initial > README.md
git add .
git -c user.name=fixture -c user.email=fixture@example.invalid commit -qm initial
git push -q origin main
baseline=$(git rev-parse HEAD)
prepare() {
  git reset --hard -q "$baseline"
  echo "$1" >> README.md
  git diff > "$tmp/oril-generated/docs.patch"
  git restore README.md
}
prepare first
bash "$repo/scripts/propose_oril_docs.sh"
first=$(git ls-remote origin refs/heads/docs/oril-generated)
for delivery in 2 3 4 5; do
  prepare first
  bash "$repo/scripts/propose_oril_docs.sh"
  test "$first" = "$(git ls-remote origin refs/heads/docs/oril-generated)"
done
prepare second
bash "$repo/scripts/propose_oril_docs.sh"
test "$first" != "$(git ls-remote origin refs/heads/docs/oril-generated)"
test "$baseline" = "$(git ls-remote origin refs/heads/main | cut -f1)"
test -f "$tmp/draft"
