"""Hand-coded tests for the canonical examples in the WHATWG URLPattern Standard.

The WPT corpus exercises 469 conformance cases by construction, but those entries
are terse JSON tuples. The examples *written into the prose* of the
[WHATWG URLPattern Standard](https://urlpattern.spec.whatwg.org/) — the ones a
human reads when they first land on the spec — deserve a separate, narrated
test surface so that:

  1. Regressions on the spec's headline examples surface as named failures.
  2. Readers can land in this file and see exactly the patterns and inputs
     the standard authors used to illustrate the feature.

Each example is annotated with its section number and a one-line description.
"""

from __future__ import annotations

import pytest

from yarlpattern import URLPattern


class TestSpecExample12Shop:
    """WHATWG URLPattern Standard §1.2 example.

    Pattern: ``http{s}?://{:subdomain.}?shop.example/products/:id([0-9]+)#reviews``

    The spec uses this example to illustrate:
      - optional protocol suffix (``http{s}?``)
      - optional named hostname segment with trailing dot (``{:subdomain.}?``)
      - regex-constrained named pathname group (``:id([0-9]+)``)
      - literal-required hash component (``#reviews``)
    """

    PATTERN = "http{s}?://{:subdomain.}?shop.example/products/:id([0-9]+)#reviews"

    @pytest.fixture(scope="class")
    def pattern(self) -> URLPattern:
        return URLPattern(self.PATTERN)

    @pytest.mark.parametrize(
        ("url", "subdomain", "id_"),
        [
            ("https://shop.example/products/74205#reviews", None, "74205"),
            ("https://kathryn@voyager.shop.example/products/74656#reviews", "voyager", "74656"),
            ("http://insecure.shop.example/products/1701#reviews", "insecure", "1701"),
        ],
    )
    def test_positive_matches(
        self,
        pattern: URLPattern,
        url: str,
        subdomain: str | None,
        id_: str,
    ) -> None:
        result = pattern.exec(url)
        assert result is not None, f"expected match for {url!r}"
        assert result.pathname["groups"]["id"] == id_
        assert result.hostname["groups"].get("subdomain") == subdomain

    @pytest.mark.parametrize(
        ("url", "reason"),
        [
            (
                "https://shop.example/products/74205",
                "missing #reviews fragment",
            ),
            (
                "https://shop.example:8443/products/74205#reviews",
                "explicit port disallowed",
            ),
            (
                "https://shop.example/products/74205?ref=hn#reviews",
                "search component disallowed",
            ),
            (
                "https://shop.example/products/abc#reviews",
                "non-digit id rejected by [0-9]+",
            ),
        ],
    )
    def test_negative_matches(
        self,
        pattern: URLPattern,
        url: str,
        reason: str,
    ) -> None:
        assert pattern.exec(url) is None, f"expected no match ({reason}): {url!r}"
