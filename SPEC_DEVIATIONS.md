# Spec deviations

This document records every place where yarlpattern intentionally
deviates from the [WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/),
where it relies on a Python-platform substitute for spec behaviour, and
where it is *stricter* than the reference behaviour. Each entry names
the **why** so reviewers can decide whether the gap matters for their
use case.

The conformance baseline is the [upstream WPT urlpattern corpus](https://github.com/web-platform-tests/wpt/tree/master/urlpattern):
469 / 469 cases pass across all five test suites
([report](https://chad-loder.github.io/yarlpattern/wpt-compliance/)).
Everything below is in addition to — not a contradiction of — that
number.

## Where yarlpattern delegates to other libraries

### URL parsing → `yarl`

- **What**: `URLPattern.test(url)`, `URLPattern.exec(url)`, and
  `baseURL=` resolution all parse `url` / `baseURL` strings via
  [`yarl`](https://github.com/aio-libs/yarl).
- **Why**: yarl is a mature, well-maintained, WHATWG-flavoured URL
  parser that is the de facto standard in the aio-libs ecosystem. It
  is itself pure Python.
- **Consequences for spec conformance**: anywhere yarl deviates from
  the WHATWG URL Living Standard, yarlpattern inherits the deviation.
  In practice the WPT conformance numbers above are the load-bearing
  evidence; the corpus exercises the edge cases that matter for the
  URL Pattern Standard. Known yarl-side caveats:
  - yarl normalises percent-encoding case to uppercase for some
    inputs; yarlpattern's per-component canonicalisation preserves
    user-supplied case verbatim where the WHATWG URLPattern spec
    requires it (WPT cases 146 & 148 contrast on this).
  - yarl strips control characters and applies IDNA via the
    `idna` package (see below).

### Hostname IDNA → `idna` package (UTS46 / IDNA2008)

- **What**: hostname canonicalisation routes through
  [`yarl.URL`](https://github.com/aio-libs/yarl), which uses
  the third-party
  [`idna`](https://pypi.org/project/idna/) package for IDNA
  processing.
- **Why**: the `idna` package implements UTS46 (the modern WHATWG
  URL Standard's hostname-processing requirement). Python's stdlib
  `idna` codec implements only IDNA2003 and is not spec-compliant
  for non-ASCII hostnames.
- **Consequence**: hostname patterns containing Unicode resolve
  to UTS46-compliant ASCII labels, matching browser behaviour. This
  is *better* than what a stdlib-only implementation can offer.

### Component-level regex compilation → `re` (default) or `regex` (opt-in)

- **What**: each component pattern is compiled to a regular
  expression, which is then evaluated by either Python's stdlib `re`
  module (default) or Matthew Barnett's
  [`regex`](https://pypi.org/project/regex/) package (opt-in via
  `pip install 'yarlpattern[regex]'`).
- **Why**: Python does not ship an ECMAScript-flavoured regex engine.
  Stdlib `re` covers the vast majority of WHATWG-defined patterns;
  `regex` covers the JavaScript `v`-flag character-class set
  operations that stdlib `re` cannot express.
- **Consequence**: conformance differs by engine:

  | Engine | WPT data-corpus pass rate | Gap |
  |---|---:|---|
  | stdlib `re` (default) | 364 / 366 (99.5%) | `[a&&b]` (intersection) and `[a--b]` (difference) from the JS `v`-flag |
  | `regex` package (`[regex]` extra) | 366 / 366 (100%) | none |

  The two outlier patterns are marked `xfail` with an install hint
  when the `regex` package is not present.

## Where yarlpattern is stricter than yarl

These three behaviours are *required by the WHATWG URLPattern Standard*
and are enforced by yarlpattern's per-component canonicalisation layer,
above what yarl itself does:

### Case-preserving `%XX` passthrough

- **What**: percent-encoded sequences in pattern *literals* are
  preserved with their user-supplied case.
- yarl normalises `caf%c3%a9` → `caf%C3%A9` (uppercase).
- yarlpattern preserves `caf%c3%a9` verbatim.
- **Why**: WHATWG WPT cases 146 and 148 contrast on whether
  `caf%C3%A9` and `caf%c3%a9` round-trip as themselves. Pattern
  equality depends on case being preserved.

### U+FFFD substitution for unpaired surrogates

- **What**: pattern strings containing unpaired UTF-16 surrogates
  have those surrogates substituted with U+FFFD REPLACEMENT
  CHARACTER before UTF-8 percent-encoding.
- yarl's quoter uses `errors="ignore"` and silently drops them.
- yarlpattern's `_canonicalize.py` substitutes.
- **Why**: WPT case 157 (`{pathname: '\ud83d \udeb2'}` →
  `%EF%BF%BD%20%EF%BF%BD`) locks this in. The
  [WHATWG URL standard §1.3](https://url.spec.whatwg.org/#percent-encoded-bytes)
  implicitly mandates U+FFFD substitution because UTF-8 encoding
  requires Unicode scalar values, and surrogate halves are not
  scalar values.

### Hostname truncation at `?` / `#` / `/` / `\`

- **What**: hostname *patterns* containing URL-structural delimiters
  are truncated at the first such character; the remainder is
  silently discarded.
- yarl rejects such hostnames outright with an exception.
- yarlpattern truncates and continues (matching Chromium's
  `CanonicalizeHostnameInternal` behaviour).
- **Why**: a hostname pattern containing `/` was almost certainly a
  paste of a full URL; respecting the prefix is more useful than
  rejecting. WPT covers this with cases like
  `{hostname: 'bad#hostname'}` → compiled hostname `'bad'`.

## Where yarlpattern is stricter than the reference behaviour

### Port parsing rejects non-digit suffixes

- **What**: port values like `"8080xyz"` are rejected as invalid.
  Only fully-numeric ports parse successfully.
- **Why**: the WHATWG URLPattern Standard's port-component
  canonicalisation goes through the URL parser's port-state, which
  rejects any non-digit content. yarlpattern enforces this
  explicitly via per-component validation.
- **Consequence**: webhook-validation patterns that constrain on
  exact port values are robust against junk suffixes. See the
  [Validate inbound webhooks by URL shape](https://chad-loder.github.io/yarlpattern/examples/validate-inbound-webhooks-by-url-shape/)
  example.

## Stable spec, tentative spec, and what is currently `xfail`

The WHATWG URLPattern Standard distinguishes between the *stable* API
surface (constructor, `test`, `exec`, `compareComponent`, component
properties, `hasRegExpGroups`) and the *tentative* surface (`generate`).
yarlpattern's posture:

| Surface | Status |
|---|---|
| Constructor + `test` + `exec` | Implemented; 100% WPT pass with `[regex]` |
| Per-component getter properties | Implemented |
| `compareComponent` | Implemented; 25 / 25 WPT cases pass |
| `hasRegExpGroups` | Implemented; 55 / 55 WPT cases pass |
| **`generate()`** | **Not implemented**; 19 cases `xfail` with `WHATWG_URLPATTERN_RUN_TENTATIVE=1` |

`generate()` is planned for v0.2.0 and tracked in the v0.2.0 roadmap.

## What yarlpattern does *not* deviate on, despite Python's defaults

A few places where the obvious Python-idiomatic choice would have been
a spec deviation, and yarlpattern goes out of its way to match WHATWG:

- **Component-name canonicalisation**: yarlpattern uses the spec's
  names (`protocol`, `username`, `password`, `hostname`, `port`,
  `pathname`, `search`, `hash`) — not yarl's (`scheme`, `user`,
  `host`, `path`, `query`, `fragment`). Cross-runtime portability
  with browser-side JS `URL` and `URLPattern` is preserved by
  construction.
- **Method-name capitalisation**: `compareComponent` and
  `hasRegExpGroups` keep their WHATWG IDL camelCase names. This
  is intentional Python-PEP-8 deviation in favour of literal-text
  compatibility with the spec and with cross-language patterns.
- **Result shape**: `URLPatternResult` mirrors the JS-side shape
  exactly: `result.<component>` is a dict with `'input'` and
  `'groups'` keys; attribute access on a Pythonic `result.<component>.groups`
  would have been more Pythonic but would not match the spec's
  observable behaviour.

## Reporting a deviation

If you find a behaviour yarlpattern produces that contradicts the
WPT urlpattern corpus *or* the WHATWG URLPattern Standard *and* is
not documented above,
[file an issue](https://github.com/chad-loder/yarlpattern/issues/new)
with the pattern, the input, the observed behaviour, and the
spec-required behaviour. Such reports are treated as bugs, not
feature requests.
