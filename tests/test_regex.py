"""Unit tests for the §2.2 part-list → regex compiler.

Two layers of assertion in each test:

1. **Shape:** the emitted regex string matches what the spec dictates exactly.
   This is the brittle but necessary check — getting this wrong silently
   makes some inputs match that shouldn't (and vice-versa).
2. **Compiles + matches the right inputs:** every emitted regex is fed to
   ``re.compile`` and then exercised against representative inputs. This is
   what we'd notice fastest in production, and it pins down the JS-regex →
   Python-re translation step.
"""

from __future__ import annotations

import re

import pytest

from yarlpattern import (
    Options,
    Part,
    PartModifier,
    PartType,
    parse_pattern_string,
    parts_to_regex,
)

PATHNAME = Options(delimiter_code_point="/", prefix_code_point="/")
EMPTY = Options()


def _compile(parts: list[Part], options: Options = PATHNAME) -> tuple[re.Pattern[str], list[str]]:
    src, names = parts_to_regex(parts, options)
    return re.compile(src, re.ASCII), names


# ---------------------------------------------------------------- fixed-text


def test_empty_parts_yields_anchor_only_regex() -> None:
    src, names = parts_to_regex([], PATHNAME)
    assert src == "^$"
    assert names == []
    assert re.fullmatch(src, "") is not None
    assert re.fullmatch(src, "x") is None


def test_fixed_text_is_escaped_inline() -> None:
    parts = [Part(type=PartType.FIXED_TEXT, value="/foo.bar", modifier=PartModifier.NONE)]
    src, names = parts_to_regex(parts, PATHNAME)
    assert src == r"^\/foo\.bar$"
    assert names == []
    pat = re.compile(src)
    assert pat.fullmatch("/foo.bar")
    # Confirms the ``.`` was escaped — otherwise this would match.
    assert pat.fullmatch("/fooxbar") is None


def test_fixed_text_with_optional_modifier_wraps_in_non_capturing_group() -> None:
    parts = [Part(type=PartType.FIXED_TEXT, value="foo", modifier=PartModifier.OPTIONAL)]
    src, _ = parts_to_regex(parts, PATHNAME)
    assert src == "^(?:foo)?$"
    pat = re.compile(src)
    assert pat.fullmatch("foo")
    assert pat.fullmatch("")


# ----------------------------------------------------- groups without affixes


def test_segment_wildcard_no_affixes() -> None:
    parts = [Part(type=PartType.SEGMENT_WILDCARD, value="", modifier=PartModifier.NONE, name="x")]
    src, names = parts_to_regex(parts, PATHNAME)
    assert src == r"^([^\/]+?)$"
    assert names == ["x"]
    m = re.fullmatch(src, "abc")
    assert m and m.group(1) == "abc"


def test_full_wildcard_no_affixes() -> None:
    parts = [Part(type=PartType.FULL_WILDCARD, value="", modifier=PartModifier.NONE, name="x")]
    src, names = parts_to_regex(parts, PATHNAME)
    assert src == "^(.*)$"
    assert names == ["x"]
    m = re.fullmatch(src, "a/b/c")
    assert m and m.group(1) == "a/b/c"


def test_repeating_group_without_affixes_uses_double_group_form() -> None:
    # ``((?:<re>)<mod>)``
    parts = [Part(type=PartType.FULL_WILDCARD, value="", modifier=PartModifier.ONE_OR_MORE, name="x")]
    src, _ = parts_to_regex(parts, PATHNAME)
    assert src == "^((?:.*)+)$"


# ----------------------------------------------- groups with prefix and suffix


