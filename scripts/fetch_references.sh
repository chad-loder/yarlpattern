#!/usr/bin/env bash
# Repopulate reference/ from scratch — at known-good upstream SHAs.
#
# `reference/` is gitignored — this repo stays a pure Python implementation
# and does not vendor upstream code. Run this after cloning, or whenever
# you bump a pin below.
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ Why pin SHAs                                                        │
# └─────────────────────────────────────────────────────────────────────┘
# The WPT data corpus is the load-bearing artifact for our compliance
# claims (466 of 469 reported cases come from it). If we track upstream
# HEAD, an unrelated WPT-wide refactor or test-data tweak silently shifts
# our reported pass count. Pinning makes "X/Y passing" reproducible at
# any future date.
#
# To bump: edit the SHA + date below, re-run, re-run `just check`, and
# re-run `just compliance-report` to refresh `docs/wpt-compliance.md`.
#
# ┌─────────────────────────────────────────────────────────────────────┐
# │ Pinned upstream commits (SHA + capture date)                        │
# └─────────────────────────────────────────────────────────────────────┘
# WPT: web-platform-tests/wpt
#   load-bearing — every conformance test runs against this corpus
WPT_REF="dd54691426c23a08c6f4a0972b2c40965307e5ce"            # 2026-05-11
#
# WHATWG URLPattern spec source (bikeshed)
#   our citations in code comments reference §-numbers from this commit
SPEC_REF="203d435c32272a10bdccc2c6dfa8a51ee5c6b92c"           # 2026-03-20
#
# ada-url/ada — C++ reference impl (urlpattern subset, sparse checkout)
ADA_REF="e56e4605319eadafeb4c70d71a12aaeaee90f538"            # 2026-05-05
#
# denoland/rust-urlpattern — the cleanest type-translatable port
RUST_REF="e29804d15bdc60797c1c7f715d90480ace0bb451"           # 2026-02-12 (v0.6.0)
#
# kenchris/urlpattern-polyfill — the WICG reference JS polyfill
POLYFILL_REF="f147a0f42a94a29ec1dcd229b218f3a700377f91"       # 2025-05-07
#
# aio-libs/yarl — the URL parser we depend on at runtime
YARL_REF="e25e8d23e6912db52a23513ef1f6a17f889751ef"           # 2026-05-08
#
# Chromium blink/url_pattern subtree.
#
# Currently un-pinned (``refs/heads/main``). The chromium/src gitiles
# archive endpoint accepts arbitrary SHAs, so pinning is possible —
# but the workflow requires manual querying because chromium's gitiles
# doesn't expose unauthenticated JSON log endpoints from arbitrary
# clients, so the script can't introspect "what SHA did I just fetch?"
# automatically.
#
# To pin: visit
#   https://chromium.googlesource.com/chromium/src/+log/main/third_party/blink/renderer/core/url_pattern
# in a browser, copy the latest commit SHA, set it here, and re-run.
#
# Until then, this is the only reference whose contents are not
# bit-for-bit reproducible from this script.
CHROMIUM_REF="refs/heads/main"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="$REPO_ROOT/reference"
SPEC="$REF/spec"
IMPLS="$REF/impls"
WPT="$REF/wpt"

mkdir -p "$SPEC" "$IMPLS" "$WPT"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

