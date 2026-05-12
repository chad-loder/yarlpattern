"""Port of ``reference/wpt/urlpattern/resources/urlpattern-compare-tests.tentative.js``.

The compare suite tests :meth:`URLPattern.compareComponent` — a static
method that returns a three-way comparison between two patterns for a
single component. URL routing libraries use it to order patterns from
most-specific to least-specific.

The corresponding WPT file is marked ``.tentative`` because the spec
text itself is not yet stable; the method shape and behavior, however,
*are* stable enough that two reference implementations (Chromium, the
WHATWG polyfill) agree on the same 25-case corpus. We implement it
against that agreed-on behavior and run the corpus by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from yarlpattern import URLPattern

_DATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "reference"
    / "wpt"
    / "urlpattern"
    / "resources"
    / "urlpattern-compare-test-data.json"
)


def _load() -> list[dict[str, Any]]:
    if not _DATA_PATH.exists():
        msg = (
            f"WPT compare-test corpus not found at {_DATA_PATH}. "
            "Run `scripts/fetch_wpt_corpus.sh` to populate the corpus."
        )
        raise FileNotFoundError(msg)
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _case_id(idx: int, entry: dict[str, Any]) -> str:
    left = json.dumps(entry.get("left"), separators=(",", ":"))
    right = json.dumps(entry.get("right"), separators=(",", ":"))
    return f"{idx:03d}-{entry.get('component')}-{left}-vs-{right}"


_CASES = _load()
_IDS = [_case_id(i, c) for i, c in enumerate(_CASES)]


@pytest.mark.parametrize("entry", _CASES, ids=_IDS)
def test_wpt_compare(entry: dict[str, Any]) -> None:
    """One parametrized entry from ``urlpattern-compare-test-data.json``."""
    left = URLPattern(entry["left"])
    right = URLPattern(entry["right"])
    component: str = entry["component"]
    expected: int = entry["expected"]

    assert URLPattern.compareComponent(component, left, right) == expected
    # Reverse: JS uses ``~~(expected * -1)`` to coerce ``-0`` to ``0``;
    # Python's ints have no negative-zero, so a plain negation is enough.
    assert URLPattern.compareComponent(component, right, left) == -expected
    # Self-equality.
    assert URLPattern.compareComponent(component, left, left) == 0
    assert URLPattern.compareComponent(component, right, right) == 0