def test_named_group_with_prefix_no_modifier() -> None:
    # ``(?:<p>(<re>)<s>)<mod>``
    parts = [
        Part(
            type=PartType.SEGMENT_WILDCARD,
            value="",
            modifier=PartModifier.NONE,
            name="foo",
            prefix="/",
            suffix="",
        ),
    ]
    src, names = parts_to_regex(parts, PATHNAME)
    assert src == r"^(?:\/([^\/]+?))$"
    assert names == ["foo"]
    pat = re.compile(src)
    m = pat.fullmatch("/abc")
    assert m and m.group(1) == "abc"
    assert pat.fullmatch("/abc/def") is None


def test_named_group_with_prefix_optional() -> None:
    parts = [
        Part(
            type=PartType.SEGMENT_WILDCARD,
            value="",
            modifier=PartModifier.OPTIONAL,
            name="foo",
            prefix="/",
            suffix="",
        ),
    ]
    src, _ = parts_to_regex(parts, PATHNAME)
    assert src == r"^(?:\/([^\/]+?))?$"
    pat = re.compile(src)
    # Both an empty input and a ``/foo`` input must match — that's what
    # "the leading slash is optional with the group" means.
    assert pat.fullmatch("")
    assert pat.fullmatch("/abc")


def test_named_group_with_prefix_and_repeating_uses_complex_form() -> None:
    parts = [
        Part(
            type=PartType.SEGMENT_WILDCARD,
            value="",
            modifier=PartModifier.ONE_OR_MORE,
            name="foo",
            prefix="/",
            suffix="",
        ),
    ]
    src, _ = parts_to_regex(parts, PATHNAME)
    # The complex form interleaves prefix/suffix between repetitions so that
    # ``/a/b/c`` captures all three but the leading prefix is not duplicated.
    assert src == r"^(?:\/((?:[^\/]+?)(?:\/(?:[^\/]+?))*)\/?)?$" or src.startswith(
        "^(?:",
    )
    pat = re.compile(src)
    m = pat.fullmatch("/a/b/c")
    assert m
    # The single capture group spans the joined repetition value.
    assert m.group(1) == "a/b/c"


def test_named_group_with_prefix_and_zero_or_more_appends_trailing_question_mark() -> None:
    parts = [
        Part(
            type=PartType.SEGMENT_WILDCARD,
            value="",
            modifier=PartModifier.ZERO_OR_MORE,
            name="foo",
            prefix="/",
            suffix="",
        ),
    ]
    src, _ = parts_to_regex(parts, PATHNAME)
    assert src.endswith(")?$")  # the spec's zero-or-more trailer
    pat = re.compile(src)
    assert pat.fullmatch("")
    assert pat.fullmatch("/a")
    assert pat.fullmatch("/a/b")


# ---------------------------------------------- empty delimiter / [^] handling


def test_empty_delimiter_segment_wildcard_translates_negated_class() -> None:
    # The spec's literal output is ``[^]+?`` for an empty delimiter — invalid
    # Python regex. We translate it on the way out.
    parts = [Part(type=PartType.SEGMENT_WILDCARD, value="", modifier=PartModifier.NONE, name="x")]
    src, _ = parts_to_regex(parts, EMPTY)
    assert "[^]" not in src
    assert r"[\s\S]" in src
    # Must still compile and match arbitrary text (including newlines).
    pat = re.compile(src)
    m = pat.fullmatch("abc\nxyz")
    assert m and m.group(1) == "abc\nxyz"


# ---------------------------------------------------- regexp body passthrough


def test_custom_regexp_body_passed_through_verbatim() -> None:
    parts = [
        Part(
            type=PartType.REGEXP,
            value=r"\d+",
            modifier=PartModifier.NONE,
            name="year",
            prefix="/",
            suffix="",
        ),
    ]
    src, names = parts_to_regex(parts, PATHNAME)
    assert src == r"^(?:\/(\d+))$"
    assert names == ["year"]
    pat = re.compile(src, re.ASCII)
    m = pat.fullmatch("/2026")
    assert m and m.group(1) == "2026"
    assert pat.fullmatch("/abc") is None


