# yarlpattern

[![PyPI](https://img.shields.io/pypi/v/yarlpattern.svg?labelColor=24292f&color=3775a9)](https://pypi.org/project/yarlpattern/)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776ab?labelColor=24292f&logo=python&logoColor=white)](https://www.python.org/)

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

→ New to URLPattern? [**What is URLPattern?**](https://chad-loder.github.io/yarlpattern/overview/what-is-urlpattern/) — the two-minute background.

URLs are parsed with [`yarl`](https://github.com/aio-libs/yarl) under the hood, so
IDNA hostnames, percent-encoding, default ports, and dot-segments are all handled
the WHATWG-correct way — but you never touch `yarl` yourself: pass plain URL
strings to `.test()` and `.exec()`.

## Examples

Each is abbreviated — follow the link for the full worked version.
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
→ [Full example](https://chad-loder.github.io/yarlpattern/examples/extract-youtube-video-ids-from-any-url-form/)

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

→ [Full example](https://chad-loder.github.io/yarlpattern/examples/classify-github-urls-in-markdown/)

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

→ [Full example](https://chad-loder.github.io/yarlpattern/examples/validate-inbound-webhooks-by-url-shape/)

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

→ [Full example](https://chad-loder.github.io/yarlpattern/examples/avoid-regex-hostname-allowlist-vulns/)

## Install

```bash
pip install yarlpattern
```

Pure Python, one runtime dependency (`yarl`), Python 3.12+.

## Conformance

yarlpattern passes **469 / 469** cases of the upstream
[WHATWG URLPattern Web Platform Tests](https://github.com/web-platform-tests/wpt/tree/master/urlpattern)
— the same suite Chromium, Safari, and Firefox validate against — alongside 130
of its own unit tests. The corpus is SHA-pinned, so the number is reproducible.

[**Full per-case report**](docs/wpt-compliance.md) ·
[**Documented spec deviations**](SPEC_DEVIATIONS.md)

The optional `regex` engine — `pip install 'yarlpattern[regex]'` — adds the two
JavaScript `v`-flag set-operation patterns (`[a&&b]` / `[a--b]`); without it,
conformance on the main suite is 364 / 366.

<!-- pypi-end -->

## See also

- [How this differs from `aiohttp.web.UrlDispatcher`](https://chad-loder.github.io/yarlpattern/comparisons/aiohttp/) — it's a predicate, not a router
- [How this differs from `yarl`](https://chad-loder.github.io/yarlpattern/comparisons/yarl/)
- [Architecture](https://chad-loder.github.io/yarlpattern/explanation/architecture/) · [All examples](https://chad-loder.github.io/yarlpattern/examples/) · [Full documentation](https://chad-loder.github.io/yarlpattern/)
