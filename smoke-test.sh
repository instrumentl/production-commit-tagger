#!/usr/bin/env bash
# Smoke test: exercise the action end-to-end against a throwaway consumer repo,
# running the same two steps action.yml runs on the GitHub Actions runner.
#
# Usage: ./smoke-test.sh
set -euo pipefail

ACTION_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

echo "==> building sandbox consumer repo at $SANDBOX"
cd "$SANDBOX"
git init -q -b main
git config user.email "test@example.com"
git config user.name "Test User"
echo first  > a.txt && git add . && git commit -q -m "chore: initial"
git tag -a v2.202604010000.1 -m "first deploy"
echo second > b.txt && git add . && git commit -q -m "feat(api): add new endpoint"
echo third  > c.txt && git add . && git commit -q -m "fix: handle nil case

BREAKING CHANGE: response shape changed"
echo fourth > d.txt && git add . && git commit -q -m "perf: speed up parser"
HEAD_SHA="$(git rev-parse HEAD)"

echo "==> step 1: uv sync --frozen --no-dev (from action_path)"
cd "$ACTION_PATH"
uv sync --frozen --no-dev

echo "==> step 2: uv run python create_tag.py ..."
GITHUB_WORKSPACE="$SANDBOX" \
GITHUB_SHA="$HEAD_SHA" \
GITHUB_ACTOR="smoke-test" \
GITHUB_OUTPUT="$SANDBOX/github_output.txt" \
uv run python create_tag.py \
  --verbose \
  --prefix v2. \
  --timestamp-format "%Y%m%d%H%M" \
  --token none \
  --repository instrumentl/smoke-test \
  2026-04-24T18:44:05Z 4477349984

echo "==> asserting outputs"
EXPECTED_TAG="v2.202604241844.4477349984"
EXPECTED_NOTES="release_notes-${EXPECTED_TAG}.txt"

grep -qx "tag_name=${EXPECTED_TAG}"              "$SANDBOX/github_output.txt"
grep -qx "release_body_path=${EXPECTED_NOTES}"   "$SANDBOX/github_output.txt"
grep -qx "commit_authors="                       "$SANDBOX/github_output.txt"

test -f "$SANDBOX/$EXPECTED_NOTES"
grep -q "Features:"                  "$SANDBOX/$EXPECTED_NOTES"
grep -q "Bug Fixes:"                 "$SANDBOX/$EXPECTED_NOTES"
grep -q "Performance Improvements:"  "$SANDBOX/$EXPECTED_NOTES"
grep -q "BREAKING CHANGES:"          "$SANDBOX/$EXPECTED_NOTES"
grep -q "add new endpoint"           "$SANDBOX/$EXPECTED_NOTES"
grep -q "handle nil case"            "$SANDBOX/$EXPECTED_NOTES"
grep -q "speed up parser"            "$SANDBOX/$EXPECTED_NOTES"
grep -q "response shape changed"     "$SANDBOX/$EXPECTED_NOTES"

git -C "$SANDBOX" rev-parse "refs/tags/${EXPECTED_TAG}" >/dev/null

echo "==> smoke test OK"
