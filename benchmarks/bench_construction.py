"""Benchmarks: ``URLPattern(...)`` construction cost.

Construction is paid once per pattern but is the load-bearing cost for any
caller that does *not* memoise the compiled pattern (e.g. ad-hoc one-shot
URL checks in scripts, or per-request reconstruction in code that has not
been profiled yet). The four pattern shapes here cover the spectrum from
"literal-only, no regex compile" to "multi-component dict with five regex
backings".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from yarlpattern import URLPattern

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture


def test_construct_from_pathname_string(
    benchmark: BenchmarkFixture,
    pattern_source: str,
) -> None:
    """Compile a single-component pattern from its pathname string."""
    benchmark(lambda: URLPattern({"pathname": pattern_source}))


def test_construct_from_full_url_string(benchmark: BenchmarkFixture) -> None:
    """Compile a pattern from a full URL string (parses to multi-component)."""
    pat = "https://example.com/users/:id(\\d+)/posts/:slug"
    benchmark(lambda: URLPattern(pat))


def test_construct_from_multi_component_dict(benchmark: BenchmarkFixture) -> None:
    """Compile MDN's kitchen-sink five-component pattern from a dict literal."""
    components = {
        "protocol": "http{s}?",
        "username": ":user?",
        "password": ":pass?",
        "hostname": "{:subdomain.}*example.com",
        "pathname": "/product/:action*",
    }
    benchmark(lambda: URLPattern(components))


def test_construct_with_base_url(benchmark: BenchmarkFixture) -> None:
    """Compile a relative-form pattern resolved against a baseURL."""
    benchmark(lambda: URLPattern("/users/:id", "https://example.com/"))
