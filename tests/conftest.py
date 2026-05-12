"""Shared pytest fixtures and the WPT-data-driven test parametrization.

The WPT urlpattern suite at ``reference/wpt/urlpattern/resources/urlpatterntestdata.json``
is the canonical conformance corpus. Rather than transcribing 366 entries into Python
source (which would inevitably drift), we read the JSON at collection time and
generate one parametrized test per entry. Entries flow into ``test_wpt.py``; the
harness logic that mirrors the WPT JS runner lives in this file as
``run_wpt_case`` so it can be reused for ad-hoc reproduction.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from yarlpattern import COMPONENTS  # re-exported for tests that need the canonical order

__all__ = ["COMPONENTS", "load_wpt_cases", "wpt_data_path"]

# Locating the data file. We deliberately do NOT vendor WPT into the source tree;
# `scripts/fetch_references.sh` populates `reference/wpt/`. The path is also
# overrideable via WPT_URLPATTERN_DATA so CI or downstream packagers can point
# the suite at a pinned copy.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _REPO_ROOT / "reference" / "wpt" / "urlpattern" / "resources" / "urlpatterntestdata.json"


def wpt_data_path() -> Path:
    override = os.environ.get("WPT_URLPATTERN_DATA")
    return Path(override) if override else _DEFAULT_DATA


def load_wpt_cases() -> list[dict[str, Any]]:
    """Parse the WPT urlpattern test data file.

    Each entry is a dict with some subset of these keys:
      - ``pattern``    : list of constructor args (1–2 items)
      - ``inputs``     : list of args to ``.test()`` / ``.exec()``
      - ``expected_obj``: expected per-component pattern strings on the compiled
                         URLPattern; the literal string ``"error"`` signals the
                         constructor itself should raise TypeError.
      - ``expected_match`` : the expected ``.exec()`` result, or ``null`` for no
                             match, or the literal string ``"error"`` to signal
                             that ``.test()`` / ``.exec()`` should raise.
      - ``exactly_empty_components`` : components asserted to be exactly empty.
      - ``//``         : free-text comments (ignored by the harness).
    """
    path = wpt_data_path()
    if not path.exists():
        pytest.skip(
            f"WPT urlpattern test data not found at {path}. "
            "Run `scripts/fetch_references.sh` or set WPT_URLPATTERN_DATA.",
            allow_module_level=True,
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _case_id(idx: int, entry: dict[str, Any]) -> str:
    """Construct a short, human-readable test id for parametrize.

    Format: ``<idx>-<first-pattern-summary>``. The pattern is summarized to keep
    pytest's -k filtering useful without blowing up the report column width.
    """
    pat = entry.get("pattern", [])
    if pat and isinstance(pat[0], dict):
        summary = ",".join(f"{k}={v!r}" for k, v in pat[0].items())
    elif pat and isinstance(pat[0], str):
        summary = pat[0]
    else:
        summary = "<no-pattern>"
    summary = summary.replace(" ", "")
    if len(summary) > 80:
        summary = summary[:77] + "..."
    return f"{idx:03d}-{summary}"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply the ``wpt`` marker to every parametrized WPT case automatically."""
    wpt_marker = pytest.mark.wpt
    for item in items:
        if "wpt_case" in getattr(item, "fixturenames", ()):
            item.add_marker(wpt_marker)


@pytest.fixture(scope="session")
def wpt_cases() -> list[dict[str, Any]]:
    """All WPT urlpattern cases, loaded once per session."""
    return load_wpt_cases()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize tests that request a single ``wpt_case`` over every entry.

    Using ``pytest_generate_tests`` (rather than a parametrize decorator on the
    test function) keeps the data-loading logic centralized here, lets us
    override the path via env var without churn, and makes the test function
    itself a one-liner over the harness.
    """
    if "wpt_case" not in metafunc.fixturenames:
        return
    cases = load_wpt_cases()
    metafunc.parametrize(
        "wpt_case",
        cases,
        ids=[_case_id(i, c) for i, c in enumerate(cases)],
    )
