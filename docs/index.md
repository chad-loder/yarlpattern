# yarlpattern

**WHATWG URLPattern for Python — 100% conformance** to the upstream
[WPT corpus](https://github.com/web-platform-tests/wpt/tree/master/urlpattern):
469 / 469 cases passing across all five test suites, the same files
Chromium, Safari, and Firefox validate against.

Pure Python on top of [`yarl`](https://github.com/aio-libs/yarl) —
immutable pattern objects, component properties named after their URL
counterparts, zero non-Python dependencies. The pattern *is* the API:
compile once, then ask `.test(url)` or `.exec(url)` from anywhere a
`yarl.URL` lives.

## Install

Install [`yarlpattern`](https://pypi.org/project/yarlpattern/) from PyPI:

```bash
pip install yarlpattern            # stdlib re backend (99.5% WPT conformance)
pip install 'yarlpattern[regex]'   # full 100% conformance via Matthew Barnett's regex package
```

The two outliers under stdlib `re` are JS-`v`-flag character-class
set operations (`[a&&b]`, `[a--b]`). The `[regex]` extra activates
them. yarlpattern detects the active engine automatically; nothing
else in your code changes.

## First match

```python
from yarlpattern import URLPattern

# Multi-tenant API: subdomain identifies the tenant, path captures
# the API version and the resource tail — all extracted in one call.
pat = URLPattern({
    "hostname": ":tenant.myapp.com",
    "pathname": "/api/v:version/*",
})

result = pat.exec("https://acme.myapp.com/api/v2/users/42")
result.hostname["groups"]["tenant"]    # 'acme'
result.pathname["groups"]["version"]   # '2'
result.pathname["groups"]["0"]         # 'users/42'
```

That's the URLPattern differentiator: matching *across* protocol,
hostname, port, path, and search at once, returning structured
named-group results per component. Flask / FastAPI / Starlette `:id`
routers only match the path; [hand-rolled regexes for URL allowlists
are routinely
error-prone](https://github.com/invoke-ai/InvokeAI/issues/7518)
because a regex source is a flat character sequence and a URL is not.

## Where to go next

- **[Overview](overview/index.md)** — what URLPattern is, where it
  came from (originally service-worker scope matching at Google),
  why its syntax inherits from `path-to-regexp` instead of inventing
  something new, and the cross-runtime adoption arc from incubation
  in 2019 to Baseline Newly Available in 2025.
- **[Examples](examples/index.md)** — 11 worked use cases including
  multi-tenant routing, KServe `/v2/models/:name{/versions/:v}?`
  inference paths, MCP resource URIs, GitHub-URL classification, and
  the rest.
- **[Reference](reference/api.md)** — auto-extracted API docs for
  every public name.
- **[Comparisons](comparisons/index.md)** — how yarlpattern fits next
  to `aiohttp.web.UrlDispatcher` and `yarl`.
- **[WPT Conformance](wpt-compliance.md)** — the auto-regenerated
  per-case evidence behind the 469 / 469 claim.
