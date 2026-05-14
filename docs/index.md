# yarlpattern

**yarlpattern** is a pure-Python implementation of the [WHATWG URLPattern standard](https://urlpattern.spec.whatwg.org/): one declarative object that matches a URL across every component at once — protocol, host, port, path, query, hash — and hands back structured named groups.

```python
from yarlpattern import URLPattern

# one pattern, matched across hostname + path together
api = URLPattern("https://:tenant.myapp.com/v:version/*")

m = api.exec("https://acme.myapp.com/v2/users/42")
m.hostname["groups"]["tenant"]    # 'acme'
m.pathname["groups"]["version"]   # '2'
m.pathname["groups"]["0"]         # 'users/42'
```

## What's a URL pattern?

A URL pattern is a single declarative string — the `:name` / `*` grammar from
[`path-to-regexp`](https://github.com/pillarjs/path-to-regexp), the same syntax
Express and React Router use — that matches a URL and captures named pieces of
it. Unlike a regex over the URL string, it matches on the **parsed** components,
so a `hostname` pattern can never accidentally match a path segment, and `.` and
`/` are treated as real separators. It's a predicate you can use anywhere —
standalone, in a data pipeline, or inside your existing router — not a framework.

→ New to URLPattern? [**What is URLPattern?**](overview/what-is-urlpattern.md) — the two-minute background.

URLs are parsed with [`yarl`](https://github.com/aio-libs/yarl) under the hood, so
IDNA hostnames, percent-encoding, default ports, and dot-segments are all handled
the WHATWG-correct way — but you never touch `yarl` yourself: pass plain URL
strings to `.test()` and `.exec()`.

## Examples

Each is abbreviated — follow the link for the full worked page.
(`from yarlpattern import URLPattern` throughout.)

### Extract a value that lives in many URL shapes

The same YouTube video ID hides in `/watch?v=`, `youtu.be/…`, `/embed/…`, and
`/shorts/…`. One pattern per shape, one loop:

```python
YT = [
    URLPattern({"hostname": "{*.}?youtube.com",
                "pathname": "/:kind(embed|shorts|v)/:id"}),
    URLPattern({"hostname": "{*.}?youtube.com",
                "pathname": "/watch", "search": "*v=:id([^&]+)(.*)"}),
    URLPattern({"hostname": "youtu.be", "pathname": "/:id"}),
]

def video_id(url):
    for pat in YT:
        if (m := pat.exec(url)):
            return (m.pathname["groups"] | m.search["groups"]).get("id")
```

Adding `music.youtube.com` is one more entry, not another branch.
→ [Full example](examples/extract-youtube-video-ids-from-any-url-form.md)

### Classify URLs in a pipeline

Ingesting a corpus of URLs and bucketing each one into a known shape — the
pattern table *is* the spec of what your pipeline recognizes:

```python
TABLE = [
    ("issue",  URLPattern({"hostname": "github.com",
               "pathname": "/:owner/:repo/issues/:num(\\d+)"})),
    ("commit", URLPattern({"hostname": "github.com",
               "pathname": "/:owner/:repo/commit/:sha([0-9a-f]+)"})),
    # … one entry per shape you care about
]

def classify(url):
    for kind, pat in TABLE:
        if (m := pat.exec(url)):
            return kind, m.pathname["groups"]
    return None
```

→ [Full example](examples/classify-github-urls-in-markdown.md)

### Validate inbound webhooks by shape

`.test()` is the whole validator — scheme, host, and an integer-only version in
one object, checked before any payload work:

```python
STRIPE = URLPattern({
    "protocol": "https",
    "hostname": "hooks.acme.example",
    "pathname": "/stripe/v:version(\\d+)/events",
})

STRIPE.test("https://hooks.acme.example/stripe/v1/events")  # True
STRIPE.test("http://hooks.acme.example/stripe/v1/events")   # False — not https
STRIPE.test("https://hooks.acme.example/stripe/vX/events")  # False — bad version
```

→ [Full example](examples/validate-inbound-webhooks-by-url-shape.md)

### A hostname allowlist that can't be fooled

A `hostname` pattern matches the *parsed* host, so it can't be tricked by the
trusted name appearing in a path or buried inside a longer hostname — the classic
substring/regex allowlist bug:

```python
TRUSTED = URLPattern({"protocol": "https",
                      "hostname": "{:sub.}*private.example"})

TRUSTED.test("https://eu.private.example/data")            # True
TRUSTED.test("https://private.example.evil.example/data")  # False
TRUSTED.test("https://evil.example/private.example/data")  # False
```

→ [Full example](examples/avoid-regex-hostname-allowlist-vulns.md)

→ [**All examples**](examples/index.md)

## Install

```bash
pip install yarlpattern
```

[`yarlpattern` on PyPI](https://pypi.org/project/yarlpattern/) — pure Python, one runtime dependency (`yarl`), Python 3.12+.

## Conformance

yarlpattern passes **469 / 469** cases of the upstream
[WHATWG URLPattern Web Platform Tests](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
— the same suite Chromium, Safari, and Firefox validate against — alongside 130
of its own unit tests. The corpus is SHA-pinned, so the number is reproducible.

[Full per-case report](wpt-compliance.md) ·
[Documented spec deviations](https://github.com/chad-loder/yarlpattern/blob/main/SPEC_DEVIATIONS.md)

The optional `regex` engine — `pip install 'yarlpattern[regex]'` — adds the two
JavaScript `v`-flag set-operation patterns (`[a&&b]` / `[a--b]`); without it,
conformance on the main suite is 364 / 366.

## Where to go next

- **[Overview](overview/index.md)** — what URLPattern is, where it came from
  (originally service-worker scope matching at Google), and the cross-runtime
  adoption arc from 2019 incubation to Baseline Newly available in 2025.
- **[Reference](reference/api.md)** — auto-extracted API docs for every public name.
- **[Comparisons](comparisons/index.md)** — how yarlpattern sits next to
  `aiohttp.web.UrlDispatcher` and `yarl`.
