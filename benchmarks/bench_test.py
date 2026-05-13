"""Benchmarks: ``URLPattern.test()`` throughput.

``test()`` is the boolean-only fast path: it short-circuits on the first
failing component and never builds the ``URLPatternResult`` envelope.
The benchmarks cover both the "hit" case (every component matches) and
the "miss" case (a wrong protocol fails fast at the first component).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from yarlpattern import URLPattern


def test_test_hit_pathname_only(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    pattern_source: str,  # noqa: ARG001 — included only to parametrize over shapes
    url_match_str: str,
    request: object,
) -> None:
    """Match a single-component pattern against the canonical URL string."""
    shape = request.node.callspec.id  # type: ignore[attr-defined]
    pat = compiled_patterns[shape]
    benchmark(pat.test, url_match_str)


def test_test_miss_protocol_fail_fast(
    benchmark: BenchmarkFixture,
    kitchen_sink_pattern: URLPattern,
    url_nomatch_str: str,
) -> None:
    """Match-miss with the protocol failing first — exercises short-circuit cost."""
    benchmark(kitchen_sink_pattern.test, url_nomatch_str)


def test_test_hit_kitchen_sink_dict(
    benchmark: BenchmarkFixture,
    kitchen_sink_pattern: URLPattern,
) -> None:
    """Match-hit on a pre-parsed component dict input — skips URL parsing."""
    components = {
        "protocol": "https",
        "username": "foo",
        "password": "bar",
        "hostname": "sub.example.com",
        "pathname": "/product/view",
    }
    benchmark(kitchen_sink_pattern.test, components)
