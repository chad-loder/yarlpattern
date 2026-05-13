# yarlpattern

[![WPT conformance](https://img.shields.io/badge/WPT%20data%20corpus-100%25%20(366%2F366)-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![WPT auxiliary suites](https://img.shields.io/badge/auxiliary%20suites-103%2F103-2ea043?labelColor=24292f)](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
[![Stable spec API](https://img.shields.io/badge/stable%20API-implemented-2ea043?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
[![Tentative spec API](https://img.shields.io/badge/tentative%20API-implemented-2ea043?labelColor=24292f)](https://urlpattern.spec.whatwg.org/)
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

## Conformance

**469 / 469** upstream Web Platform Tests pass (100%) across every WHATWG URLPattern test suite
— the same files Chromium, Safari, Firefox, Ada, and rust-urlpattern validate against. The
WPT corpus is SHA-pinned by [`scripts/fetch_references.sh`](scripts/fetch_references.sh)
to commit [`dd54691`](https://github.com/web-platform-tests/wpt/commit/dd54691426c23a08c6f4a0972b2c40965307e5ce)
(2026-05-11) so the pass count is reproducible at any future date.

| Suite | Source | Cases | Status |
|---|---|---:|:---:|
| `urlpattern.any.js` | WPT &nbsp;·&nbsp; `urlpatterntestdata.json` | 366 | <kbd>✓</kbd> &nbsp; 366 / 366 |
| `urlpattern-constructor.any.js` | WPT *(inline)* | 4 | <kbd>✓</kbd> &nbsp; 4 / 4 |
| `urlpattern-hasregexpgroups.any.js` | WPT &nbsp;·&nbsp; `urlpattern-hasregexpgroups-tests.js` | 55 | <kbd>✓</kbd> &nbsp; 55 / 55 |
| `urlpattern-compare.tentative.any.js` | WPT &nbsp;·&nbsp; `urlpattern-compare-test-data.json` | 25 | <kbd>✓</kbd> &nbsp; 25 / 25 |
| `urlpattern-generate.tentative.any.js` | WPT &nbsp;·&nbsp; `urlpattern-generate-test-data.json` | 19 | <kbd>✓</kbd> &nbsp; 19 / 19 |
| yarlpattern unit tests | this repo &nbsp;·&nbsp; tokenizer / parser / parts / regex / engine / pattern | 130 | <kbd>✓</kbd> &nbsp; 130 / 130 |
| **Total** | | **599** | <kbd>✓</kbd> &nbsp; **599 / 599** |

→ [**Full per-case conformance report**](docs/wpt-compliance.md) (regenerate via `just compliance-report`)
&nbsp;·&nbsp; [**Documented deviations and stricter-than-yarl rules**](SPEC_DEVIATIONS.md)

### What we get right that's easy to miss

The 100% number is the headline. Equally load-bearing — and easy to skip past — are the
per-component canonicalisation rules the WHATWG URLPattern spec quietly requires. yarlpattern
enforces all of them; a stdlib-only port that goes through `urllib.parse` cannot:

- **WHATWG URL parsing end-to-end** via [`yarl`](https://github.com/aio-libs/yarl), not
  `urllib.parse` (which is not WHATWG-conformant).
- **IDNA2008 / UTS46 hostname canonicalization** via the third-party
  [`idna`](https://pypi.org/project/idna/) package, not Python's stdlib `idna` codec
  (which is IDNA2003 and not spec-compliant for modern IDN labels).
- **Strict port parsing** — `"8080xyz"` is rejected as the WHATWG URL parser's port-state
  requires; webhook-validation patterns that constrain on exact ports stay robust against
  junk suffixes.
- **Case-preserving `%XX` passthrough** in pattern literals — `caf%c3%a9` round-trips as
  itself, where yarl would normalise to uppercase (WPT cases 146 / 148 pin this).
- **U+FFFD substitution for unpaired surrogates** before UTF-8 percent-encoding, where yarl
  silently drops them (WPT case 157).
- **Hostname-pattern truncation at `?` / `#` / `/` / `\`**, matching browser engine
  behaviour for hostnames that were pasted from full URLs.

> **Stdlib-only mode.** Under stdlib `re` without the `[regex]` extra, conformance on
> `urlpattern.any.js` is **364 / 366 (99.5%)**. The two outlier patterns — `[a&&b]`
> (intersection) and `[a--b]` (difference) from the JS `v`-flag — require Matthew
> Barnett's [`regex`](https://pypi.org/project/regex/) package; they're marked `xfail`
> with an install hint when it's absent. `pip install yarlpattern[regex]` activates them.

### API surface

Every stable and tentative method in the WHATWG URLPattern IDL is implemented:
`URLPattern(input | string, baseURL?, options?)`, `test`, `exec`, all eight component
properties, `hasRegExpGroups`, `URLPattern.compareComponent`, and the tentative
`generate(component, groups)`. See [SPEC_DEVIATIONS.md](SPEC_DEVIATIONS.md) for the
intentional Python-flavour choices (camelCase method names, the additional `with_*`
derivers, escape-helper exposure).

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

Where the WHATWG URLPattern spec is stricter than yarl, yarlpattern enforces the spec — see the
[Conformance](#conformance) section above and [SPEC_DEVIATIONS.md](SPEC_DEVIATIONS.md).

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
pip install yarlpattern            # stdlib re backend
pip install 'yarlpattern[regex]'   # full 100% conformance — see Conformance § above
```

## Bring your own regex engine

The matcher's regex backend is pluggable behind a `@runtime_checkable Protocol`. Two adapters
ship in-tree — stdlib `re` (always available; default fallback) and
[`regex`](https://pypi.org/project/regex/) (auto-detected when `yarlpattern[regex]` is
installed; closes the `[a&&b]` / `[a--b]` gap).

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

## Architecture

Layout, the matching pipeline, the engine seam used by the optional `regex` package, and the
deliberate-divergence notes (yarl fast path, `with_*` derivers, the three WHATWG-strictness
rules) live on the docs site.

→ [Architecture](https://chad-loder.github.io/yarlpattern/explanation/architecture/)
