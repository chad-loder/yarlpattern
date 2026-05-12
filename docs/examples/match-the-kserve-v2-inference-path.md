# Match the KServe `/v2/models` inference path

The [Open Inference Protocol V2](https://github.com/kserve/open-inference-protocol/blob/main/specification/protocol/inference_rest.md)
— used by KServe, NVIDIA Triton, Seldon Core, MLServer, AMD Inference
Server, and several others — defines its routing as path templates with
an optional version segment:

```text
v2/models/${MODEL_NAME}[/versions/${MODEL_VERSION}]/infer
v2/models/${MODEL_NAME}[/versions/${MODEL_VERSION}]/ready
v2/models/${MODEL_NAME}[/versions/${MODEL_VERSION}]/generate
```

The spec explicitly notes: *"path contents in `[]` are shown as
optional to allow implementations that don't support versioning or
for cases when the user does not want to specify a specific model
version."* Anything fronting one of these servers — a Python proxy
doing tracing, billing, per-tenant auth, or canary routing — has to
match this shape.

## The awkward way

Today, proxies typically register two routes per verb (one with
version, one without) or write per-endpoint regex:

```python
import re

_RE = re.compile(
    r"^/v2/models/(?P<name>[^/]+)"
    r"(?:/versions/(?P<version>[^/]+))?"
    r"/(?P<action>infer|ready|generate)$"
)

def parse(path: str):
    m = _RE.match(path)
    if not m:
        return None
    return m.groupdict()
```

Manual character-class management (`[^/]+`), manual optional-group
syntax (`(?:...)?`), no validation that `name` / `version` are
URL-safe.

## With URLPattern

```python
from yarlpattern import URLPattern

INFER = URLPattern({
    "pathname": "/v2/models/:name{/versions/:version}?/:action(infer|ready|generate)",
})

INFER.test("https://triton.example.com/v2/models/bert/infer")
# True

INFER.exec("https://triton.example.com/v2/models/bert/infer").pathname["groups"]
# {'name': 'bert', 'action': 'infer'}  (version absent)

INFER.exec("https://triton.example.com/v2/models/bert/versions/v3/infer").pathname["groups"]
# {'name': 'bert', 'version': 'v3', 'action': 'infer'}
```

The `{/versions/:version}?` group is *optional* — when the segment is
absent, the named group is simply not in the result. Same pattern
handles both URL shapes.

## Multi-backend routing with `compareComponent()`

If you're fronting *several* inference servers — Triton at one URL
prefix, KServe at another, TorchServe at a third — `compareComponent`
gives you spec-defined specificity ordering rather than insertion-order
fragility:

```python
ROUTES = [
    URLPattern({"pathname": "/v2/repository/models/:name/load"}),    # most specific
    URLPattern({"pathname": "/v2/repository/models/:name/unload"}),
    URLPattern({"pathname": "/v2/models/:name{/versions/:version}?/infer"}),
    URLPattern({"pathname": "/v2/models/:name{/versions/:version}?/:action"}),  # most general
]

# Sort by specificity per the spec — no manual "register specific first" discipline.
ROUTES.sort(key=cmp_to_key(lambda a, b: URLPattern.compareComponent("pathname", a, b)))
```

## What you get for free

- **Optional segment groups** — the most under-appreciated URLPattern
  feature, and the exact shape the inference protocol uses.
- **Regex-constrained action enum** — `:action(infer|ready|generate)`
  rejects `/v2/models/bert/explain` at the pattern level, before any
  handler dispatch.
- **`compareComponent()` for specificity** — replaces the
  "register specific patterns first" discipline every Python router
  documents. A spec-defined deterministic ordering means a sidecar can
  *compute* the right dispatch order from a route list it didn't write.
- **Translates verbatim from / to other ecosystems** — the same
  pattern string works in a Cloudflare Worker fronting the same
  inference cluster, or a Deno service mesh sidecar. URLPattern is the
  ecosystem-portable form of the routing table.
