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

- [**What is URLPattern?**](what-is-urlpattern.md) — origin story, the
  five concepts (path-to-regexp lineage, service-worker scoping
  origin, dual-purpose API, component-wise matching, canonicalize-
  then-match semantics), and a ranked top-3 of intros to read first.
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
