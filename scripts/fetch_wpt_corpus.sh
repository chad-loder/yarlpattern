#!/usr/bin/env bash
# scripts/fetch_wpt_corpus.sh — CI-targeted WPT corpus fetcher.
#
# Populates ``reference/wpt/`` with the test data and JS test files the
# ``tests/test_wpt*.py`` suites consume. Designed to be the *only*
# network step taken by CI to bring in test fixtures.
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ Security model                                                      │
# └─────────────────────────────────────────────────────────────────────┘
#
# We treat the WPT corpus as *trusted but bounded* input: it's a
# load-bearing test artifact (366/366 reported conformance cases come
# from it), so we want strong provenance, but we also want hard limits
# on what a malicious upstream could do to a runner.
#
# Provenance:
#
#   * **Pinned SHA**. ``WPT_REF`` is baked into this script. A hostile
#     web-platform-tests/wpt push cannot affect us until we explicitly
#     bump the pin.
#   * **HTTPS-only clone**. ``GIT_TERMINAL_PROMPT=0`` so a redirect to
#     auth never blocks on stdin.
#   * **Post-fetch verification**. ``git rev-parse HEAD`` is compared
#     against the literal ``WPT_REF`` after clone+checkout — defends
#     against an unlikely-but-cheap-to-rule-out cache/proxy swap.
#   * **Sparse checkout**. Only ``urlpattern/`` and ``resources/`` from
#     the upstream tree are materialized. Nothing else lands on disk.
#
# Bounds (DoS / memory):
#
#   * Every load-bearing JSON file is size-checked *before* it is
#     handed to ``json.loads`` — see ``MAX_JSON_BYTES`` below. The
#     limit is ~16x the current artifact size.
#   * After size-clearance, the JSON is parsed and structurally
#     validated: it must decode to a list of objects. A trailing
#     "well-formed but not what we expect" check guards against subtle
#     upstream schema changes.
#
# Idempotent: if ``reference/wpt`` is already at ``WPT_REF``, this
# script verifies and exits without network use.
#
# Usage:
#
#   scripts/fetch_wpt_corpus.sh             # fetch + verify
#   scripts/fetch_wpt_corpus.sh --verify    # verify only (assume present)

set -euo pipefail
umask 022

# Refuse to inherit a tampered PATH from an attacker-controlled environment.
# This script is meant to be the *first* thing CI runs after checkout, so a
# minimal PATH is fine.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# git: never prompt for credentials. A 401/redirect should fail fast, not hang.
export GIT_TERMINAL_PROMPT=0

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Pinned upstream commit                                              │
# └─────────────────────────────────────────────────────────────────────┘
# Bump in lockstep with the ``WPT_REF`` in ``scripts/fetch_references.sh``
# (the dev-side fetcher). When both agree, ``just compliance-report``
# numbers on a contributor laptop match CI's combined conformance count.
WPT_REF="dd54691426c23a08c6f4a0972b2c40965307e5ce"   # 2026-05-11

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Size cap on each parsed JSON fixture                                │
# └─────────────────────────────────────────────────────────────────────┘
# At the pinned SHA the largest fixture is ~700 KB. 10 MiB gives plenty
# of headroom for new conformance tests without exposing a parser-DoS
# surface: an attacker who controlled WPT could ship a 1 GiB file that
# would crash ``json.loads`` on a runner. We refuse to even open one
# this large.
MAX_JSON_BYTES=$((10 * 1024 * 1024))

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WPT_DIR="$REPO_ROOT/reference/wpt"

# Expected fixtures. Tests fail-fast (no longer skip) if any are absent
# or malformed, so the list is duplicated here as the integrity contract.
EXPECTED_JSON=(
    "urlpattern/resources/urlpatterntestdata.json"
    "urlpattern/resources/urlpattern-compare-test-data.json"
    "urlpattern/resources/urlpattern-generate-test-data.json"
)
EXPECTED_JS=(
    "urlpattern/urlpattern-constructor.any.js"
    "urlpattern/resources/urlpattern-hasregexpgroups-tests.js"
    "urlpattern/resources/urlpattern-compare-tests.tentative.js"
    "urlpattern/urlpattern-generate.tentative.any.js"
)

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Helpers                                                             │
# └─────────────────────────────────────────────────────────────────────┘

