"""Benchmarks: ``URLPattern.exec()`` throughput.

``exec()`` extends ``test()`` by building a :class:`URLPatternResult` —
one dict per component containing the input substring and a ``groups``
sub-dict of named-group captures. That extra allocation is the entire
delta versus :file:`bench_test.py`; comparing the two measurements
reveals the overhead of result construction in isolation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from yarlpattern import URLPattern


def test_exec_hit_pathname_only(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    pattern_source: str,  # noqa: ARG001 — included only to parametrize over shapes
    url_match_str: str,
    request: object,
) -> None:
    """exec-hit on each pattern shape; result envelope must be allocated."""
    shape = request.node.callspec.id  # type: ignore[attr-defined]
    pat = compiled_patterns[shape]
    benchmark(pat.exec, url_match_str)


def test_exec_miss_returns_none(
    benchmark: BenchmarkFixture,
    kitchen_sink_pattern: URLPattern,
    url_nomatch_str: str,
) -> None:
    """exec-miss returns ``None`` without allocating a result — should match ``test`` miss cost."""
    benchmark(kitchen_sink_pattern.exec, url_nomatch_str)


def test_exec_hit_extract_named_groups(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    url_match_str: str,
) -> None:
    """exec-hit and immediately read out the captured ``:id`` and ``:slug`` groups."""
    pat = compiled_patterns["regex-constrained"]

    def _hit_and_extract() -> tuple[str | None, str | None]:
        result = pat.exec(url_match_str)
        assert result is not None
        return result.pathname["groups"].get("id"), result.pathname["groups"].get("slug")

    benchmark(_hit_and_extract)
