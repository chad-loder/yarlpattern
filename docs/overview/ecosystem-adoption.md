# Ecosystem adoption

URLPattern began as a Chromium proposal in 2019 and has, over roughly
six years, become a cross-runtime web standard supported by every
major browser engine and every major server-side JavaScript runtime.
This page is the citation surface for the claim that yarlpattern is
implementing a stable, broadly-adopted standard — not a Chromium
experiment.

## Timeline

| Year | Milestone | Source |
|---|---|---|
| 2019 | Proposal filed at WICG by Ben Kelly (Google); W3C TAG review opened; TPAC 2019 discussions | [TAG #417](https://github.com/w3ctag/design-reviews/issues/417) |
| 2020 | TPAC 2020 follow-up; reference C++ implementation (`liburlpattern`) lands in Chromium | [202012 incubation update](https://github.com/whatwg/urlpattern/blob/main/202012-update.md) |
| 2021-09 | **Deno 1.14** ships URLPattern (unstable) — first server runtime; stabilized in 1.15 | [Deno 1.14 release notes](https://deno.com/blog/v1.14) |
| 2021-10 | **Chrome 95** ships URLPattern enabled by default — first stable browser | [New in Chrome 95](https://developer.chrome.com/blog/new-in-chrome-95) |
| 2022-03 | **Cloudflare Workers** ships URLPattern as part of its web-standards surface | [Cloudflare standards-compliant Workers API](https://blog.cloudflare.com/standards-compliant-workers-api/) |
| 2023-10 | **URLPattern graduates from WICG to WHATWG** as a Living Standard | [The URL Pattern Standard (WHATWG blog)](https://blog.whatwg.org/url-pattern-standard) |
| 2025-01 | **Bun 1.2** implements URLPattern (passes 408 WPT cases) | [Bun 1.2 release notes](https://bun.sh/blog/bun-v1.2) |
| 2025-02 | **Interop 2025** picks URLPattern as a focus area, committing all four engine vendors to convergence | [Announcing Interop 2025 (WebKit)](https://webkit.org/blog/16458/announcing-interop-2025/) |
| 2025-02 | **Safari Technology Preview 213** implements URLPattern | [STP 213 release notes](https://webkit.org/blog/16461/release-notes-for-safari-technology-preview-213/) |
| 2025-03 | **Node.js 23.8.0** ships URLPattern (implementation contributed by Cloudflare, atop Ada URL) | [Cloudflare announcement](https://blog.cloudflare.com/improving-web-standards-urlpattern/) |
| 2025-05 | **Node.js 24.0.0** exposes URLPattern globally | [Node 24 release notes](https://nodejs.org/en/blog/release/v24.0.0) |
| 2025-08 | **Firefox 142** enables URLPattern by default | [Firefox 142 release notes](https://www.firefox.com/en-US/firefox/142.0/releasenotes/) |
| 2025-09 | **Safari 26** ships URLPattern in stable; URLPattern reaches **Baseline Newly Available** | [URLPattern is now Baseline Newly available (web.dev)](https://web.dev/blog/baseline-urlpattern) |
| 2026-02 | Interop 2025 retrospective cites URLPattern as a flagship cross-browser convergence win | [Interop 2025: A year of convergence (WebKit)](https://webkit.org/blog/17808/interop-2025-review/) |

## Snapshot: where URLPattern is today

**Browsers** — Baseline Newly Available since September 2025:

| Engine | Ships URLPattern | Default since |
|---|---|---|
| Blink (Chrome / Edge / Opera / Brave / …) | Yes | Chrome 95, October 2021 |
| Gecko (Firefox) | Yes | Firefox 142, August 2025 |
| WebKit (Safari) | Yes | Safari 26, September 2025 |

**Server runtimes** — all natively, no polyfill:

| Runtime | Ships URLPattern | Default since |
|---|---|---|
| Deno | Yes | 1.14 (Sep 2021), stable since 1.15 |
| Cloudflare Workers | Yes | March 2022 |
| Bun | Yes | 1.2 (Jan 2025) |
| Node.js | Yes | 23.8.0 (Mar 2025); global in 24.0.0 (May 2025) |

**Standards governance:**

- WHATWG Living Standard since October 2023 — same governance class
  as URL, Fetch, DOM, and HTML[^1]
- Interop 2025 focus area, all four engine vendors committed and
  shipped[^2]
- Reference Rust implementation
  ([denoland/rust-urlpattern](https://github.com/denoland/rust-urlpattern)),
  reference C++ implementations
  ([liburlpattern](https://github.com/whatwg/urlpattern/blob/main/202012-update.md#liburlpattern)
  in Chromium and [Ada URL](https://github.com/ada-url/ada) used by
  Node.js and Cloudflare).

## Frameworks built around URLPattern

The URLPattern adoption arc is closing the loop: frameworks that used
to ship their own routers are now exposing URLPattern as the routing
primitive itself.

- **[Hono](https://hono.dev/docs/concepts/routers)** ships
  `PatternRouter`, a sub-15 KB router built on URLPattern, runnable
  unchanged on Workers, Deno, Bun, Node, and Lambda.
- **Deno standard library** —
  [`@std/http/unstable-route`](https://docs.deno.com/runtime/reference/std/http/)
  builds `route()` directly on URLPattern. The matcher in
  `unstable_route.ts` is about 15 lines wrapping `pattern.exec()`.
- **[Next.js Edge Runtime](https://nextjs.org/docs/api-reference/edge-runtime)**
  and **[Netlify Functions](https://docs.netlify.com/functions/overview/)**
  are cited by the WHATWG blog post as URLPattern-adopting runtimes.[^1]
- **[Servo](https://github.com/servo/servo/pull/36144)** has an open
  implementation PR — once landed, that's a fifth engine.

## What this means for yarlpattern

URLPattern is no longer a Chromium proposal — it is a multi-vendor,
multi-runtime web standard with a complete shipping matrix and a Living
Standard home. The Python implementation:

- targets a **stable** surface (the API is unlikely to break under us
  — too many shipping runtimes depend on it),
- has an **authoritative conformance corpus** (the WPT urlpattern test
  suite, the same files Chromium, Safari, Firefox, Deno, Bun, Node,
  Workers, and Ada validate against),
- composes with the **ecosystem-portable form** of routing tables —
  the same pattern string runs in yarlpattern, Chrome, Safari, Deno,
  and a Cloudflare Worker fronting your service.

For a Python team, that's the case for adopting yarlpattern over
hand-rolled `urlparse` + regex laddering: you're standardizing on the
same routing primitive your browser, your Edge worker, and your
LLM-stack runtime are already standardizing on.

---

[^1]: [The URL Pattern Standard](https://blog.whatwg.org/url-pattern-standard) — WHATWG blog post announcing graduation from WICG, October 25, 2023.

[^2]: [Announcing Interop 2025](https://webkit.org/blog/16458/announcing-interop-2025/) (WebKit) and
[Interop 2025: another year of web platform improvements](https://web.dev/blog/interop-2025) (web.dev)
— multi-vendor commitment to URLPattern convergence.
