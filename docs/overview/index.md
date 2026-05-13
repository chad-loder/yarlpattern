# Overview

The 30-second story:

- **yarlpattern** is the Python implementation of the
  [WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/).
- URLPattern matches *every* URL component (protocol, hostname, port,
  path, search, hash) declaratively, with named groups per component.
- It's the same standard Chromium, Safari, Firefox, Deno, Bun,
  Node.js, and Cloudflare Workers implement — yarlpattern brings it
  to Python with **100% conformance** to the upstream WPT corpus
  (469 / 469 cases across 5 suites).

## What's in this section

- [**What is URLPattern?**](what-is-urlpattern.md) — origin story
  (URLPattern began as a service-worker scoping mechanism, not a
  developer routing toolkit), why the syntax mirrors `path-to-regexp`
  rather than the OpenAPI `{name}` style, what *component-wise*
  matching means in practice, and the canonicalize-then-match
  semantics that surprise everyone porting from substring matching.
  Ends with three recommended intros to read before any Python.
- [**Ecosystem adoption**](ecosystem-adoption.md) — chronological
  timeline from 2020 incubation to Baseline Newly Available status
  in September 2025, plus current snapshot tables for browsers,
  server runtimes, and frameworks.

## Want to skip to the code?

- [**Examples**](../examples/index.md) — 11 worked examples
  ("classify GitHub URLs in markdown", "route a multi-tenant API by
  subdomain", "match the KServe inference path", …) each verified
  against the test suite.
- [**API reference**](../reference/api.md) — auto-extracted from the
  source's docstrings.
