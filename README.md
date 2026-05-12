# yarlpattern

[![WPT conformance](https://img.shields.io/badge/WPT%20data%20corpus-100%25%20(366%2F366)-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![WPT auxiliary suites](https://img.shields.io/badge/auxiliary%20suites-84%2F84-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![Stable spec API](https://img.shields.io/badge/stable%20API-implemented-2ea043?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
[![Tentative spec API](https://img.shields.io/badge/tentative%20API-tracked-1f6feb?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776ab?labelColor=24292f&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-6e7681?labelColor=24292f)](LICENSE)

Pure-Python, spec-strict implementation of the [WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/).
The API is shaped to feel familiar to [`yarl`](https://github.com/aio-libs/yarl) users — immutable
pattern objects, component properties named after their URL counterparts, a small surface — and
yarl is what does the underlying URL parsing.

```python
from yarlpattern import URLPattern

# Multi-tenant API: the subdomain identifies the tenant, the path
# captures the API version and the resource tail — all extracted in
# one match call.
pat = URLPattern({
    "hostname": ":tenant.myapp.com",
    "pathname": "/api/v:version/*",
})

result = pat.exec("https://acme.myapp.com/api/v2/users/42")
result.hostname["groups"]["tenant"]    # 'acme'
result.pathname["groups"]["version"]   # '2'
result.pathname["groups"]["0"]         # 'users/42'

pat.test("https://foo.example.com/api/v2/users")  # False — wrong host
pat.test("https://acme.myapp.com/api/users")      # False — no version
```

That's the differentiator. Flask-style `:id` routers match the path component
in isolation; URLPattern matches *across* protocol, hostname, port, path, and
search at once, returning structured named groups per component.

## WHATWG conformance

**366 / 366** Web Platform Tests pass (100%) on
[`urlpattern.any.js`](https://github.com/web-platform-tests/wpt/blob/master/urlpattern/urlpattern.any.js)
— the canonical end-to-end suite driven by
[`urlpatterntestdata.json`](https://github.com/web-platform-tests/wpt/blob/master/urlpattern/resources/urlpatterntestdata.json),
the same corpus Chromium, Safari, Firefox, Ada, and rust-urlpattern validate against. Every
auxiliary WPT suite that covers the stable spec also passes in full.

The corpus is SHA-pinned by [`scripts/fetch_references.sh`](scripts/fetch_references.sh)
to commit
[`dd54691`](https://github.com/web-platform-tests/wpt/commit/dd54691426c23a08c6f4a0972b2c40965307e5ce)
(2026-05-11) so the reported pass count is reproducible at any future date. Bump the pin in the
script and re-run `just check` + `just compliance-report` to refresh against a newer corpus.

### Test corpus matrix

Summary below; the [**full per-case report**](docs/wpt-compliance.md) (regenerate via
`just compliance-report`) lists every one of the 469 WPT cases with its status.

Status legend:
<kbd>✓</kbd> all passing &nbsp;·&nbsp;
<kbd>~</kbd> engine-dependent &nbsp;·&nbsp;
<kbd>◐</kbd> tentative spec, tracked but not implemented &nbsp;·&nbsp;
<kbd>✗</kbd> not implemented.

| WPT runner | Data file | Count | Result |
|---|---|---:|:---|
| `urlpattern.any.js` | `urlpatterntestdata.json` | 366 | <kbd>✓</kbd> &nbsp; **366 / 366** &nbsp; ![100%](https://img.shields.io/badge/-100%25-2ea043) |
| `urlpattern-constructor.any.js` | *(inline)* | 4 | <kbd>✓</kbd> &nbsp; **4 / 4** &nbsp; ![100%](https://img.shields.io/badge/-100%25-2ea043) |
| `urlpattern-hasregexpgroups.any.js` | `urlpattern-hasregexpgroups-tests.js` | 55 | <kbd>✓</kbd> &nbsp; **55 / 55** &nbsp; ![100%](https://img.shields.io/badge/-100%25-2ea043) |
| `urlpattern-compare.tentative.any.js` | `urlpattern-compare-test-data.json` | 25 | <kbd>✓</kbd> &nbsp; **25 / 25** &nbsp; ![100%](https://img.shields.io/badge/-100%25-2ea043) |
| `urlpattern-generate.tentative.any.js` | `urlpattern-generate-test-data.json` | 19 | <kbd>◐</kbd> &nbsp; opt-in via `WHATWG_URLPATTERN_RUN_TENTATIVE=1` |

> **Stdlib-only mode.** Under stdlib `re` without the `[regex]` extra, conformance on
> `urlpattern.any.js` is **364 / 366 (99.5%)**. The two outlier patterns — `[a&&b]`
> (intersection) and `[a--b]` (difference) from the JS `v`-flag — require Matthew
> Barnett's [`regex`](https://pypi.org/project/regex/) package; they're marked `xfail`
> with an install hint when it's absent. `pip install yarlpattern[regex]` activates them.

### API surface

| Surface | Spec status | Status |
|---|---|:---|
| `URLPattern(input)` &mdash; dict or string constructor | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `URLPattern(string, baseURL, options?)` &mdash; full signature | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `URLPattern(input, options?)` &mdash; two-arg overload | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `test(input, baseURL?)` | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `exec(input, baseURL?)` | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| 8 component properties (`protocol`, `hostname`, `pathname`, …) | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `hasRegExpGroups` property | Stable | <kbd>✓</kbd> &nbsp; Implemented |
| `URLPattern.compareComponent()` | Tentative | <kbd>✓</kbd> &nbsp; Implemented |
| `generate()` | Tentative | <kbd>◐</kbd> &nbsp; Tracked |

## How this differs from `aiohttp.web.UrlDispatcher`

The aio-libs ecosystem already ships a mature URL pattern matcher in
[`aiohttp.web.UrlDispatcher`](https://docs.aiohttp.org/en/stable/web_reference.html) — stable
since 2016, used by every aiohttp web service in production. The two tools have different
scopes and are best at different jobs.

| | `aiohttp.web.UrlDispatcher` | this library |
|---|---|---|
| Spec lineage | path-to-regexp (Flask / Werkzeug family) | [WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/) |
| Pattern syntax | `{name}` / `{name:regex}` | `:name` / `:name(regex)` / `*` / `{group}?` |
| Matches against | Path component only — protocol/host/port are determined by the running web server | All 8 URL components: protocol, hostname, port, pathname, search, hash, username, password |
| Operating mode | Dispatch-oriented: register routes with handlers; route an incoming request to them | Predicate-oriented: compile a pattern, ask `.test(url)` or `.exec(url)` |
| Standalone use | The class is technically usable outside aiohttp, but its API is shaped around request handling | The pattern *is* the API; no server context needed |
| Cross-language portability | Python-specific syntax | Same pattern string works in browsers, Deno, Bun, Cloudflare Workers |

If you're building an aiohttp web service, use `UrlDispatcher`. If you're matching URLs outside
a server context (crawler, classifier, analytics pipeline, CLI), or you need to constrain on
hostname/port/scheme alongside path, or you want patterns that match what browsers implement,
this library is the closer fit.

## How this differs from yarl

[yarl](https://github.com/aio-libs/yarl) is a URL parser/builder; this library is a URLPattern
matcher. They're complementary — we depend on yarl for actual URL parsing and IDNA hostname
encoding, and the API is shaped to feel familiar to yarl users (see [Quick start](#quick-start)).

There are a few places where this library is *stricter* than yarl, all because the WHATWG
URLPattern spec requires it. Quoting the relevant rules:

### 1. Case-preserving `%XX` passthrough

| | Behavior |
|---|---|
| yarl | Normalizes percent-encoded sequences to uppercase: `caf%c3%a9` → `caf%C3%A9` |
| this library | Preserves the user's case verbatim: `caf%c3%a9` stays `caf%c3%a9` |

The WHATWG URLPattern spec pins this down in the test suite — WPT cases 146 and 148 contrast
exactly on whether `caf%C3%A9` and `caf%c3%a9` round-trip as themselves. Pattern *equality*
depends on case being preserved; if we lowercased to match yarl's convention, patterns
constructed from URL strings with mixed case would silently change meaning.

### 2. Unpaired surrogates → U+FFFD before UTF-8 encoding

| | Behavior |
|---|---|
| yarl | Silently drops invalid sequences (`errors="ignore"`) |
| this library | Replaces with U+FFFD REPLACEMENT CHARACTER per WHATWG |

The [WHATWG URL standard §1.3](https://url.spec.whatwg.org/#percent-encoded-bytes) says
"to UTF-8 percent-encode a code point C using a percent-encode set, return the result of
running UTF-8 encode on C". UTF-8 encode requires a Unicode *scalar value*, and surrogate
halves (`D800–DFFF`) aren't scalar values — so the spec implicitly mandates U+FFFD
substitution. WPT case 157 (`{pathname: '\ud83d \udeb2'}` → `%EF%BF%BD%20%EF%BF%BD`)
locks this in.

### 3. Hostname truncation at `?` / `#` / `/` / `\`

| | Behavior |
|---|---|
| yarl | Rejects those characters in a host string outright |
| this library | Truncates at the first one, matching Chromium |

This follows [Chromium's `CanonicalizeHostnameInternal`](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/url_pattern/url_pattern_dummy_url_canon.cc),
which strips at the first `?`, `/`, `#` and treats `\` as `/` for special schemes (the
WHATWG URL "special authority" rule). The rationale is forgiveness: a hostname pattern
containing `/` was almost certainly a paste of a full URL, and respecting the prefix is
more useful than rejecting. WPT covers this with patterns like `{hostname: 'bad#hostname'}`
expecting compiled hostname `'bad'`.

### Where we agree with yarl (and the rest of the aio-libs family)

The encoding philosophy is the same: **strict UTF-8, no BOM handling, no autodetection,
Python `str` at the public boundary.**

- The WHATWG URL spec mandates UTF-8 for all newly percent-encoded bytes — no encoding
  alias machinery (the kind `webencodings` provides for HTML body parsing) applies. URLs
  are sequences of Unicode code points, not encoded bytes.
- A U+FEFF BOM in a URL string is just a regular non-ASCII code point; we percent-encode
  it as `%EF%BB%BF` exactly like yarl would. No "strip-the-BOM-at-the-start" logic exists
  in either library because URL parsing doesn't need it.
- aiohttp follows the same "be strict, plug in autodetection if you need it" pattern for
  HTTP body charsets via its `fallback_charset_resolver` hook. URL parsing has no analog
  because no autodetection is needed — UTF-8 is unconditional.

### Component-name mapping (yarl ↔ WHATWG)

5 of 8 URL component names differ between yarl and the WHATWG URLPattern spec. The names
we use match the spec (and the JS `URL` interface in browsers); knowing both makes the
muscle-memory transition shorter.

| yarl | this library | WHATWG / browser JS |
|---|---|---|
| `scheme` | `protocol` | `protocol` |
| `user` | `username` | `username` |
| `password` | `password` | `password` |
| `host` | `hostname` | `hostname` |
| `port` | `port` | `port` |
| `path` | `pathname` | `pathname` |
| `query` (a MultiDict) | `search` (a str) | `search` |
| `fragment` | `hash` | `hash` |

### yarl-style ergonomics

Two affordances specifically for yarl-shaped code:

**`yarl.URL` accepted as input — fast path.** `.test()` and `.exec()` accept a `yarl.URL` in
both the `input` and `base_url` positions. The matcher reads components directly off the
already-parsed URL object instead of re-stringing and re-parsing, so the typical
"`pat.test(request.url)`" call in an aiohttp handler is the fast path:

```python
pat = URLPattern("https://api.example.com/users/:id")
pat.test(request.url)                    # yarl.URL passed directly — no str() needed
pat.exec(yarl.URL("https://..."))        # parsed components consumed in place
```

**Per-component `with_*` methods.** Alongside the spec-shaped `with_(**kwargs)` deriver,
the library exposes one `with_<component>` method per URL component — same yarl convention,
WHATWG names:

```python
base = URLPattern({"hostname": "example.com"})
base.with_hostname("api.example.com")    # equivalent to base.with_(hostname="...")
base.with_pathname("/v2/:id")            # → URLPattern({hostname=example.com, pathname=/v2/:id})
```

Both methods exist; `with_(**kwargs)` is preferred when changing multiple components at once,
`with_<component>` when changing exactly one (and matches yarl's habit).

## Install

```bash
pip install yarlpattern            # stdlib re backend (99.5% WPT conformance)
pip install 'yarlpattern[regex]'   # full 100% conformance via Matthew Barnett's regex package
```

## Bring your own regex engine

The matcher's regex backend is pluggable behind a `@runtime_checkable Protocol`. Two adapters ship in-tree:

| Engine | Trigger | Conformance | Cost |
|---|---|:---:|---|
| stdlib `re` | always available; default fallback | 99.5% | no extra deps |
| [`regex`](https://pypi.org/project/regex/) (Matthew Barnett) | `pip install yarlpattern[regex]` &nbsp;·&nbsp; auto-detected | 100% | one extension wheel |

Selection priority: explicit `engine=` argument &rsaquo; `URLPATTERN_REGEX_ENGINE` env var
&rsaquo; auto-probe (prefers `regex` when importable, falls back to `re`).
See [`src/yarlpattern/_regex_engine/protocols.py`](src/yarlpattern/_regex_engine/protocols.py)
for the Protocol definitions; a future PyO3-backed engine slots in as one new adapter module.

## Quick start

```bash
uv sync --all-groups
uv run pytest                  # full test suite
just check                     # lint + types + tests (requires `just`)
```

```python
from yarlpattern import URLPattern

# Dict form, fully wildcarded except path
api = URLPattern({"pathname": "/api/v:version/users/:id(\\d+)"})
api.test({"pathname": "/api/v2/users/42"})              # True
api.exec({"pathname": "/api/v2/users/42"}).pathname     # {'input': '...', 'groups': {'version': '2', 'id': '42'}}

# String form with base URL
route = URLPattern("/posts/:slug", "https://blog.example.com")
route.test("https://blog.example.com/posts/hello")      # True

# Match a full URL against the constructed pattern
pat = URLPattern("https://*.shop.example/products/:sku")
pat.test("https://eu.shop.example/products/SKU-991")    # True
```

<!-- pypi-end -->

## Layout

- `src/yarlpattern/` — implementation modules (`_tokenizer`, `_parts`, `_regex`, `_constructor`, `_canonicalize`, `_url`, `_pattern`).
- `src/yarlpattern/_regex_engine/` — pluggable regex engine: `Protocol` + adapters for stdlib `re` and the `regex` package.
- `tests/test_wpt*.py` — parametrized from the WHATWG WPT data files. Other `tests/test_*.py` are unit-level.
- `reference/spec/` — local copy of the WHATWG URLPattern specification (fetched, not vendored in git).
- `reference/impls/` — shallow clones of reference implementations (Ada, Blink, rust-urlpattern, urlpattern-polyfill).
- `reference/wpt/` — shallow sparse clone of `web-platform-tests/wpt` (`urlpattern/` directory only).
- `scripts/fetch_references.sh` — repopulates `reference/` from scratch (it's gitignored).

## Why pure Python

A correct, readable, dependency-light implementation is the goal. The only required runtime
dependency is [`yarl`](https://github.com/aio-libs/yarl) for WHATWG URL parsing — itself a
pure-Python library with a tight dependency footprint. A Rust/C++ backend can be added later as
an optional extra without changing the API surface; the same `Protocol`-based engine seam used
today for the third-party `regex` package is what a PyO3 backend would plug into.
