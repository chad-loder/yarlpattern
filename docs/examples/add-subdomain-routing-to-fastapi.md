# Add subdomain routing to FastAPI

FastAPI's [maintainers have explicitly declined to add subdomain
routing inside the framework](https://github.com/fastapi/fastapi/issues/5282),
pointing users at nginx or Traefik instead. For multi-tenant SaaS
shapes (`acme.api.example.com` / `globex.api.example.com`) that
guidance forces every Python app to either run a reverse proxy *just*
for hostname routing, or roll its own.

## The awkward way

The typical Python-only workaround — recommended in every
"multi-tenant FastAPI" blog post — is a `Depends()` that parses
`request.url.hostname` by hand:

```python
from fastapi import FastAPI, Request, Depends, HTTPException

app = FastAPI()

def get_tenant(request: Request) -> str:
    host = request.url.hostname or ""
    parts = host.split(".")
    if len(parts) < 3 or parts[-2:] != ["example", "com"]:
        raise HTTPException(404)
    return parts[0]  # subdomain

@app.get("/billing")
async def billing(tenant: str = Depends(get_tenant)):
    return load_billing(tenant)
```

Three problems:

1. The hostname check is duplicated in every dependency that needs
   tenant context.
2. The tenant isn't a typed route parameter — it doesn't appear in
   the function signature or OpenAPI spec.
3. The `parts[-2:] != ["example", "com"]` check is precisely the kind
   of hostname-suffix logic that's *almost* but not quite right (try
   `evil.example.com.attacker.com`).

## With URLPattern

Use URLPattern inside the dependency. yarlpattern accepts a `yarl.URL`
directly, and FastAPI's `request.url` is yarl-compatible (Starlette's
`URL` exposes it):

```python
from fastapi import FastAPI, Request, Depends, HTTPException
from yarlpattern import URLPattern

app = FastAPI()

TENANT_HOST = URLPattern({"hostname": ":tenant.api.example.com"})

def get_tenant(request: Request) -> str:
    result = TENANT_HOST.exec(str(request.url))
    if result is None:
        raise HTTPException(404)
    return result.hostname["groups"]["tenant"]

@app.get("/billing")
async def billing(tenant: str = Depends(get_tenant)):
    return load_billing(tenant)
```

For routes that have additional URL-shape constraints — say, a
versioned API endpoint that only the admin tenant can hit — compose
two patterns:

```python
ADMIN_USERS = URLPattern({
    "hostname": "admin.api.example.com",
    "pathname": "/api/v:version(\\d+)/users/:id(\\d+)",
})

@app.get("/api/{ver}/users/{uid}")
async def admin_users(request: Request):
    result = ADMIN_USERS.exec(str(request.url))
    if result is None:
        raise HTTPException(404)
    g = result.pathname["groups"]
    return load_user(int(g["id"]), version=int(g["version"]))
```

FastAPI's path router still dispatches on path. URLPattern adds the
hostname constraint and the type-enforced path-parameter capture
(`:id(\\d+)` rejects `/api/v2/users/abc` at the pattern level).

## What you get for free

- **Hostname routing FastAPI doesn't ship.** No nginx, no Traefik, no
  framework patch. The pattern is the routing constraint.
- **Wildcard subdomains that work correctly.** `:tenant.api.example.com`
  consumes exactly one label and stops at the `.`, so
  `evil.example.com.attacker.com` is *not* an `evil` tenant — it
  doesn't match at all. Hand-rolled hostname-suffix checks routinely
  get this wrong.
- **One source of truth for the URL contract.** Pattern lives next to
  the route. Adding tenant context to a new endpoint is one
  `Depends(get_tenant)` away.
- **Type-enforced path params alongside hostname.** `:id(\\d+)` is in
  the pattern, not in a separate validator.