# pin_clone <dir> <url> <sha> [sparse-paths...]
#
# Clone or update a repository at a *specific* commit. Treeless filter
# (--filter=blob:none) skips file blobs for unreached paths — cheap.
# Sparse-checkout is applied before checkout so we never materialize
# files we don't need.
#
# Idempotent: if the directory already exists at the right SHA, this is
# a no-op other than a quiet ``git checkout``.
pin_clone() {
  local dir="$1" url="$2" sha="$3"
  shift 3
  local sparse_paths=("$@")
  if [[ ! -d "$dir/.git" ]]; then
    git clone --filter=blob:none --no-checkout "$url" "$dir"
  fi
  if [[ ${#sparse_paths[@]} -gt 0 ]]; then
    git -C "$dir" sparse-checkout init --no-cone >/dev/null 2>&1 || true
    git -C "$dir" sparse-checkout set "${sparse_paths[@]}"
  fi
  # Fetch the target SHA if we don't already have it. ``git rev-parse``
  # exits non-zero when the SHA isn't local yet.
  if ! git -C "$dir" rev-parse --verify "$sha^{commit}" >/dev/null 2>&1; then
    git -C "$dir" fetch --filter=blob:none origin "$sha"
  fi
  git -C "$dir" checkout --quiet "$sha"
}

# ---- WHATWG URLPattern specification ---------------------------------
echo "==> whatwg/urlpattern  pinned to ${SPEC_REF:0:12}"
pin_clone "$SPEC/whatwg-urlpattern" \
  https://github.com/whatwg/urlpattern.git \
  "$SPEC_REF"

echo "==> Fetching rendered single-page spec..."
curl -fsSL https://urlpattern.spec.whatwg.org/ -o "$SPEC/urlpattern.spec.html"

# Convert to markdown. Prefer pandoc; fall back to ``uvx markdownify``.
if command -v pandoc >/dev/null 2>&1; then
  echo "==> Converting spec to markdown via pandoc..."
  pandoc -f html -t gfm --wrap=preserve "$SPEC/urlpattern.spec.html" -o "$SPEC/urlpattern.md"
elif command -v uvx >/dev/null 2>&1; then
  echo "==> Converting spec to markdown via uvx markdownify..."
  uvx --from markdownify markdownify "$SPEC/urlpattern.spec.html" > "$SPEC/urlpattern.md"
else
  echo "  Neither pandoc nor uvx available — skipping markdown conversion." >&2
fi

# ---- Reference implementations ---------------------------------------
echo "==> ada-url/ada  pinned to ${ADA_REF:0:12}  (sparse)"
pin_clone "$IMPLS/ada" \
  https://github.com/ada-url/ada.git \
  "$ADA_REF" \
  src include \
  tests/wpt_tests.cpp \
  tests/url_pattern_tests.cpp \
  tests/url_pattern_regex_tests.cpp

echo "==> denoland/rust-urlpattern  pinned to ${RUST_REF:0:12}"
pin_clone "$IMPLS/rust-urlpattern" \
  https://github.com/denoland/rust-urlpattern.git \
  "$RUST_REF"

echo "==> kenchris/urlpattern-polyfill  pinned to ${POLYFILL_REF:0:12}"
pin_clone "$IMPLS/urlpattern-polyfill" \
  https://github.com/kenchris/urlpattern-polyfill.git \
  "$POLYFILL_REF"

echo "==> aio-libs/yarl  pinned to ${YARL_REF:0:12}"
pin_clone "$IMPLS/yarl" \
  https://github.com/aio-libs/yarl.git \
  "$YARL_REF"

# Chromium blink/url_pattern via gitiles archive. The URL embeds the SHA
# directly, so reproducibility is whatever Chromium's gitiles serves for
# that commit — they retain history indefinitely.
echo "==> Chromium blink/url_pattern  pinned to ${CHROMIUM_REF:0:12}"
mkdir -p "$IMPLS/chromium-url_pattern"
curl -fsSL \
  "https://chromium.googlesource.com/chromium/src/+archive/${CHROMIUM_REF}/third_party/blink/renderer/core/url_pattern.tar.gz" \
  -o "$IMPLS/chromium-url_pattern/snapshot.tar.gz"
tar -xzf "$IMPLS/chromium-url_pattern/snapshot.tar.gz" -C "$IMPLS/chromium-url_pattern"
rm -f "$IMPLS/chromium-url_pattern/snapshot.tar.gz"

# ---- WPT test data (load-bearing for compliance) ---------------------
echo "==> web-platform-tests/wpt  pinned to ${WPT_REF:0:12}  (sparse, urlpattern only)"
pin_clone "$WPT" \
  https://github.com/web-platform-tests/wpt.git \
  "$WPT_REF" \
  urlpattern resources

# ---- Final summary ---------------------------------------------------
echo
echo "All reference material pinned and materialized under $REF/"
echo
echo "Captured commit SHAs (also listed at the top of this script):"
printf "  %-28s  %s\n" "web-platform-tests/wpt"          "$WPT_REF"
printf "  %-28s  %s\n" "whatwg/urlpattern (spec)"        "$SPEC_REF"
printf "  %-28s  %s\n" "ada-url/ada"                     "$ADA_REF"
printf "  %-28s  %s\n" "denoland/rust-urlpattern"        "$RUST_REF"
printf "  %-28s  %s\n" "kenchris/urlpattern-polyfill"    "$POLYFILL_REF"
printf "  %-28s  %s\n" "aio-libs/yarl"                   "$YARL_REF"
printf "  %-28s  %s\n" "chromium/src (blink/url_pat)"    "$CHROMIUM_REF"