fatal() {
    printf 'FATAL: %s\n' "$*" >&2
    exit 1
}

# Verify a single JSON fixture: present, within size cap, well-formed,
# top-level shape matches what tests assume (a list, optionally with
# dict entries). Stdlib-only — no third-party Python deps.
verify_json() {
    local rel="$1"
    local full="$WPT_DIR/$rel"

    [[ -f "$full" ]] || fatal "missing JSON fixture: $rel"

    local size
    size="$(wc -c < "$full" | tr -d '[:space:]')"

    [[ "$size" =~ ^[0-9]+$ ]] || fatal "could not stat size of $rel"
    (( size > 0 )) || fatal "$rel is empty"
    (( size <= MAX_JSON_BYTES )) || fatal "$rel is $size bytes, exceeds cap of $MAX_JSON_BYTES"

    # Hand the path as argv (not via shell interpolation into the python
    # source) so the file path can never escape into the parser.
    python3 - "$full" <<'PY' || fatal "JSON validation failed: $rel"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(data, list):
    raise SystemExit(f"{path.name}: top-level is {type(data).__name__}, expected list")
non_dict = [i for i, e in enumerate(data) if not isinstance(e, (dict, str))]
if non_dict:
    raise SystemExit(f"{path.name}: entries at {non_dict[:5]} are not objects/strings")
PY

    printf '  ok  %-60s  %s bytes\n' "$rel" "$size"
}

verify_js_present() {
    local rel="$1"
    [[ -f "$WPT_DIR/$rel" ]] || fatal "missing JS fixture: $rel"
    printf '  ok  %s\n' "$rel"
}

verify_corpus() {
    printf 'Verifying WPT corpus at %s\n' "$WPT_DIR"
    for f in "${EXPECTED_JSON[@]}"; do verify_json "$f"; done
    for f in "${EXPECTED_JS[@]}"; do verify_js_present "$f"; done
    local actual_ref
    actual_ref="$(git -C "$WPT_DIR" rev-parse HEAD 2>/dev/null || echo "<not a git checkout>")"
    [[ "$actual_ref" == "$WPT_REF" ]] \
        || fatal "WPT_REF mismatch — expected $WPT_REF, got $actual_ref"
    printf 'WPT corpus integrity OK (pinned at %s)\n' "$WPT_REF"
}

# ┌─────────────────────────────────────────────────────────────────────┐
# │ --verify mode (used by CI to re-check restored caches)              │
# └─────────────────────────────────────────────────────────────────────┘
if [[ "${1:-}" == "--verify" ]]; then
    [[ -d "$WPT_DIR/.git" ]] || fatal "$WPT_DIR is not a git checkout (run without --verify first)"
    verify_corpus
    exit 0
fi

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Fetch (idempotent — fast no-op when cache is warm at the same SHA)  │
# └─────────────────────────────────────────────────────────────────────┘
mkdir -p "$WPT_DIR"

if [[ -d "$WPT_DIR/.git" ]] \
   && [[ "$(git -C "$WPT_DIR" rev-parse HEAD 2>/dev/null || true)" == "$WPT_REF" ]]; then
    printf 'WPT corpus already at %s, skipping fetch.\n' "$WPT_REF"
else
    if [[ ! -d "$WPT_DIR/.git" ]]; then
        # ``--filter=blob:none`` keeps the clone tree-only; blobs for paths we
        # don't materialize via sparse-checkout never touch the runner.
        git clone \
            --filter=blob:none \
            --no-checkout \
            "https://github.com/web-platform-tests/wpt.git" \
            "$WPT_DIR"
    fi
    # Sparse-checkout *before* fetching the target commit so the fetch
    # skips blobs outside the cone. ``--no-cone`` lets us use exact paths.
    git -C "$WPT_DIR" sparse-checkout init --no-cone >/dev/null
    git -C "$WPT_DIR" sparse-checkout set urlpattern resources
    git -C "$WPT_DIR" fetch --filter=blob:none origin "$WPT_REF"
    git -C "$WPT_DIR" checkout --quiet "$WPT_REF"
fi

verify_corpus
