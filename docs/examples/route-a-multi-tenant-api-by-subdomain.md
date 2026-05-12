# Route a multi-tenant API by subdomain

A common SaaS shape: every customer gets their own subdomain
(`acme.myapp.com`, `globex.myapp.com`, …) and every API call carries
its version in the path (`/api/v2/users/42`). One match needs to give
you the tenant name *and* the version *and* the resource tail.

## The problem

Multi-tenant routing is one of the most-requested features in modern
Python web frameworks:

- [aiohttp #1342](https://github.com/aio-libs/aiohttp/issues/1342) — "Route for subdomains"
- [FastAPI #5282](https://github.com/fastapi/fastapi/issues/5282) — "Does FastAPI support subdomains like Flask?"
- [FastAPI #445](https://github.com/tiangolo/fastapi/issues/445) — "subdomains / virtual host" (open since 2019)

Maintainers have generally declined to add it inside the framework,
recommending nginx / Traefik out-of-band. Every multi-tenant app
re-invents the host-parsing layer.

## The awkward way

```python
from urllib.parse import urlparse

def get_tenant_and_version(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host.endswith(".myapp.com"):
        return None
    tenant = host[: -len(".myapp.com")]
    if "." in tenant or not tenant:
        return None  # reject foo.bar.myapp.com / .myapp.com
    parts = parsed.path.split("/", 3)
    if len(parts) < 4 or parts[1] != "api" or not parts[2].startswith("v"):
        return None
    return tenant, parts[2][1:]
```

Imperative, fragile to URL normalization (case, percent-encoding, trailing
slash), and the tenant + version + resource-tail extraction is three
independent pieces of string surgery.

## With URLPattern

```python
from yarlpattern import URLPattern

API = URLPattern({
    "hostname": ":tenant.myapp.com",
    "pathname": "/api/v:version/*",
})

result = API.exec("https://acme.myapp.com/api/v2/users/42")
result.hostname["groups"]["tenant"]    # 'acme'
result.pathname["groups"]["version"]   # '2'
result.pathname["groups"]["0"]         # 'users/42'

API.test("https://foo.example.com/api/v2/users")    # False — wrong host
API.test("https://acme.myapp.com/api/users")        # False — no v-segment
API.test("https://foo.bar.myapp.com/api/v2/users")  # False — two-level subdomain rejects
```

`:tenant.myapp.com` is a hostname pattern: the `:tenant` named group
consumes exactly one label (it stops at `.`), so `foo.bar.myapp.com`
correctly fails to match. The `*` in the path captures everything after
`/api/v:version/` as a numbered wildcard group (key `"0"`).

## What you get for free

- **Cross-component matching** — one pattern object constrains hostname
  *and* path together, returning groups from both in one call.
- **Component-aware separators** — the spec defines `.` as the hostname
  segment separator, so `:tenant` stops at the first `.` automatically;
  no manual `host.split(".")` or `endswith(".myapp.com")` check.
- **Normalization is the spec's job, not yours** — case folding on the
  hostname, percent-encoding in pathname segments, empty-segment
  handling. WPT cases pin down the corner behaviors.
- **The same `URLPattern` works for `.test()` and `.exec()`** — no
  separate "do we route this?" / "extract from this" code paths to
  drift apart.
