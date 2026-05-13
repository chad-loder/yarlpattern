"""Run every WICG urlpattern-polyfill test case against yarlpattern.

A second cross-implementation conformance vector beyond the upstream
WPT corpus. The polyfill's ``urlpatterntestdata.json`` is a slightly
older snapshot of the WPT file plus a handful of polyfill-specific
entries; running it adds redundant coverage of the shared cases and
flags any case where yarlpattern's compiled-pattern strings differ
from the polyfill's expectations (a useful regression net for changes
to the canonicalisation layer).

Cases where the polyfill diverges from the current WHATWG spec (the
two implementations disagree on whether some hostname / port patterns
should construct successfully) are skipped at parametrize time in
``conftest.py`` via :func:`_polyfill_diverges_from_wpt`. The skips
are deliberate and tracked, not failures hidden under a carpet.

Driver-logic-wise, this file is a thin shim over the same
``test_wpt_case`` runner — the data shape is identical, only the
fixture is different.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .test_wpt import test_wpt_case as _run_data_corpus_case

if TYPE_CHECKING:
    import pytest


def test_polyfill_case(polyfill_case: dict[str, Any], request: pytest.FixtureRequest) -> None:
    """Execute one parametrized polyfill urlpattern conformance entry."""
    _run_data_corpus_case(polyfill_case, request)
