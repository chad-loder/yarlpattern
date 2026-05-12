# Add subdomain routing to aiohttp

aiohttp doesn't natively support routing handlers by hostname. The
canonical workaround — recommended by aiohttp's maintainers in
[issue #1860](https://github.com/aio-libs/aiohttp/issues/1860) — is to
split your application into sub-apps:

```python
app.add_subapp("/", api, host="api.example.com")
app.add_subapp("/", ui,  host="example.com")
app.add_subapp("/admin", admin, host="example.com")
```

This forces three separate `Application` instances just to vary by
host, and there's no wildcard form: per-tenant `*.example.com` routing
requires hand-coded middleware that strips the host and dispatches.

## The awkward way (middleware)

```python
@web.middleware
async def tenant_middleware(request, handler):
    host = request.url.host or ""
    if not host.endswith(".example.com"):
        return web.HTTPNotFound()
    tenant = host[: -len(".example.com")]
    if "." in tenant or not tenant:
        return web.HTTPNotFound()
    request["tenant"] = tenant
    return await handler(request)
```

Hostname-shape validation lives separately from the routes themselves;
every handler reaches into `request["tenant"]` blindly.

## With URLPattern

URLPattern matches **a URL**, not "a request" — so the natural fit is
to use it inside the handler (or a middleware) on the `request.url`
yarl.URL object. yarlpattern accepts a `yarl.URL` directly, so there's
no `str()` round-trip:

```python
from yarlpattern import URLPattern

TENANT = URLPattern({
    "hostname": ":tenant.example.com",
    "pathname": "/*",
})

@web.middleware
async def tenant_middleware(request, handler):
    result = TENANT.exec(request.url)        # yarl.URL accepted directly
    if result is None:
        return web.HTTPNotFound()
    request["tenant"] = result.hostname["groups"]["tenant"]
    return await handler(request)
```

For per-route URL-shape constraints, attach a URLPattern to each
handler:

```python
USERS = URLPattern({"hostname": ":tenant.example.com",
                    "pathname": "/api/v:version/users/:id(\\d+)"})

async def get_user(request):
    result = USERS.exec(request.url)
    if result is None:
        return web.HTTPNotFound()
    groups = {**result.hostname["groups"], **result.pathname["groups"]}
    # groups = {'tenant': 'acme', 'version': '2', 'id': '42'}
    return web.json_response(load_user(**groups))

app.router.add_get("/api/{tail:.*}", get_user)  # broad aiohttp route
```

aiohttp's own router still dispatches the broad path; URLPattern
narrows on the full URL (hostname + version + id) inside the handler.

## What you get for free

- **Hostname pattern matching aiohttp doesn't have.** No sub-app
  acrobatics, no `add_domain()` config gymnastics.
- **`yarl.URL` as input — fast path.** `request.url` is already a
  `yarl.URL`; yarlpattern reads components directly from it without
  re-parsing. The typical `pat.test(request.url)` call is the fast
  path, not the slow one.
- **Wildcard subdomains work properly.** `:tenant.example.com`
  matches `acme.example.com` but *not* `foo.bar.example.com` (two
  labels) or `acme-example.com` (no boundary) — exactly what
  multi-tenant security requires. Hand-rolled `endswith()` checks
  routinely get this wrong.
- **One pattern, all components.** Hostname constraint *and* path
  constraint *and* per-segment regex (`:id(\\d+)`) in one declaration.
  The aiohttp router only constrains the path.
