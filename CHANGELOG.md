# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/chad-loder/yarlpattern/releases/tag/v0.2.0) — 2026-05-13

v0.2 closes the remaining tentative-spec gap, adds a parallel polyfill
conformance vector, and brings the public API into PEP-8 alignment without
giving up literal-text portability with the WHATWG spec.

### Highlights

- **`URLPattern.generate(component, groups)` implemented.** The tentative-spec
  method that reverses `exec()` — given named-group values, emit the
  canonical-form URL component string that would have matched. **19 / 19**
  upstream WPT cases for `urlpattern-generate-test-data.json` pass.
  Single-pass walk over the per-component parsed part-list with lazy validator
  compilation; **zero overhead on the `test()` / `exec()` hot path**.
- **PEP-8 snake_case primary, camelCase aliases preserved.** The canonical
  spellings are now `URLPattern.compare_component(...)` and
  `pat.has_regexp_groups`; the WHATWG IDL forms (`compareComponent`,
  `hasRegExpGroups`) are kept as straight aliases so code ported verbatim
  from the spec / browser JS / Deno / Bun / Cloudflare-Workers reads
  identically. Both spellings dispatch to the same descriptor — `is`-identity
  holds. **No breaking change.**
- **WICG polyfill conformance corpus vendored** alongside WPT.
  `scripts/fetch_polyfill_corpus.sh` mirrors the WPT fetch script with the
  same security-hardened sparse-checkout pattern. 328 polyfill cases pass;
  8 documented polyfill-vs-WPT divergences are explicitly skipped (the
  polyfill expects a constructor error where WPT requires acceptance with
  truncation — yarlpattern follows WPT).
- **`SPEC_DEVIATIONS.md`** — explicit documentation of where yarlpattern
  delegates to other libraries (`yarl` for URL parsing, `idna` for UTS46
  hostname canonicalisation, `re` / `regex` for component-level regex
  compilation) and where the library is *stricter* than yarl per the spec
  (case-preserving `%XX`, U+FFFD substitution for unpaired surrogates,
  hostname-pattern truncation at URL-structural delimiters, strict port
  parsing rejecting `"8080xyz"`).
- **Hand-coded MDN + WHATWG spec example tests** — `tests/test_mdn_examples.py`
  and `tests/test_spec_examples.py` lock in the pedagogical examples from
  developer.mozilla.org and the spec prose so doc-page-example regressions
  surface as named test failures.
- **Self-benchmark suite under `benchmarks/`** — yarlpattern-only across the
  four hot paths (construction, `test()`, `exec()`, and the `yarl.URL`
  fast path), gated behind the `bench` PEP-735 dependency-group. Invoke
  with `just bench` / `just bench-save`. Default `pytest` does not pick the
  benchmarks up.
- **New security-shaped example.** `docs/examples/avoid-regex-hostname-allowlist-vulns.md`
  walks through the canonical regex-URL-allowlist credential-leak class of
  bug (path-segment fallthrough, subdomain shadowing) using the seed
  [`invoke-ai/InvokeAI#7518`](https://github.com/invoke-ai/InvokeAI/issues/7518)
  as the worked example, with URLPattern as the component-aware fix.

### Conformance

- **WPT corpus: 469 / 469 across all five suites** (was: 450 passing + 19
  generate cases skipped behind `WHATWG_URLPATTERN_RUN_TENTATIVE=1`).
- **WICG polyfill corpus: 328 / 336** (8 documented divergences).
- **Total in-repo test count: 951 passing, 8 skipped** (was 580 in v0.1.0).

### Documentation

- README restructured: conformance section is now the first H2 after the
  hero code, with a single consolidated test-suite table and a new
  *"What we get right that's easy to miss"* subsection promoting the
  per-component canonicalisation rules.
- `docs/wpt-compliance.md` regenerated with the badge row dropped (the
  shields.io badges 404'd when labels contained embedded hyphens; the
  Summary table directly below them already carried the same per-suite
  counts).
- Sly home-page link to the regex-allowlist vuln example for readers
  arriving from security-curious contexts.

### Removed

- The `WHATWG_URLPATTERN_RUN_TENTATIVE=1` env-var gate on the generate
  test suite is gone; the 19 cases now run unconditionally.

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
