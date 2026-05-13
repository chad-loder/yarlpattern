# What is URLPattern?

URLPattern is a web-platform primitive for matching URLs against a
declarative pattern syntax, returning structured named-group results
per URL component. It is a
[WHATWG Living Standard](https://urlpattern.spec.whatwg.org/)
[^1], implemented natively in every major browser engine and every
major server-side JavaScript runtime. **yarlpattern** is the Python
implementation.

If you're arriving from Flask, FastAPI, Starlette, Django, or any
regex-based URL routing, here's what to anchor on first.

## 1. Path-to-regexp lineage

URLPattern's pattern grammar is consciously derived from
[Blake Embrey's `path-to-regexp` library](https://github.com/pillarjs/path-to-regexp) —
the same syntax the Express.js, koa.js, and React Router communities have
been writing since the early 2010s.

The WICG explainer calls this a *paved cowpath*:

> Since there are popular libraries already used for matching we also
> propose to adopt the syntax from one as a popular cowpath. Specifically,
> we propose to adopt the syntax from path-to-regexp. It has 20 million
> weekly downloads on npm and is used in popular projects like expressjs
> and react-router.[^2]

The decision was deliberate. The spec's Acknowledgments section names
Blake Embrey directly:

> Special thanks to Blake Embrey and the other pillarjs/path-to-regexp
> contributors for building an excellent open source library that so many
> have found useful.[^1]

For a Python developer used to Flask's `<int:id>` or Django's
`<int:pk>` URL converters, the analogous URLPattern grammar is `:id(\d+)`
(`:name` for a named group, `(regex)` for a per-group constraint). The
top-level wildcards are `*` (any-segment) and `{group}?` (optional
group with attached delimiters).

## 2. Service-worker scoping was the originating problem

URLPattern was not designed primarily as a developer routing toolkit.
It exists because service-worker registration uses prefix-matching on
a single scope string, which breaks down when multiple teams share an
origin. The
[WICG explainer's motivating example](https://github.com/whatwg/urlpattern/blob/main/explainer.md)[^2]:

> Often … one team's area is nested under a part of the path controlled
> by a different team. The canonical example is a team responsible for
> the top level page and a team working on a product limited to any
> other path on the site; e.g. `foo.com/` vs `foo.com/product`.

That's where the proposal started. The
[W3C TAG design review](https://github.com/w3ctag/design-reviews/issues/417)
was originally filed in 2019 under the title *"Service Worker Scope
Pattern Matching explainer"* [^3]. The general-purpose JavaScript API
was the byproduct — and is now the dominant use case.

The point for a Python developer: URLPattern was designed by people
solving a *routing* problem on the *web platform*, not a *path-matching*
problem in a *web framework*. That's why its semantics span the whole
URL (protocol, hostname, port, pathname, search, hash) instead of just
the path.

## 3. Dual-purpose API: developer-facing *and* platform primitive

Every authoritative source emphasizes this duality. The
[WebKit standards position](https://github.com/WebKit/standards-positions/issues/61)
puts it concisely:

> URLPattern would support both web developer use in JS and native URL
> matching in other web APIs. For example, the initial use cases discuss
> using URLPattern for service worker scope matching.[^4]

Other web specs that reuse URLPattern as a primitive: the
ServiceWorker Static Routing API, web app manifest URL handlers, and
several emerging routing-adjacent proposals. For a library author,
that's the strongest possible signal that the surface is stable:
the web platform itself depends on URLPattern not changing semantics.

## 4. Component-wise matching, not whole-URL regex

URLPattern matches the eight URL components — protocol, username,
password, hostname, port, pathname, search, hash — **independently**,
each with its own pattern. This is a deliberate departure from regex-
on-the-whole-URL-string and is what makes URLPattern *URL-aware*
rather than just *string-aware*.

The Chrome for Developers writeup frames the win:

> URLPattern is an addition to the web platform that builds on the
> foundation created by these frameworks, with a goal to standardize
> a routing pattern syntax, including support for wildcards, named
> token groups, regular expression groups, and group modifiers.[^5]

Practically: hostname patterns understand `.` as a label separator
(so `:tenant.example.com` consumes exactly one label and `*.example.com`
behaves like the spec says); pathname patterns understand `/` as a
segment separator; search and hash patterns operate on the canonical
query and fragment forms. None of this is true of a raw regex over
the URL string.

## 5. Canonicalize-then-match semantics

Input URLs go through the [WHATWG URL Standard](https://url.spec.whatwg.org/)
parser and per-component canonicalization *before* matching. A pattern
is written against the *canonical* form of a URL, not the raw text.

This is the property most likely to surprise developers used to
substring or regex matching on URL strings. Two URLs the spec considers
equivalent — differing only in case, percent-encoding case, trailing
slashes, default ports — will always match the same pattern. In Python
terms: URLPattern's notion of equality is the same notion of equality
`yarl.URL` already uses, applied to *patterns* not just URLs.

The flip side: a pattern that hardcodes a non-canonical form
(e.g. `caf%c3%a9` with lowercase percent-encoded bytes) is preserved
verbatim, because matching a pattern against a URL that round-trips
through canonicalization must still succeed. The yarlpattern
[yarl comparison](../comparisons/yarl.md) covers the three places this
strictness shows up.

## Further reading

The three best concept-first introductions, ranked, for someone
learning URLPattern fresh:

1. **[URLPattern brings routing to the web platform](https://developer.chrome.com/docs/web-platform/urlpattern)**
   — Chrome for Developers (Jeff Posnick). Single best concept-first
   walkthrough of the grammar with worked examples. ~15 minutes.

2. **[URL Pattern API](https://developer.mozilla.org/en-US/docs/Web/API/URL_Pattern_API)**
   — MDN. Reference-grade, framed against Rails / Express / Next.js
   vocabulary, easy to scan.

3. **[URLPattern is now Baseline Newly available](https://web.dev/blog/baseline-urlpattern)**
   — web.dev, September 2025 (Jay Rungta). Short, current, and answers
   "why does this matter *now*."

The
[WHATWG URL Pattern Standard](https://urlpattern.spec.whatwg.org/)[^1]
is the authoritative source if you need to settle a corner-case
argument; the
[WICG explainer](https://github.com/whatwg/urlpattern/blob/main/explainer.md)[^2]
is shorter and more readable for the *why*.

---

[^1]: [The URL Pattern Standard](https://urlpattern.spec.whatwg.org/) — WHATWG Living Standard. Editors: Ben Kelly, Jeremy Roman, Shunya Shishido. Section: Acknowledgments.

[^2]: [URLPattern Explainer](https://github.com/whatwg/urlpattern/blob/main/explainer.md) — WICG / WHATWG, originally authored by Ben Kelly in 2019 as *"Service Worker Scope Pattern Matching Explainer."*

[^3]: [W3C TAG Design Review #417](https://github.com/w3ctag/design-reviews/issues/417) — filed
2019-09-04. The review's original title (*"Service Worker Scope Pattern Matching explainer"*) is
itself the strongest evidence for the origin-story claim.

[^4]: [WebKit standards-positions #61](https://github.com/WebKit/standards-positions/issues/61) — 2022-09-09, position: Support. Cites the dual-purpose framing explicitly.

[^5]: [URLPattern brings routing to the web platform](https://developer.chrome.com/docs/web-platform/urlpattern) — Chrome for Developers.
