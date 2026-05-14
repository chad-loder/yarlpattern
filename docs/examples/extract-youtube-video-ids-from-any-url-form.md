# Extract YouTube video IDs from any URL form

The "extract a video ID from a YouTube link" question is one of the
most-asked URL-parsing problems on Stack Overflow. The reason it's
tricky is that *the same ID* lives in four different URL shapes:

- `https://www.youtube.com/watch?v=ID`
- `https://youtu.be/ID`
- `https://www.youtube.com/embed/ID`
- `https://www.youtube.com/shorts/ID`

…and a robust extractor has to handle the subdomain (`m.youtube.com`,
no subdomain, etc.), the country variants (`youtube.co.uk` is rare),
and the trailing-query case (`?t=42s`).

## The awkward way

Composite of the most-upvoted Stack Overflow answer to ["How can I
extract video ID from YouTube's link in Python?"](https://stackoverflow.com/questions/4356538/how-can-i-extract-video-id-from-youtubes-link-in-python):

```python
from urllib.parse import urlparse, parse_qs

def get_yt_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if "youtu.be" in hostname:
        return parsed.path.lstrip("/") or None
    if "youtube.com" in hostname:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith(("/embed/", "/v/", "/shorts/")):
            return parsed.path.split("/")[2]
    return None
```

Three branches glued together by ad-hoc string ops; `hostname.endswith()`
checks; `parse_qs` + index 0; no validation that the captured ID
actually looks like a YouTube ID.

## With URLPattern

```python
from yarlpattern import URLPattern

_YT_PATTERNS = [
    URLPattern({"hostname": "{*.}?youtube.com",
                "pathname": "/watch",
                "search":   "*v=:vid([^&]+)(.*)"}),
    URLPattern({"hostname": "youtu.be",
                "pathname": "/:vid"}),
    URLPattern({"hostname": "{*.}?youtube.com",
                "pathname": "/:kind(embed|v|shorts)/:vid"}),
]

def get_yt_video_id(url: str) -> str | None:
    for pat in _YT_PATTERNS:
        result = pat.exec(url)
        if result is not None:
            groups = result.pathname["groups"] | result.search["groups"]
            return groups.get("vid")
    return None
```

Three patterns, one loop. Each pattern is its own assertion about which
URL shape it covers; adding a fourth shape (say, `music.youtube.com`)
is one more `URLPattern({...})` entry, not another branch with its own
string-slicing.

## What you get for free

- **Hostname subdomain wildcard** — `{*.}?youtube.com` matches the
  apex domain *and* any subdomain, but only at the label boundary.
  `youtube.com.evil.com` (a phishing-style hostname) does not match
  this pattern; the naive `"youtube.com" in hostname` check would.
- **Regex-constrained named group** — `:kind(embed|v|shorts)` only
  matches the three legitimate path prefixes. A URL with
  `/foo/abc123` doesn't accidentally classify as an embed.
- **Search-component matching** — `*v=:vid([^&]+)(.*)` extracts the
  `v=` parameter from a query string without `parse_qs`. The `[^&]+`
  bound stops the capture at the next `&`, and the trailing `(.*)`
  absorbs the rest, so the value comes out clean even when other
  params are mixed in (`?v=ID&t=42s`). Note that a bare `:vid` here
  would not stop at `&` — the search component has no delimiter, so
  the value group needs an explicit regex bound.
- **Spec-strict normalization** — uppercase / lowercase hostnames,
  percent-encoded path bytes, trailing slashes all behave consistently
  because the matching goes through WHATWG URL parsing.
