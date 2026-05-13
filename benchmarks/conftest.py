"""Shared fixtures for the yarlpattern benchmark suite.

The benchmark tree lives outside ``tests/`` so it is *not* picked up by the
default ``pytest`` invocation (see ``[tool.pytest.ini_options].testpaths``
in ``pyproject.toml``). Run with::

    just bench
    # or
    uv run --group bench pytest benchmarks/

These benchmarks measure yarlpattern against itself across the hot paths
that real callers exercise: constructor cost, ``test()``, ``exec()``, and
the ``yarl.URL`` fast path. They deliberately do *not* compare against
other URLPattern implementations — apples-to-apples cross-library
comparison is a different exercise with its own methodological pitfalls.
"""

from __future__ import annotations

import pytest
from yarl import URL

from yarlpattern import URLPattern

# A representative cross-section of pattern shapes callers actually use.
# Picked to cover:
#   - literal-only (fastest path; no groups, no regex back-references)
#   - one named group with default segment-wildcard
#   - one named group with an explicit ECMAScript-style regex constraint
#   - the multi-component "kitchen sink" used in the MDN guide
#   - wildcard-heavy catch-all routing pattern
PATTERN_DEFINITIONS = {
    "literal-pathname": "/foo/bar/baz",
    "named-group": "/users/:id",
    "regex-constrained": r"/users/:id(\d+)/posts/:slug",
    "wildcard-tail": "/api/:version/*",
}


@pytest.fixture(scope="session")
def url_match_str() -> str:
    """A URL string that matches every fixture pattern's pathname expectations."""
    return "https://example.com/users/123/posts/hello-world"


@pytest.fixture(scope="session")
def url_match_yarl(url_match_str: str) -> URL:
    """The matching URL pre-parsed into a :class:`yarl.URL` — the fast-path input."""
    return URL(url_match_str)


@pytest.fixture(scope="session")
def url_nomatch_str() -> str:
    """A URL that fails pattern-matching early at the protocol or path stage."""
    return "ftp://example.com/sessions/abc"


@pytest.fixture(scope="session")
def kitchen_sink_pattern() -> URLPattern:
    """Multi-component pattern from MDN's "Using multiple components" guide.

    Held as a session-scoped instance so the construction cost is amortised
    across benchmarks that only care about ``test`` / ``exec`` throughput.
    """
    return URLPattern(
        {
            "protocol": "http{s}?",
            "username": ":user?",
            "password": ":pass?",
            "hostname": "{:subdomain.}*example.com",
            "pathname": "/product/:action*",
        }
    )


@pytest.fixture(
    scope="session",
    params=sorted(PATTERN_DEFINITIONS.keys()),
    ids=sorted(PATTERN_DEFINITIONS.keys()),
)
def pattern_source(request: pytest.FixtureRequest) -> str:
    """The raw pathname-only pattern string, parametrized across all shapes."""
    return PATTERN_DEFINITIONS[request.param]


@pytest.fixture(scope="session")
def compiled_patterns() -> dict[str, URLPattern]:
    """One pre-compiled :class:`URLPattern` per pattern shape, keyed by id.

    Constructors are not free — keeping these in a session-scoped dict lets
    ``test`` / ``exec`` benchmarks isolate match cost from compile cost.
    """
    return {name: URLPattern({"pathname": src}) for name, src in PATTERN_DEFINITIONS.items()}
