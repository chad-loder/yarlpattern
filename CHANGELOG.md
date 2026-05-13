# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0](https://github.com/chad-loder/yarlpattern/releases/tag/v0.1.0) — 2026-05-12

First public release. WHATWG URLPattern for Python, with **100% conformance**
to the upstream [WPT urlpattern corpus](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
— 469 / 469 cases passing across all five test suites (the same files
Chromium, Safari, and Firefox validate against).

### Highlights

- **Component-wise matching across all eight URL components** — protocol,
  username, password, hostname, port, pathname, search, hash. Patterns can
  constrain any combination.
- **Path-to-regexp-derived syntax** (`:name`, `:name(regex)`, `*`,
  `{group}?`) — the same grammar Express.js, koa.js, and React Router users
  already know.
- **Pluggable regex engine** — stdlib `re` is the default (99.5%
  conformance). `pip install 'yarlpattern[regex]'` activates Matthew
  Barnett's [`regex`](https://pypi.org/project/regex/) package and closes
  the last 2 of 366 data-corpus cases (the JS `v`-flag character-class
  set-operation patterns).
- **yarl-shaped ergonomics** — `URLPattern.test()` / `URLPattern.exec()`
  accept a `yarl.URL` directly (no `str()` round-trip), per-component
  `with_*` derivers, component names matching the WHATWG spec /
  browser-side JS `URL` interface.

### Implementation

- Pure Python, no compiled wheels. One required runtime dep: `yarl>=1.20`.
- Sigstore-signed [PEP 740 attestations](https://peps.python.org/pep-0740/)
  with SLSA build-provenance predicates, generated and verified by
  [`hynek/build-and-inspect-python-package`](https://github.com/hynek/build-and-inspect-python-package)
  in CI.
- Tested against Python 3.12, 3.13, 3.14 on Linux / macOS / Windows.

### Documentation

- Full docs site at <https://chad-loder.github.io/yarlpattern> covering
  the spec lineage, 11 worked examples ("route a multi-tenant API by
  subdomain", "match the KServe `/v2/models` inference path", "replace
  MCP resource URI templates", …), the API reference, comparisons with
  `aiohttp.web.UrlDispatcher` and `yarl`, and the architecture
  explanation.
- Auto-regenerated [WPT Conformance report](https://chad-loder.github.io/yarlpattern/wpt-compliance/)
  pins the corpus SHA so the 469 / 469 number is reproducible at any
  future date.

<!-- python-semantic-release stamps releases above this line -->
