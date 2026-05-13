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

__all__ = [
    "COMPONENTS",
    "load_polyfill_cases",
    "load_wpt_cases",
    "polyfill_data_path",
    "wpt_data_path",
]

# Locating the data file. We deliberately do NOT vendor WPT into the source tree;
# `scripts/fetch_references.sh` populates `reference/wpt/`. The path is also
# overrideable via WPT_URLPATTERN_DATA so CI or downstream packagers can point
# the suite at a pinned copy.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA = _REPO_ROOT / "reference" / "wpt" / "urlpattern" / "resources" / "urlpatterntestdata.json"

# Second cross-implementation conformance vector: the WICG urlpattern-polyfill's
# own test fixture. Populated by ``scripts/fetch_polyfill_corpus.sh``;
# overrideable via ``URLPATTERN_POLYFILL_DATA`` for downstream pinning.
_DEFAULT_POLYFILL_DATA = _REPO_ROOT / "reference" / "polyfill" / "test" / "urlpatterntestdata.json"


def wpt_data_path() -> Path:
    override = os.environ.get("WPT_URLPATTERN_DATA")
    return Path(override) if override else _DEFAULT_DATA


def polyfill_data_path() -> Path:
    override = os.environ.get("URLPATTERN_POLYFILL_DATA")
    return Path(override) if override else _DEFAULT_POLYFILL_DATA


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
        # Fail-fast: a missing fixture used to ``pytest.skip`` here, which
        # silently dropped ~470 conformance tests and made coverage look
        # artificially low. The corpus is load-bearing for our conformance
        # claims, so its absence is a CI / dev-env error, not a runtime
        # condition the tests should tolerate.
        msg = (
            f"WPT urlpattern test data not found at {path}. "
            "Run `scripts/fetch_wpt_corpus.sh` to populate the corpus, "
            "or set WPT_URLPATTERN_DATA to point at a copy."
        )
        raise FileNotFoundError(msg)
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


def load_polyfill_cases() -> list[dict[str, Any]]:
    """Parse the polyfill's urlpatterntestdata.json fixture.

    Structure mirrors the WPT corpus's; the polyfill's harness is itself
    derived from the WPT JS runner. Most entries are byte-identical to the
    WPT file (a snapshot of an older spec revision), with a small number
    that diverge — those are filtered by :func:`_polyfill_diverges_from_wpt`.
    """
    path = polyfill_data_path()
    if not path.exists():
        msg = (
            f"polyfill urlpattern test data not found at {path}. "
            "Run `scripts/fetch_polyfill_corpus.sh` to populate the corpus, "
            "or set URLPATTERN_POLYFILL_DATA to point at a copy."
        )
        raise FileNotFoundError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def _polyfill_diverges_from_wpt(
    polyfill_entry: dict[str, Any], wpt_by_pattern: dict[str, list[dict[str, Any]]]
) -> bool:
    """True iff the polyfill expects a constructor error but WPT does not.

    The polyfill bundles an older snapshot of urlpatterntestdata.json where
    a handful of pattern strings (e.g. ``{hostname: 'bad#hostname'}``) were
    marked as constructor errors. The current WHATWG spec — what yarlpattern
    targets — accepts these and applies Chromium-style truncation. Skipping
    here keeps the polyfill suite green without forcing yarlpattern to
    regress to the polyfill's older behaviour.
    """
    if polyfill_entry.get("expected_obj") != "error":
        return False
    key = json.dumps(
        {"pattern": polyfill_entry.get("pattern", [])},
        sort_keys=True,
        ensure_ascii=False,
    )
    candidates = wpt_by_pattern.get(key, [])
    return bool(candidates) and any(c.get("expected_obj") != "error" for c in candidates)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply suite markers (``wpt`` / ``polyfill``) to parametrized entries."""
    wpt_marker = pytest.mark.wpt
    polyfill_marker = pytest.mark.polyfill
    for item in items:
        fnames = getattr(item, "fixturenames", ())
        if "wpt_case" in fnames:
            item.add_marker(wpt_marker)
        if "polyfill_case" in fnames:
            item.add_marker(polyfill_marker)


@pytest.fixture(scope="session")
def wpt_cases() -> list[dict[str, Any]]:
    """All WPT urlpattern cases, loaded once per session."""
    return load_wpt_cases()


@pytest.fixture(scope="session")
def polyfill_cases() -> list[dict[str, Any]]:
    """All polyfill urlpattern cases, loaded once per session."""
    return load_polyfill_cases()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize tests that request a single corpus entry.

    Centralizing the data-loading logic here lets us override paths via env
    var without churn, and keeps each test function a one-liner over the
    shared harness.
    """
    if "wpt_case" in metafunc.fixturenames:
        cases = load_wpt_cases()
        metafunc.parametrize(
            "wpt_case",
            cases,
            ids=[_case_id(i, c) for i, c in enumerate(cases)],
        )
        return

    if "polyfill_case" in metafunc.fixturenames:
        # Both corpora interleave dict entries with bare-string ``//``-style
        # comments; cast through ``Any`` so the isinstance guards below are
        # real runtime narrowing, not redundant from the type checker's view.
        wpt_cases_list: list[Any] = load_wpt_cases()
        wpt_by_pattern: dict[str, list[dict[str, Any]]] = {}
        for w in wpt_cases_list:
            if not isinstance(w, dict) or "pattern" not in w:
                continue
            key = json.dumps(
                {"pattern": w["pattern"]},
                sort_keys=True,
                ensure_ascii=False,
            )
            wpt_by_pattern.setdefault(key, []).append(w)

        polyfill: list[Any] = load_polyfill_cases()
        params: list[Any] = []
        ids = []
        for i, entry in enumerate(polyfill):
            if not isinstance(entry, dict):
                # Polyfill data interleaves comment strings with case dicts;
                # skip those without consuming a parametrize slot.
                continue
            if _polyfill_diverges_from_wpt(entry, wpt_by_pattern):
                params.append(
                    pytest.param(
                        entry,
                        marks=pytest.mark.skip(
                            reason=(
                                "polyfill expects a constructor error here, but the "
                                "current WHATWG spec (what yarlpattern targets) does "
                                "not — kept in the suite as a tracked divergence"
                            ),
                        ),
                    ),
                )
            else:
                params.append(entry)
            ids.append(_case_id(i, entry))
        metafunc.parametrize("polyfill_case", params, ids=ids)
        return
