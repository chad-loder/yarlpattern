#!/usr/bin/env bash
# scripts/fetch_polyfill_corpus.sh — CI-targeted polyfill corpus fetcher.
#
# Populates ``reference/polyfill/`` with the
# [WICG urlpattern-polyfill](https://github.com/kenchris/urlpattern-polyfill)
# test fixtures the ``tests/test_polyfill*.py`` suites consume.
#
# The polyfill is the reference JavaScript implementation of the WHATWG
# URLPattern Standard. Running its own test corpus against yarlpattern
# is a second cross-implementation conformance vector beyond the
# upstream WPT corpus that ``scripts/fetch_wpt_corpus.sh`` fetches.
#
# Security posture follows ``scripts/fetch_wpt_corpus.sh`` byte-for-byte:
# pinned SHA, HTTPS-only sparse-checkout, post-fetch SHA verification,
# per-file size cap, JSON well-formedness + shape check, ``--verify``
# mode for re-checking restored caches.

set -euo pipefail
umask 022

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export GIT_TERMINAL_PROMPT=0

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Pinned upstream commit                                              │
# └─────────────────────────────────────────────────────────────────────┘
# Bump in lockstep with the ``POLYFILL_REF`` in
# ``scripts/fetch_references.sh`` (the dev-side fetcher). Same convention
# as the WPT pin.
POLYFILL_REF="f147a0f42a94a29ec1dcd229b218f3a700377f91"   # 2025-05-07

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Size cap on each parsed JSON fixture                                │
# └─────────────────────────────────────────────────────────────────────┘
# At the pinned SHA the largest fixture is ~85 KB. 10 MiB gives plenty
# of headroom without exposing a parser-DoS surface to a malicious
# upstream.
MAX_JSON_BYTES=$((10 * 1024 * 1024))

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLY_DIR="$REPO_ROOT/reference/polyfill"

EXPECTED_JSON=(
    "test/urlpatterntestdata.json"
    "test/urlpattern-compare-test-data.json"
)

fatal() {
    printf 'FATAL: %s\n' "$*" >&2
    exit 1
}

verify_json() {
    local rel="$1"
    local full="$POLY_DIR/$rel"

    [[ -f "$full" ]] || fatal "missing JSON fixture: $rel"

    local size
    size="$(wc -c < "$full" | tr -d '[:space:]')"

    [[ "$size" =~ ^[0-9]+$ ]] || fatal "could not stat size of $rel"
    (( size > 0 )) || fatal "$rel is empty"
    (( size <= MAX_JSON_BYTES )) || fatal "$rel is $size bytes, exceeds cap of $MAX_JSON_BYTES"

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

verify_corpus() {
    printf 'Verifying polyfill corpus at %s\n' "$POLY_DIR"
    for f in "${EXPECTED_JSON[@]}"; do verify_json "$f"; done
    local actual_ref
    actual_ref="$(git -C "$POLY_DIR" rev-parse HEAD 2>/dev/null || echo "<not a git checkout>")"
    [[ "$actual_ref" == "$POLYFILL_REF" ]] \
        || fatal "POLYFILL_REF mismatch — expected $POLYFILL_REF, got $actual_ref"
    printf 'Polyfill corpus integrity OK (pinned at %s)\n' "$POLYFILL_REF"
}

if [[ "${1:-}" == "--verify" ]]; then
    [[ -d "$POLY_DIR/.git" ]] || fatal "$POLY_DIR is not a git checkout (run without --verify first)"
    verify_corpus
    exit 0
fi

mkdir -p "$POLY_DIR"

if [[ -d "$POLY_DIR/.git" ]] \
   && [[ "$(git -C "$POLY_DIR" rev-parse HEAD 2>/dev/null || true)" == "$POLYFILL_REF" ]]; then
    printf 'Polyfill corpus already at %s, skipping fetch.\n' "$POLYFILL_REF"
else
    if [[ ! -d "$POLY_DIR/.git" ]]; then
        git clone \
            --filter=blob:none \
            --no-checkout \
            "https://github.com/kenchris/urlpattern-polyfill.git" \
            "$POLY_DIR"
    fi
    git -C "$POLY_DIR" sparse-checkout init --no-cone >/dev/null
    git -C "$POLY_DIR" sparse-checkout set test
    git -C "$POLY_DIR" fetch --filter=blob:none origin "$POLYFILL_REF"
    git -C "$POLY_DIR" checkout --quiet "$POLYFILL_REF"
fi

verify_corpus
