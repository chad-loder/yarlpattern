# yarlpattern

[![WPT conformance](https://img.shields.io/badge/WPT%20data%20corpus-100%25%20(366%2F366)-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![WPT auxiliary suites](https://img.shields.io/badge/auxiliary%20suites-84%2F84-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![Stable spec API](https://img.shields.io/badge/stable%20API-implemented-2ea043?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
[![Tentative spec API](https://img.shields.io/badge/tentative%20API-tracked-1f6feb?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776ab?labelColor=24292f&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-6e7681?labelColor=24292f)](LICENSE)

**WHATWG URLPattern for Python — 100% conformance** to the upstream
[WPT corpus](https://github.com/web-platform-tests/wpt/tree/master/urlpattern):
**469 / 469** cases passing across all five test suites, the same files Chromium,
Safari, and Firefox validate against.

Pure Python on top of [`yarl`](https://github.com/aio-libs/yarl) — immutable
pattern objects, component properties named after their URL counterparts, zero
non-Python dependencies. The pattern *is* the API: compile once, then ask
`.test(url)` or `.exec(url)` from anywhere a `yarl.URL` lives.

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

[`aiohttp.web.UrlDispatcher`](https://docs.aiohttp.org/en/stable/web_reference.html) is a
mature path-router shaped around web-request dispatch. yarlpattern is a *predicate*: it
matches across all eight URL components (not just the path), works standalone (no server
context required), and uses the same WHATWG pattern syntax browsers, Deno, Bun, and
Cloudflare Workers all implement.

Use `UrlDispatcher` if you're building an aiohttp service. Use yarlpattern if you're matching
URLs outside a server context, need to constrain on hostname / port / scheme alongside path,
or want patterns that match what browsers do.

→ [Full comparison](https://chad-loder.github.io/yarlpattern/comparisons/aiohttp/)

## How this differs from yarl

[yarl](https://github.com/aio-libs/yarl) is a URL parser / builder; yarlpattern is a URLPattern
matcher. They're complementary — yarlpattern depends on yarl for URL parsing and IDNA hostname
encoding, accepts `yarl.URL` directly in `.test(...)` and `.exec(...)` calls (no `str()`
round-trip), and uses WHATWG component names (`protocol` / `hostname` / `pathname` / `search` /
`hash`) rather than yarl's (`scheme` / `host` / `path` / `query` / `fragment`).

Three places where yarlpattern is *stricter* than yarl, all because the WHATWG URLPattern spec
requires it:

- Percent-encoded `%XX` case is preserved verbatim (yarl normalizes to uppercase).
- Unpaired surrogates substitute U+FFFD before UTF-8 encoding (yarl drops them).
- Hostname patterns truncate at `?` / `#` / `/` / `\` (yarl rejects).

Component-name mapping for muscle-memory porting:

| yarl | yarlpattern | WHATWG / browser JS |
|---|---|---|
| `scheme` | `protocol` | `protocol` |
| `user` | `username` | `username` |
| `host` | `hostname` | `hostname` |
| `path` | `pathname` | `pathname` |
| `query` (MultiDict) | `search` (str) | `search` |
| `fragment` | `hash` | `hash` |

→ [Full comparison](https://chad-loder.github.io/yarlpattern/comparisons/yarl/), including the
WPT cases that pin down each strictness rule, the `with_*` ergonomics, and the encoding
philosophy yarlpattern shares with the rest of aio-libs.

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
