"""Hand-coded tests for the canonical examples on MDN's ``URLPattern`` page.

These mirror the worked examples shown on
[developer.mozilla.org/en-US/docs/Web/API/URL_Pattern_API](https://developer.mozilla.org/en-US/docs/Web/API/URL_Pattern_API)
and its companion guides. They are deliberately a small, narrated set —
the WPT corpus carries the conformance load; this file documents the
*pedagogical* surface readers actually encounter first.
"""

from __future__ import annotations

import pytest

from yarlpattern import URLPattern


class TestMdnMultipleComponents:
    """MDN guide: "Using multiple components".

    Constructs a URLPattern from a dict literal covering protocol, username,
    password, hostname, and pathname components simultaneously, then exec's it
    against a fully-populated URL.
    """

    @pytest.fixture(scope="class")
    def pattern(self) -> URLPattern:
        return URLPattern(
            {
                "protocol": "http{s}?",
                "username": ":user?",
                "password": ":pass?",
                "hostname": "{:subdomain.}*example.com",
                "pathname": "/product/:action*",
            }
        )

    def test_match_extracts_every_component_group(self, pattern: URLPattern) -> None:
        url = "http://foo:bar@sub.example.com/product/view?q=12345"
        result = pattern.exec(url)
        assert result is not None
        assert result.username["groups"]["user"] == "foo"
        assert result.password["groups"]["pass"] == "bar"
        assert result.hostname["groups"]["subdomain"] == "sub"
        assert result.pathname["groups"]["action"] == "view"

    def test_match_with_no_optional_components_present(self, pattern: URLPattern) -> None:
        # Per the MDN walkthrough, the optional username/password/subdomain
        # are absent here and the pathname's ``:action*`` matches zero
        # segments. Note: the ``*`` modifier in path-to-regexp absorbs its
        # preceding ``/`` separator, so the zero-match form is ``/product``
        # — not ``/product/``.
        url = "https://example.com/product"
        result = pattern.exec(url)
        assert result is not None
        # When an optional named group does not participate in the match,
        # WHATWG URLPattern omits the key from ``groups`` entirely (rather
        # than returning ``None``). Use ``.get()`` to express "absent or
        # empty".
        assert result.username["groups"].get("user") in (None, "")
        assert result.password["groups"].get("pass") in (None, "")
        assert result.hostname["groups"].get("subdomain") in (None, "")
        assert result.pathname["groups"].get("action") in (None, "")


class TestMdnSubdomainWildcard:
    """MDN guide: "Custom prefix and suffix modifiers".

    ``{:subdomain.}*example.com`` matches any number of dotted subdomain
    labels, including zero. The named group inside the explicit ``{ ... }``
    grouping captures whatever subdomain prefix was matched.
    """

    @pytest.fixture(scope="class")
    def pattern(self) -> URLPattern:
        return URLPattern({"hostname": "{:subdomain.}*example.com"})

    @pytest.mark.parametrize(
        ("hostname", "expected_subdomain"),
        [
            ("example.com", None),
            ("foo.example.com", "foo"),
            ("foo.bar.example.com", "foo.bar"),
            ("a.b.c.example.com", "a.b.c"),
        ],
    )
    def test_positive(
        self,
        pattern: URLPattern,
        hostname: str,
        expected_subdomain: str | None,
    ) -> None:
        result = pattern.exec({"hostname": hostname})
        assert result is not None, f"expected match for {hostname!r}"
        assert result.hostname["groups"].get("subdomain") == expected_subdomain

    @pytest.mark.parametrize(
        "hostname",
        [
            ".example.com",  # leading dot — empty label
            "example.org",  # wrong eTLD
            "example.com.",  # trailing dot
        ],
    )
    def test_negative(self, pattern: URLPattern, hostname: str) -> None:
        assert not pattern.test({"hostname": hostname}), f"expected no match for {hostname!r}"


class TestMdnRegexConstrainedGroup:
    r"""MDN guide: "Pattern syntax — regex groups".

    The pathname pattern ``/books/:id(\d+)`` constrains the ``:id`` group to
    one or more decimal digits using an inline regex tail.
    """

    @pytest.fixture(scope="class")
    def pattern(self) -> URLPattern:
        return URLPattern({"pathname": r"/books/:id(\d+)"})

    @pytest.mark.parametrize(
        ("url", "expected_id"),
        [
            ("https://x.example/books/42", "42"),
            ("https://x.example/books/0", "0"),
            ("https://x.example/books/9876543210", "9876543210"),
        ],
    )
    def test_positive(self, pattern: URLPattern, url: str, expected_id: str) -> None:
        result = pattern.exec(url)
        assert result is not None
        assert result.pathname["groups"]["id"] == expected_id

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.example/books/abc",  # letters disallowed
            "https://x.example/books/42a",  # trailing letter
            "https://x.example/books/",  # empty id rejected by + quantifier
            "https://x.example/books/-1",  # signs not in [0-9]
        ],
    )
    def test_negative(self, pattern: URLPattern, url: str) -> None:
        assert pattern.exec(url) is None, f"expected no match: {url!r}"
