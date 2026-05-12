# Replace MCP resource URI templates

The [Model Context Protocol](https://modelcontextprotocol.io/) addresses
resources by URI — custom schemes like `weather://`, `db://`, `notion://`,
`screen://`. The official Python SDK and FastMCP both ship URI-template
matchers, and both of them are hand-rolled URLPattern lookalikes.

## The awkward way

[Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
`src/mcp/server/mcpserver/resources/templates.py`:

```python
def matches(self, uri: str) -> dict[str, Any] | None:
    """Check if URI matches template and extract parameters."""
    pattern = self.uri_template.replace("{", "(?P<").replace("}", ">[^/]+)")
    match = re.match(f"^{pattern}$", uri)
    if match:
        return {key: unquote(value) for key, value in match.groupdict().items()}
    return None
```

Two `str.replace` calls plus `re.match`. No scheme isolation, no
wildcards, no segment regex constraints, no way to express an optional
trailing segment. A template like `weather://{city}/current` matches
`db://anything/current` too, because the scheme isn't part of the
"pattern" — it's part of the URI string the regex happens to see.

FastMCP rebuilt the same thing with more features (`build_regex()` in
[`fastmcp_slim/fastmcp/resources/template.py`](https://github.com/jlowin/fastmcp/blob/main/fastmcp_slim/fastmcp/resources/template.py)),
still as a regex-string-concat with `try/except re.error` to detect bad
templates.

## With URLPattern

```python
from yarlpattern import URLPattern

WEATHER = URLPattern({"protocol": "weather", "hostname": ":city", "pathname": "/current"})

WEATHER.test("weather://nyc/current")        # True
WEATHER.test("weather://sf/current")         # True
WEATHER.test("weather://nyc/forecast")       # False — wrong path
WEATHER.test("db://nyc/current")             # False — wrong scheme

WEATHER.exec("weather://nyc/current").hostname["groups"]["city"]   # 'nyc'
```

Need an integer-only resource id? Constrain the named group:

```python
DB_USER = URLPattern({"protocol": "db", "hostname": ":table", "pathname": "/:id(\\d+)"})

DB_USER.test("db://users/42")     # True
DB_USER.test("db://users/abc")    # False — id must be digits
```

A whole resource registry becomes a small table:

```python
RESOURCES = [
    (WEATHER, get_weather),
    (URLPattern({"protocol": "db", "hostname": ":table", "pathname": "/:id(\\d+)"}),
     fetch_record),
    (URLPattern({"protocol": "file", "pathname": "/:path+"}),
     read_file),
    (URLPattern({"protocol": "notion", "hostname": ":workspace", "pathname": "/:page_id"}),
     load_notion_page),
]

def dispatch(uri: str):
    for pattern, handler in RESOURCES:
        result = pattern.exec(uri)
        if result is not None:
            return handler(result)
```

## What you get for free

- **Scheme isolation by construction.** `protocol: "weather"` means
  exactly that scheme; the MCP SDK's `str.replace` trick gives you no
  such isolation — any URI shape matches as long as the path lines up.
- **Per-group regex constraints.** `:id(\\d+)` rejects non-numeric ids
  at the pattern level. FastMCP's regex-string-concat can express this
  but only if you remember to escape every other character correctly.
- **Spec-conformant URI parsing.** Custom schemes, percent-encoding,
  case folding all behave consistently with the rest of the URL
  parsing in your application (yarlpattern delegates to yarl, which
  is WHATWG-conformant).
- **The pattern *is* the documentation.** A reader sees
  `URLPattern({"protocol": "weather", "hostname": ":city", "pathname": "/current"})`
  and knows the resource shape immediately. The MCP SDK's
  `{"city/current"}` template lives inside a class with a `matches()`
  method that has to be read to understand what it accepts.
