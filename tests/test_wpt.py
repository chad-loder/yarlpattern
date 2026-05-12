"""Run every WHATWG WPT urlpattern test case against our implementation.

This is a near-direct port of ``urlpatterntests.js`` from the WPT suite.
The case data flows in via the ``wpt_case`` fixture, which is parametrized
in ``conftest.py`` from ``urlpatterntestdata.json``. One entry → one test.

Until the implementation lands, most cases will fail; that failure count is
exactly the conformance signal we want to track over time.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import pytest

from yarlpattern import COMPONENTS, URLPattern
from yarlpattern._regex_engine import get_default_engine

# Mirror of EARLIER_COMPONENTS from the WPT JS harness — used to derive the
# expected component-pattern strings when ``expected_obj`` does not pin them.
EARLIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "protocol": (),
    "hostname": ("protocol",),
    "port": ("protocol", "hostname"),
    "username": (),
    "password": (),
    "pathname": ("protocol", "hostname", "port"),
    "search": ("protocol", "hostname", "port", "pathname"),
    "hash": ("protocol", "hostname", "port", "pathname", "search"),
}


def _expected_component_pattern(entry: dict[str, Any], component: str) -> str:
    """Compute the expected compiled-pattern string for one component.

    Mirrors the priority chain in ``urlpatterntests.js`` ``runTests``:
      1. Explicit value in ``expected_obj``.
      2. Listed in ``exactly_empty_components`` → ``""``.
      3. Component present on the first pattern arg → echo it back.
      4. An earlier component is specified → ``"*"`` (no baseURL inheritance).
      5. baseURL exists (from first arg's ``baseURL`` or second positional URL
         string) and the component is not username/password → that component
         of the URL, minus the URL-level separators (``:`` for protocol,
         leading ``?`` / ``#`` for search/hash).
      6. Fallback: ``"*"``.
    """
    expected_obj = entry.get("expected_obj") or {}
    if component in expected_obj:
        return expected_obj[component]

    exactly_empty = entry.get("exactly_empty_components") or []
    if component in exactly_empty:
        return ""

    pattern_args = entry.get("pattern", [])
    first = pattern_args[0] if pattern_args else None

    if isinstance(first, dict) and first.get(component):
        return first[component]
    if isinstance(first, dict) and any(c in first for c in EARLIER_COMPONENTS[component]):
        return "*"

    base_url: str | None = None
    if isinstance(first, dict) and first.get("baseURL"):
        base_url = first["baseURL"]
    elif len(pattern_args) > 1 and isinstance(pattern_args[1], str):
        base_url = pattern_args[1]

    if base_url and component not in ("username", "password"):
        parts = urlsplit(base_url)
        # urllib's SplitResult uses ``scheme``/``netloc``/``path``/``query``/``fragment``;
        # the WPT JS harness pulls component-named getters off URL() and strips
        # the separators. Map and strip here.
        if component == "protocol":
            return parts.scheme
        if component == "hostname":
            return parts.hostname or ""
        if component == "port":
            return str(parts.port) if parts.port is not None else ""
        if component == "pathname":
            return parts.path
        if component == "search":
            return parts.query
        if component == "hash":
            return parts.fragment

    return "*"


def _auto_populate_expected_component(
    entry: dict[str, Any],
    component: str,
) -> dict[str, Any]:
    """Mirror of the ``if (!expected_obj)`` branch in urlpatterntests.js.

    The WPT data file omits ``expected_match[component]`` for any component
    that would just match the wildcard default — the harness fills in
    ``{input: "", groups: {"0": ""}}`` automatically so tests stay terse.
    Components listed in ``exactly_empty_components`` get an empty groups
    map instead, reflecting that they were compiled to the literal empty
    pattern rather than the wildcard.
    """
    expected_match = entry.get("expected_match") or {}
    existing = expected_match.get(component)
    if existing is not None:
        return existing
    exactly_empty = entry.get("exactly_empty_components") or []
    if component in exactly_empty:
        return {"input": "", "groups": {}}
    return {"input": "", "groups": {"0": ""}}


def _normalize_expected_groups(expected_groups: dict[str, Any]) -> dict[str, Any]:
    """Translate ``null`` group values to "key absent".

    The WPT data is JSON, which has no ``undefined``. Optional-group misses
    are recorded as ``null`` and the JS harness translates them with
    ``expected_obj.groups[key] = undefined`` before the structural compare.
    Our :meth:`URLPattern.exec` omits unmatched optional groups entirely,
    so we strip null entries here to make the two dicts directly comparable.
    """
    return {k: v for k, v in expected_groups.items() if v is not None}


def _assert_component_match(
    actual: dict[str, Any] | None,
    expected: dict[str, Any],
    component: str,
) -> None:
    """Compare one component's exec result against the (auto-populated) expected."""
    assert actual is not None, f"expected {component} component result, got None"
    assert actual.get("input") == expected.get("input"), (
        f"exec().{component}.input: expected {expected.get('input')!r}, got {actual.get('input')!r}"
    )
    actual_groups = actual.get("groups") or {}
    expected_groups = _normalize_expected_groups(expected.get("groups") or {})
    assert actual_groups == expected_groups, (
        f"exec().{component}.groups: expected {expected_groups!r}, got {actual_groups!r}"
    )


# WPT cases that depend on the JS regex ``v`` flag's set operations
# (``[a&&b]`` / ``[a--b]``). With the stdlib ``re`` engine these patterns
# match the wrong characters; with the third-party ``regex`` engine
# (installed via the ``[regex]`` extra) they're handled correctly via the
# ``(?V1)`` dialect. Treated as ``xfail`` only when the active engine
# can't handle them.
_SET_OP_CASES = frozenset(
    {
        "350-pathname='/([[a-z]--a])'",
        "351-pathname='/([\\\\d&&[0-1]])'",
    }
)


def test_wpt_case(wpt_case: dict[str, Any], request: pytest.FixtureRequest) -> None:
    """Execute one parametrized WPT urlpattern conformance entry."""
    case_id = request.node.callspec.id
    # Some pytest pickle/display paths roundtrip backslashes by escaping them
    # once more — match against either the raw or the doubly-escaped form so
    # we stay robust to that.
    normalized_id = case_id.replace("\\\\", "\\")
    is_set_op_case = case_id in _SET_OP_CASES or normalized_id in _SET_OP_CASES
    engine = get_default_engine()
    if is_set_op_case and not engine.supports_set_operations:
        pytest.xfail(
            f"Active regex engine {engine.name!r} doesn't support JS v-flag "
            f"set operations; install `urlpattern[regex]` to enable: {case_id}",
        )

    # --- Constructor phase ------------------------------------------------------
    if wpt_case.get("expected_obj") == "error":
        with pytest.raises(TypeError):
            URLPattern(*wpt_case["pattern"])
        return

    pattern = URLPattern(*wpt_case["pattern"])

    # --- Compiled component pattern strings -------------------------------------
    for component in COMPONENTS:
        expected = _expected_component_pattern(wpt_case, component)
        actual = getattr(pattern, component)
        assert actual == expected, f"compiled pattern.{component!s}: expected {expected!r}, got {actual!r}"

    # --- Match phase ------------------------------------------------------------
    if wpt_case.get("expected_match") == "error":
        with pytest.raises(TypeError):
            pattern.test(*wpt_case["inputs"])
        with pytest.raises(TypeError):
            pattern.exec(*wpt_case["inputs"])
        return

    expected_match = wpt_case.get("expected_match")
    # JS truthiness: any object (including ``{}``) is truthy; only ``null``
    # / ``undefined`` / ``false`` is falsy here. The WPT JS harness writes
    # ``!!expected_match`` and an empty dict counts as a successful match.
    # Python's ``bool({})`` is False, so we explicitly distinguish "is an
    # object" from "is None/False".
    expected_test_result = expected_match is not None and expected_match is not False
    assert pattern.test(*wpt_case["inputs"]) is expected_test_result

    exec_result = pattern.exec(*wpt_case["inputs"])
    if expected_match is None or not isinstance(expected_match, dict):
        assert exec_result == expected_match
        return

    # Default the expected ``inputs`` echo to the test inputs themselves.
    expected_inputs = expected_match.get("inputs") or wpt_case["inputs"]
    actual_inputs = exec_result.inputs
    assert len(actual_inputs) == len(expected_inputs)
    for actual_input, expected_input in zip(actual_inputs, expected_inputs, strict=True):
        if isinstance(actual_input, str):
            assert actual_input == expected_input
            continue
        for component in COMPONENTS:
            assert actual_input.get(component) == expected_input.get(component), component

    for component in COMPONENTS:
        _assert_component_match(
            getattr(exec_result, component, None),
            _auto_populate_expected_component(wpt_case, component),
            component,
        )