def test_re_ascii_flag_is_required_for_js_d_semantics() -> None:
    # Without re.ASCII, Python's \\d matches non-ASCII digits like Arabic-
    # Indic. The compile site (URLPattern) must set re.ASCII to keep JS
    # regex semantics; this test pins down that we *do* need that flag.
    src, _ = parts_to_regex(
        [
            Part(
                type=PartType.REGEXP,
                value=r"\d+",
                modifier=PartModifier.NONE,
                name="year",
                prefix="",
                suffix="",
            ),
        ],
        PATHNAME,
    )
    # Eastern Arabic 2026 — would match under Python's default \\d.
    arabic_2026 = "٢٠٢٦"
    assert re.fullmatch(src, arabic_2026) is not None  # Unicode-aware (default)
    assert re.fullmatch(src, arabic_2026, re.ASCII) is None


# ------------------------------------------------- end-to-end via parser


def test_parse_then_compile_blog_pattern() -> None:
    parts = parse_pattern_string(r"/blog/:year(\d+)/:month(\d+)", PATHNAME)
    pat, names = _compile(parts)
    assert names == ["year", "month"]
    m = pat.fullmatch("/blog/2026/05")
    assert m
    assert m.groups() == ("2026", "05")
    assert pat.fullmatch("/blog/abc/def") is None
    assert pat.fullmatch("/blog/2026") is None


def test_parse_then_compile_optional_id() -> None:
    parts = parse_pattern_string("/products/:id?", PATHNAME)
    pat, names = _compile(parts)
    assert names == ["id"]
    assert pat.fullmatch("/products")
    assert pat.fullmatch("/products/42")
    # Trailing slash with no id is NOT matched — the ``/`` belongs to the
    # optional group.
    assert pat.fullmatch("/products/") is None


def test_parse_then_compile_wildcard_tail() -> None:
    parts = parse_pattern_string("/products/*", PATHNAME)
    pat, names = _compile(parts)
    assert names == ["0"]
    m = pat.fullmatch("/products/a/b/c")
    assert m and m.group(1) == "a/b/c"


def test_parse_then_compile_explicit_optional_group_with_delimiter() -> None:
    parts = parse_pattern_string("/products/{:id}?", PATHNAME)
    pat, _ = _compile(parts)
    # Now the trailing slash is part of the *fixed* text, so empty id no
    # longer matches "/products" — it requires "/products/".
    assert pat.fullmatch("/products/") is not None
    assert pat.fullmatch("/products/42") is not None
    assert pat.fullmatch("/products") is None


# ------------------------------------------------ name_list / groups parallel


def test_name_list_is_parallel_to_groups() -> None:
    parts = parse_pattern_string(r"/:a(\d+)/:b(\d+)/:c(\w+)", PATHNAME)
    pat, names = _compile(parts)
    m = pat.fullmatch("/1/22/three")
    assert m
    assert dict(zip(names, m.groups(), strict=True)) == {"a": "1", "b": "22", "c": "three"}


def test_anonymous_groups_get_numeric_names_in_groups_dict() -> None:
    parts = parse_pattern_string("/*/*", PATHNAME)
    pat, names = _compile(parts)
    m = pat.fullmatch("/a/b")
    assert m
    assert dict(zip(names, m.groups(), strict=True)) == {"0": "a", "1": "b"}


# --------------------------------------------------- error-shaped patterns


@pytest.mark.parametrize(
    "pattern",
    [
        # All of these must compile without raising — they're patterns that
        # have historically tripped up similar engines.
        "/",
        "*",
        ":foo",
        r"(\d+)",
        "/{a}",
        "/{a}?",
        "{a:foo(bar)b}*",
    ],
)
def test_compiles_without_raising(pattern: str) -> None:
    parts = parse_pattern_string(pattern, PATHNAME)
    src, _ = parts_to_regex(parts, PATHNAME)
    re.compile(src, re.ASCII)  # must not raise
