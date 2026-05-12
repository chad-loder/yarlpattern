"""Port of ``reference/wpt/urlpattern/urlpattern-constructor.any.js``.

The WPT file is small (4 inline assertions) so we keep it as a hand-written
test rather than data-driven parametrization. Each test mirrors one
``test(() => { ... })`` block from the JS source.
"""

from __future__ import annotations

import pytest

from yarlpattern import URLPattern


def test_unclosed_token_paren() -> None:
    # WPT: `new URLPattern(new URL('https://example.org/%('))` → TypeError
    # The JS code coerces the URL object to its string form before passing it
    # to the URLPattern constructor; Python doesn't have an implicit URL
    # type, so we pass the equivalent string directly.
    with pytest.raises(TypeError):
        URLPattern("https://example.org/%(")


def test_unclosed_token_double_paren() -> None:
    # WPT: `new URLPattern(new URL('https://example.org/%(('))` → TypeError.
    with pytest.raises(TypeError):
        URLPattern("https://example.org/%((")


def test_unclosed_escape() -> None:
    # WPT: `new URLPattern('(\\')` → TypeError. The JS literal `'(\\'` is a
    # two-character string: open-paren and a single backslash. Python
    # ``'(\\'`` decodes to the same two-character string.
    with pytest.raises(TypeError):
        URLPattern("(\\")


def test_constructor_with_undefined() -> None:
    # WPT: `new URLPattern(undefined, undefined)` does NOT throw — the spec
    # treats both args as missing and produces an all-wildcards pattern.
    # Python equivalent: positional ``None`` for both.
    pat = URLPattern(None, None)
    # All components fall back to their default wildcard pattern.
    assert pat.protocol == "*"
    assert pat.pathname == "*"
