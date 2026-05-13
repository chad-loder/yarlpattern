# Translate `google.api.http` to URLPattern

Google's [`google.api.http`](https://github.com/googleapis/googleapis/blob/master/google/api/http.proto)
annotation is the convention for mapping gRPC RPCs to HTTP/JSON URLs.
Vertex AI's inference RPCs, the Cloud APIs, and every service running
behind [grpc-gateway](https://github.com/grpc-ecosystem/grpc-gateway)
use it. The grammar is essentially URLPattern in protobuf form.

## The pattern

```protobuf
service AIPlatform {
  rpc Predict(PredictRequest) returns (PredictResponse) {
    option (google.api.http) = {
      post: "/v1/{endpoint=projects/*/locations/*/endpoints/*}:predict"
      additional_bindings {
        post: "/v1/{name=projects/*/locations/*/publishers/*/models/*}:predict"
      }
    };
  }
}
```

`{name=projects/*/locations/*/models/*}` is a *multi-segment capture
with a literal scaffold* — exactly what URLPattern named groups do.

## A Python client / proxy ingesting these URLs

Without a URL-pattern library, a Python proxy fronting a gRPC service
that ingests these URLs writes per-endpoint regex:

```python
import re
_PREDICT = re.compile(
    r"^/v1/projects/(?P<project>[^/]+)"
    r"/locations/(?P<location>[^/]+)"
    r"/models/(?P<model>[^/]+):predict$"
)

def extract(path):
    m = _PREDICT.match(path)
    return m.groupdict() if m else None
```

…and a separate, similarly-shaped regex for every additional binding.

## With URLPattern

```python
from yarlpattern import URLPattern

PREDICT = URLPattern({
    "pathname": "/v1/projects/:project/locations/:location/models/:model\\::action(predict|classify)",
})

PREDICT.exec("https://aiplatform.googleapis.com/v1/projects/p1/locations/us-central1/models/m99:predict").pathname["groups"]
# {'project': 'p1', 'location': 'us-central1', 'model': 'm99', 'action': 'predict'}

PREDICT.test("https://aiplatform.googleapis.com/v1/projects/p1/locations/us-central1/models/m99:explain")
# False — :action constraint rejects 'explain'
```

The `\\:` escapes the literal colon that separates the resource name
from the verb (Google AIP-136 convention). The `:action(predict|classify)`
named group enforces that only legitimate verbs match.

`additional_bindings` translates to a list of URLPattern objects under
one handler:

```python
PREDICT_BINDINGS = [
    URLPattern({"pathname": "/v1/projects/:project/locations/:location/endpoints/:endpoint\\:predict"}),
    URLPattern({"pathname": "/v1/projects/:project/locations/:location/publishers/:publisher/models/:model\\:predict"}),
]

def route_predict(url):
    for pat in PREDICT_BINDINGS:
        result = pat.exec(url)
        if result is not None:
            return predict_handler(result.pathname["groups"])
```

## What you get for free

- **`{name=projects/*/locations/*/models/*}` is URLPattern semantics
  in protobuf form.** Translation is mechanical: each `*` becomes a
  named group; the literal scaffold (`projects/`, `locations/`,
  `models/`) stays as-is.
- **Verb enums via regex group.** `:action(predict|classify)` rejects
  unknown verbs at the pattern level — the `google.api.http` grammar
  doesn't enforce this directly, but URLPattern can.
- **`additional_bindings` ↔ pattern list.** Multiple URLPattern
  entries pointing at the same handler are the natural representation;
  `compare_component()` gives you the same specificity ordering grpc-
  gateway computes internally.
- **Same patterns work everywhere.** A Python sidecar fronting a
  gRPC-gateway-translated service, a Cloudflare Worker fronting the
  same service, and a Deno trace exporter all match URLs identically
  if they share the URLPattern definitions. The translation from
  `.proto` to URLPattern is the single source of truth.
