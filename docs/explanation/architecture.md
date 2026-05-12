# Architecture

How yarlpattern is laid out, what each module is responsible for, and why
the project is pure Python with a deliberate seam for an optional engine.

## Layout

```text
src/yarlpattern/
├── __init__.py           public surface (re-exports)
├── _tokenizer.py         §2.1.1 — pattern string → token list
├── _parts.py             §2.1.4 — tokens → part list (with options)
├── _regex.py             §2.2 — part list → regex source string
├── _constructor.py       §1.6 — constructor-string FSM (URL-shaped strings)
├── _canonicalize.py      percent-encoding, IDNA, IPv6 — per-component
├── _url.py               yarl-shaped URL parsing + baseURL inheritance
├── _pattern.py           the public URLPattern class
├── _regex_engine/        pluggable regex backend (stdlib re | `regex` package)
└── _version.py           single source of truth, stamped by PSR
```

Each module corresponds either to a spec section or to a well-bounded
piece of preprocessing the spec mandates. Variable names track the spec
text so cross-references in `reference/spec/urlpattern.md` stay legible
when reading the implementation.

```text
tests/
├── conftest.py                       WPT-data parametrization
├── test_wpt.py                       urlpattern.any.js (366 cases)
├── test_wpt_constructor.py           urlpattern-constructor.any.js (4)
├── test_wpt_hasregexpgroups.py       urlpattern-hasregexpgroups.any.js (55)
├── test_wpt_compare.py               urlpattern-compare.tentative.any.js (25)
├── test_wpt_generate.py              urlpattern-generate.tentative.any.js (19)
└── test_*.py                         unit-level tests for each module
```

Test files named `test_wpt*.py` are parametrized from the WPT fixture
JSON; the other `test_*.py` files are module-level unit tests.

```text
reference/                  (gitignored, populated by scripts/fetch_references.sh)
├── spec/                   rendered WHATWG URLPattern spec
├── impls/                  shallow clones of Ada, Blink, rust-urlpattern, the polyfill, yarl
└── wpt/                    sparse clone of web-platform-tests/wpt (urlpattern/ only)
```

`reference/` exists for contributors cross-checking against upstream;
it never ships, and CI fetches only the WPT corpus via the dedicated
`scripts/fetch_wpt_corpus.sh` script with size and integrity checks.

## Why pure Python

A correct, readable, dependency-light implementation is the goal.

**Runtime dependencies are minimal.** The only required runtime dep is
[`yarl`](https://github.com/aio-libs/yarl) for WHATWG URL parsing —
itself a pure-Python library with a tight dependency footprint.
`yarl` is the lingua franca of URL handling in the aio-libs ecosystem,
and using it here means yarlpattern composes naturally with aiohttp,
httpx-via-yarl-converters, and the other URL-y libraries Python web
developers already use.

**No compiled wheels means no platform matrix.** A pure-Python wheel
installs on every CPython, every PyPy, every architecture, every
OS. No `manylinux` / `musllinux` / `macosx_arm64` proliferation; no
build-from-source surprises in environments without a C toolchain.
For a library that's a *correctness* primitive (routing decisions
have to be right), the operational simplicity is part of the value
proposition.

**A faster backend can plug in without changing the API surface.** The
matcher is engine-agnostic: it compiles patterns to regex *source
strings* and hands them to a `Protocol`-defined engine for compilation
and matching. Two engines ship today — the stdlib `re` module (the
default) and Matthew Barnett's third-party
[`regex`](https://pypi.org/project/regex/) package (opt-in via
`pip install yarlpattern[regex]`, activates the JS `v`-flag set-ops
that close the last 2 of 366 WPT data-corpus cases).

```python
# src/yarlpattern/_regex_engine/protocols.py — sketch
class RegexEngine(Protocol):
    def compile(self, pattern: str, *, flags: int = 0) -> "CompiledRegex": ...

class CompiledRegex(Protocol):
    def fullmatch(self, s: str) -> "MatchResult | None": ...
    @property
    def groups(self) -> int: ...
```

A future PyO3 wrapper around Chromium's
[`liburlpattern`](https://github.com/whatwg/urlpattern/blob/main/202012-update.md#liburlpattern)
or
[`rust-urlpattern`](https://github.com/denoland/rust-urlpattern) would
slot in as one more adapter under `_regex_engine/`. The public
`URLPattern` API doesn't change; users opt into the faster engine the
same way they opt into the `regex` package today.

## The matching pipeline

A pattern goes through these stages on `URLPattern(...)` construction:

```text
input string or dict
  → _url.py            split into (per-component pattern strings, baseURL, options)
  → _constructor.py    (if string input) FSM splits the constructor string
  → _canonicalize.py   per-component canonicalization (IDNA, percent-encoding)
  → _tokenizer.py      tokenize each component's pattern string
  → _parts.py          parse tokens into a part list (literal | group | wildcard)
  → _regex.py          generate a regex source string + named-group table
  → _regex_engine/     compile the regex with the active engine
  → URLPattern         immutable, stored as compiled-regex-per-component
```

Match-time (`pat.test(...)` / `pat.exec(...)`) reverses the input side:

```text
input URL string or yarl.URL or dict
  → _url.py            parse via yarl, split into components (yarl.URL fast path)
  → _canonicalize.py   per-component canonicalize the input the same way
  → per-component      compiled regex's fullmatch against the canonical form
  → URLPatternResult   structured result with .protocol / .hostname / … groups
```

The same canonicalization function runs on both pattern strings (at
compile time) and input URLs (at match time), so two URLs the spec
considers equivalent always match the same pattern — even if their
textual form differs in case, percent-encoding, or trailing slashes.

## Where the implementation diverges from the simplest possible shape

Three places worth knowing about:

1. **A fast path for `yarl.URL` inputs.** `pat.test(request.url)` is
   the most common call shape in an aiohttp handler. yarlpattern reads
   pre-parsed components straight off the `yarl.URL` object instead
   of stringifying and reparsing.

2. **Per-component `with_*` derivers.** Alongside the spec's
   `with_(**kwargs)`, yarlpattern exposes one `with_<component>`
   method per URL component (`with_hostname`, `with_pathname`, …) —
   matching yarl's habit for the single-component-change case.

3. **Spec-strict choices where yarl is more permissive.** Three places
   yarlpattern is stricter than yarl, all because WHATWG URLPattern
   requires it: case-preserving `%XX` passthrough, U+FFFD substitution
   for unpaired surrogates, and hostname truncation at `?` / `#` / `/` /
   `\`. The [yarl comparison page](../comparisons/yarl.md) covers each
   with the WPT case that pins it down.
