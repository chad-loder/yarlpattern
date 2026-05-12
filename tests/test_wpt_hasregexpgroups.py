"""Port of ``reference/wpt/urlpattern/resources/urlpattern-hasregexpgroups-tests.js``.

The JS file is one big ``test()`` block iterating per-component patterns;
we expand it into ``pytest.mark.parametrize`` cases so each failing
combination shows up individually in the test output.

The spec rule: ``hasRegExpGroups`` returns true iff any component's part
list contains a part whose type is ``regexp`` and whose value is not the
component's segment-wildcard or full-wildcard regexp value. That is,
custom-regex parts (named or anonymous) count; segment wildcards (``:foo``)
and the full wildcard (``*``) do not.
"""

from __future__ import annotations

import pytest

from yarlpattern import URLPattern

# Components that accept richer pattern syntax — pathname, hostname, etc.
# Protocol and port are syntactically narrower and the WPT corpus skips
# the "mixed text + regexp" rows for them.
_ALL_COMPONENTS = (
    "protocol",
    "username",
    "password",
    "hostname",
    "port",
    "pathname",
    "search",
    "hash",
)
_RICH_COMPONENTS = tuple(c for c in _ALL_COMPONENTS if c not in ("protocol", "port"))


def test_match_everything_pattern_has_no_regexp_groups() -> None:
    # Empty dict → every component defaults to ``*`` (full wildcard). No
    # custom-regex parts anywhere → ``hasRegExpGroups`` must be false.
    assert URLPattern({}).has_regexp_groups is False


@pytest.mark.parametrize("component", _ALL_COMPONENTS)
def test_wildcard_has_no_regexp_groups(component: str) -> None:
    assert URLPattern({component: "*"}).has_regexp_groups is False


@pytest.mark.parametrize("component", _ALL_COMPONENTS)
def test_segment_wildcard_has_no_regexp_groups(component: str) -> None:
    # ``:foo`` is a segment wildcard — its part type is "segment-wildcard",
    # not "regexp". Names alone do not count.
    assert URLPattern({component: ":foo"}).has_regexp_groups is False


@pytest.mark.parametrize("component", _ALL_COMPONENTS)
def test_optional_segment_wildcard_has_no_regexp_groups(component: str) -> None:
    assert URLPattern({component: ":foo?"}).has_regexp_groups is False


@pytest.mark.parametrize("component", _ALL_COMPONENTS)
def test_named_regexp_group_has_regexp_groups(component: str) -> None:
    # ``:foo(hi)`` — named regexp; the part type is "regexp" with custom body.
    assert URLPattern({component: ":foo(hi)"}).has_regexp_groups is True


@pytest.mark.parametrize("component", _ALL_COMPONENTS)
def test_anonymous_regexp_group_has_regexp_groups(component: str) -> None:
    # ``(hi)`` — anonymous regexp. Auto-assigned numeric name, but the part
    # type is still "regexp" with custom body, so the flag must be true.
    assert URLPattern({component: "(hi)"}).has_regexp_groups is True


@pytest.mark.parametrize("component", _RICH_COMPONENTS)
def test_mixed_fixed_text_and_wildcard_has_no_regexp_groups(component: str) -> None:
    # ``a-{:hello}-z-*-a`` mixes fixed text, group, segment-wildcard, and
    # full-wildcard parts — none of which are custom-regexp.
    assert URLPattern({component: "a-{:hello}-z-*-a"}).has_regexp_groups is False


@pytest.mark.parametrize("component", _RICH_COMPONENTS)
def test_mixed_fixed_text_and_regexp_groups_has_regexp_groups(component: str) -> None:
    # ``a-(hi)-z-(lo)-a`` mixes fixed text with two anonymous regexp groups.
    assert URLPattern({component: "a-(hi)-z-(lo)-a"}).has_regexp_groups is True


def test_complex_pathname_without_regexp() -> None:
    pat = URLPattern({"pathname": "/a/:foo/:baz?/b/*"})
    assert pat.has_regexp_groups is False


def test_complex_pathname_with_regexp() -> None:
    pat = URLPattern({"pathname": "/a/:foo/:baz([a-z]+)?/b/*"})
    assert pat.has_regexp_groups is True
