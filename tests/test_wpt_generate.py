"""Port of ``reference/wpt/urlpattern/urlpattern-generate.tentative.any.js``.

``URLPattern.generate(component, groups)`` reverses an exec — given the
named groups, produce the URL-string the pattern would have matched.
Useful for URL builders that want to roundtrip via the same pattern.

Tentative-spec feature; skipped by default. Set
``WHATWG_URLPATTERN_RUN_TENTATIVE=1`` to run.
"""

from __future__ import annotations

import json
import os
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
    / "urlpattern-generate-test-data.json"
)

_ENABLE = os.environ.get("WHATWG_URLPATTERN_RUN_TENTATIVE", "").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def _load() -> list[dict[str, Any]]:
    if not _DATA_PATH.exists():
        msg = (
            f"WPT generate-test corpus not found at {_DATA_PATH}. "
            "Run `scripts/fetch_wpt_corpus.sh` to populate the corpus."
        )
        raise FileNotFoundError(msg)
    return json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _case_id(idx: int, entry: dict[str, Any]) -> str:
    pat = json.dumps(entry.get("pattern"), separators=(",", ":"))
    groups = json.dumps(entry.get("groups"), separators=(",", ":"))
    return f"{idx:03d}-{entry.get('component')}-{pat}-{groups}"


_CASES = _load()
_IDS = [_case_id(i, c) for i, c in enumerate(_CASES)]


@pytest.mark.skipif(
    not _ENABLE,
    reason=("URLPattern.generate() is a tentative-spec feature; set WHATWG_URLPATTERN_RUN_TENTATIVE=1 to run."),
)
@pytest.mark.parametrize("entry", _CASES, ids=_IDS)
def test_wpt_generate(entry: dict[str, Any]) -> None:
    """One parametrized entry from ``urlpattern-generate-test-data.json``."""
    pattern = URLPattern(entry["pattern"])

    generate = getattr(pattern, "generate", None)
    if generate is None:
        pytest.fail("URLPattern.generate is not implemented")

    if entry["expected"] is None:
        # ``expected: null`` means the call must throw TypeError. In JS this
        # covers e.g. an invalid component name or groups that don't satisfy
        # the pattern's required captures.
        with pytest.raises(TypeError):
            generate(entry["component"], entry["groups"])
        return

    result = generate(entry["component"], entry["groups"])
    assert result == entry["expected"]
