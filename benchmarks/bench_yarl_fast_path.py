"""Benchmarks: the :class:`yarl.URL` input fast path.

When the caller passes an already-parsed :class:`yarl.URL`, yarlpattern
skips ``yarl.URL(url_str)`` construction and reads the URL components
directly off the yarl instance. For ``aiohttp`` / yarl-based applications
(where every request already holds a parsed URL) this avoids re-parsing
the same string on every match.

These benchmarks expose the delta by running the same match through the
string-input path (parse-then-match) and the yarl-input path (match
only) side by side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture
    from yarl import URL

    from yarlpattern import URLPattern


def test_test_with_string_input(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    url_match_str: str,
) -> None:
    """Baseline: ``test()`` on a string input — includes ``yarl.URL`` parsing."""
    pat = compiled_patterns["regex-constrained"]
    benchmark(pat.test, url_match_str)


def test_test_with_yarl_input(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    url_match_yarl: URL,
) -> None:
    """Fast path: ``test()`` on a pre-built :class:`yarl.URL` — no reparse."""
    pat = compiled_patterns["regex-constrained"]
    benchmark(pat.test, url_match_yarl)


def test_exec_with_string_input(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    url_match_str: str,
) -> None:
    """Baseline: ``exec()`` on a string input — includes ``yarl.URL`` parsing."""
    pat = compiled_patterns["regex-constrained"]
    benchmark(pat.exec, url_match_str)


def test_exec_with_yarl_input(
    benchmark: BenchmarkFixture,
    compiled_patterns: dict[str, URLPattern],
    url_match_yarl: URL,
) -> None:
    """Fast path: ``exec()`` on a pre-built :class:`yarl.URL` — no reparse."""
    pat = compiled_patterns["regex-constrained"]
    benchmark(pat.exec, url_match_yarl)
