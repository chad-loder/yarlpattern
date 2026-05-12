# yarlpattern vs. `aiohttp.web.UrlDispatcher`

The aio-libs ecosystem already ships a mature URL pattern matcher in
[`aiohttp.web.UrlDispatcher`](https://docs.aiohttp.org/en/stable/web_reference.html) — stable
since 2016, used by every aiohttp web service in production. The two tools have different
scopes and are best at different jobs.

|  | `aiohttp.web.UrlDispatcher` | yarlpattern |
|---|---|---|
| Spec lineage | path-to-regexp (Flask / Werkzeug family) | [WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/) |
| Pattern syntax | `{name}` / `{name:regex}` | `:name` / `:name(regex)` / `*` / `{group}?` |
| Matches against | Path component only — protocol / host / port are determined by the running web server | All eight URL components: protocol, hostname, port, pathname, search, hash, username, password |
| Operating mode | Dispatch-oriented: register routes with handlers; route an incoming request to them | Predicate-oriented: compile a pattern, ask `.test(url)` or `.exec(url)` |
| Standalone use | The class is technically usable outside aiohttp, but its API is shaped around request handling | The pattern *is* the API; no server context needed |
| Cross-language portability | Python-specific syntax | Same pattern string works in browsers, Deno, Bun, Cloudflare Workers |

If you're building an aiohttp web service, use `UrlDispatcher`. If you're matching URLs outside
a server context (crawler, classifier, analytics pipeline, CLI), or you need to constrain on
hostname / port / scheme alongside path, or you want patterns that match what browsers implement,
yarlpattern is the closer fit.
