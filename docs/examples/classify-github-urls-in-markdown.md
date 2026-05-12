# Classify GitHub URLs in markdown

Any pipeline that ingests prose containing URLs and needs to do
domain-specific things with some of them — RAG corpora, knowledge
graphs, citation indexers, link-checking — hits the same two-layer
shape:

1. **Find URL strings in arbitrary text.** A small, stable regex.
2. **Classify each URL into a known shape and pull out structured
   fields.** A growing table of patterns that needs to stay
   declarative.

URLPattern is for layer two. Here we use GitHub URLs as the concrete
demonstration — they're the densest, best-known structured-URL family
in any developer corpus, and they cover every interesting URLPattern
feature in one example.

## The awkward way

Each URL shape is two hand-written functions — a classifier and an
extractor — that have to stay in sync:

```python
import yarl

def is_github_issue(url: yarl.URL) -> bool:
    return (
        url.host == "github.com"
        and len(url.parts) >= 5
        and url.parts[3] == "issues"
        and url.parts[4].isdigit()
    )

def extract_github_issue(url: yarl.URL) -> dict[str, str]:
    owner, repo, _, num = url.parts[1], url.parts[2], url.parts[3], url.parts[4]
    out = {"owner": owner, "repo": repo, "num": num}
    if (url.fragment or "").startswith("issuecomment-"):
        out["comment_id"] = url.fragment.removeprefix("issuecomment-")
    return out
```

For each new shape — PRs, commits, blobs with line ranges, releases,
compare URLs, gists — you write two more functions. The "shape of an
issue URL" is implicit in the four `parts` index checks; nothing names
the fields until you `removeprefix` your way to them.

## With URLPattern

```python
from yarlpattern import URLPattern

ISSUE         = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/issues/:num(\\d+)"})
ISSUE_COMMENT = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/issues/:num(\\d+)",
                            "hash":     "issuecomment-:comment_id(\\d+)"})
PR            = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/pull/:num(\\d+)"})
PR_REVIEW     = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/pull/:num(\\d+)",
                            "hash":     "discussion_r:comment_id(\\d+)"})
COMMIT        = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/commit/:sha([0-9a-f]+)"})
BLOB          = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/blob/:ref/:path+"})
BLOB_LINES    = URLPattern({"hostname": "github.com",
                            "pathname": "/:owner/:repo/blob/:ref/:path+",
                            "hash":     "L:start(\\d+){-L:end(\\d+)}?"})

# Most-specific patterns first so the deep-link variants win over the
# base shapes (e.g. an issue comment URL also matches the bare-issue
# pattern; we want the comment_id-bearing match).
TABLE = [
    ("issue_comment", ISSUE_COMMENT),
    ("pr_review",     PR_REVIEW),
    ("blob_lines",    BLOB_LINES),
    ("issue",         ISSUE),
    ("pr",            PR),
    ("commit",        COMMIT),
    ("blob",          BLOB),
]

def classify(url: str) -> tuple[str, dict[str, str]] | None:
    for kind, pat in TABLE:
        result = pat.exec(url)
        if result is not None:
            fields = {**result.pathname["groups"], **result.hash["groups"]}
            return kind, {k: v for k, v in fields.items() if v}
    return None
```

Concrete output for an issue-comment deep link:

```python
classify("https://github.com/chad-loder/yarlpattern/issues/42#issuecomment-1234567")
# ('issue_comment',
#  {'owner': 'chad-loder', 'repo': 'yarlpattern', 'num': '42', 'comment_id': '1234567'})

classify("https://github.com/chad-loder/yarlpattern/blob/main/src/foo.py#L42-L50")
# ('blob_lines',
#  {'owner': 'chad-loder', 'repo': 'yarlpattern',
#   'ref': 'main', 'path': 'src/foo.py', 'start': '42', 'end': '50'})

classify("https://github.com/chad-loder/yarlpattern/commit/b97ec43abc")
# ('commit', {'owner': 'chad-loder', 'repo': 'yarlpattern', 'sha': 'b97ec43abc'})
```

Each new shape is one more entry in `TABLE`: gists, releases, tags,
compare URLs, raw file URLs (`raw.githubusercontent.com/...`),
enterprise GitHub instances (`{:host}.ghe.example.com`), Gitea forks
with compatible URL conventions — all one pattern each.

## The two-layer split

URLPattern matches **structured URLs**, not text. The text-scan step
stays its own thing:

```python
import re
URL_RE = re.compile(r"https?://[^\s\)\]\"\'<>]+")

for url in URL_RE.findall(markdown_text):
    kind, fields = classify(url) or (None, None)
    if kind is not None:
        handle(kind, fields)
```

The boundary between *extracting URL strings from text* and
*classifying / destructuring one URL string* is real and useful. The
extraction regex is small and rarely-changed; the classification
table is where the surface grows. Letting URLPattern own the
classification layer keeps the growing surface declarative.

## What you get for free

- **Optional segment groups for deep-link fragments.** The
  `{-L:end(\\d+)}?` inside the blob hash pattern is *one* optional
  group; the same pattern matches `#L42` and `#L42-L50`. No
  branch-on-presence dance in the handler.
- **Per-group regex constraints catch typos at the pattern level.**
  `:num(\\d+)`, `:sha([0-9a-f]+)`, `:start(\\d+)` — non-conforming
  URLs simply don't classify, no validator needed downstream.
- **Patterns are documentation.** A reviewer can read the `TABLE`
  list and see exactly which GitHub URL shapes the pipeline
  recognizes — no need to trace classifier functions.
- **Composes upward.** A pattern that fronts the whole GitHub family
  (`URLPattern({"hostname": "github.com"})`) lets you cheaply filter
  out non-GitHub URLs before the per-shape dispatch, and the named
  groups it would have captured stay available.
- **Spec-strict URL normalization.** Case folding, percent-encoding,
  trailing slashes, empty segments all behave per WHATWG. Two URLs
  the spec considers equivalent match the same pattern even if their
  textual form differs.
