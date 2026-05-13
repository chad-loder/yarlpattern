# Comparisons

Where yarlpattern fits next to the routing tools Python developers
already know.

- [**vs. `aiohttp.web.UrlDispatcher`**](aiohttp.md) — yarlpattern is a
  predicate (the pattern *is* the API; no server context needed) and
  matches across all eight URL components, not just the path.
  `UrlDispatcher` is the right choice if you're building an aiohttp
  service; yarlpattern is the right choice outside one — or when you
  need hostname / port / scheme constraints alongside path.
- [**vs. yarl**](yarl.md) — yarl is a URL parser/builder; yarlpattern
  is a URLPattern matcher built on top of it. Covers the three places
  yarlpattern is *stricter* than yarl (case-preserving `%XX`,
  U+FFFD substitution, hostname truncation), the component-name
  mapping (`scheme`/`host`/`path` → `protocol`/`hostname`/`pathname`),
  and the yarl-style ergonomics (`yarl.URL` accepted directly,
  `with_*` derivers).

If you want to see yarlpattern *replace* a hand-rolled solution from
some other framework — FastAPI, Starlette, Django, MCP servers,
LiteLLM, KServe — those live under [Examples](../examples/index.md).
