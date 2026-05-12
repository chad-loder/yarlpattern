"""Unit tests for the §2.1.5 pattern parser.

Like the tokenizer tests, these isolate each spec sub-algorithm so a single
regression doesn't have to be hunted through the integration suite. The
expected part lists were cross-checked against the urlpattern-polyfill JS
reference (running the same input through ``new URLPattern({pathname: ...})``
and inspecting the resulting compiled parts).
"""

from __future__ import annotations

import pytest

from yarlpattern import (
    Options,
    Part,
    PartModifier,
    PartType,
    escape_regexp_string,
    generate_segment_wildcard_regexp,
    parse_pattern_string,
)

# A "pathname-like" options bundle — the most common in real patterns and the
# one whose behavior is exercised by the bulk of WPT entries. The other
# components mostly differ by changing ``delimiter_code_point`` /
# ``prefix_code_point``, so picking pathname for the unit suite covers the
# parser's interesting branches without combinatorially exploding the cases.
PATHNAME = Options(delimiter_code_point="/", prefix_code_point="/")
EMPTY = Options()


def _fixed(value: str, modifier: PartModifier = PartModifier.NONE) -> Part:
    return Part(type=PartType.FIXED_TEXT, value=value, modifier=modifier)


def _seg(name: str, prefix: str = "", suffix: str = "", modifier: PartModifier = PartModifier.NONE) -> Part:
    return Part(
        type=PartType.SEGMENT_WILDCARD,
        value="",
        modifier=modifier,
        name=name,
        prefix=prefix,
        suffix=suffix,
    )


def _full(name: str, prefix: str = "", suffix: str = "", modifier: PartModifier = PartModifier.NONE) -> Part:
    return Part(
        type=PartType.FULL_WILDCARD,
        value="",
        modifier=modifier,
        name=name,
        prefix=prefix,
        suffix=suffix,
    )


def _re(name: str, value: str, prefix: str = "", suffix: str = "", modifier: PartModifier = PartModifier.NONE) -> Part:
    return Part(
        type=PartType.REGEXP,
        value=value,
        modifier=modifier,
        name=name,
        prefix=prefix,
        suffix=suffix,
    )


# --------------------------------------------------------------------- helpers


def test_escape_regexp_string_escapes_specials() -> None:
    # Spot-check each special character listed in §2.2.
    assert escape_regexp_string("a.b") == r"a\.b"
    assert escape_regexp_string("/") == r"\/"
    assert escape_regexp_string(r"\\") == r"\\\\"
    assert escape_regexp_string("(a+b)*?[c|d]{e}") == r"\(a\+b\)\*\?\[c\|d\]\{e\}"


def test_escape_regexp_string_leaves_non_specials_alone() -> None:
    assert escape_regexp_string("abc123") == "abc123"
    assert escape_regexp_string("") == ""


def test_generate_segment_wildcard_regexp_default() -> None:
    # With an empty delimiter, the spec produces ``[^]+?`` — odd-looking but
    # what the algorithm yields verbatim; the matcher takes it as-is.
    assert generate_segment_wildcard_regexp(EMPTY) == "[^]+?"


def test_generate_segment_wildcard_regexp_pathname() -> None:
    assert generate_segment_wildcard_regexp(PATHNAME) == r"[^\/]+?"


# ---------------------------------------------------------------- empty + chars


def test_empty_pattern_emits_nothing() -> None:
    assert parse_pattern_string("", PATHNAME) == []


def test_plain_literal_becomes_one_fixed_text_part() -> None:
    # All adjacent chars collapse into a single fixed-text part — that's the
    # whole point of pending_fixed_value.
    assert parse_pattern_string("foo", PATHNAME) == [_fixed("foo")]


def test_escaped_chars_merge_into_fixed_text() -> None:
    # The backslash itself was already stripped by the tokenizer, so the
    # parser just sees an ``escaped-char`` token with the bare ``*`` value
    # and folds it into the surrounding literal.
    assert parse_pattern_string(r"a\*b", PATHNAME) == [_fixed("a*b")]


# ----------------------------------------------------------------- named group


def test_named_group_with_prefix() -> None:
    # ``/`` is the configured automatic prefix code point, so it attaches to
    # the part as ``prefix`` rather than merging into a preceding fixed-text.
    assert parse_pattern_string("/:foo", PATHNAME) == [_seg("foo", prefix="/")]


def test_named_group_prefix_thats_not_the_auto_prefix_folds_into_fixed_text() -> None:
    # ``-`` is not the prefix code point, so it merges into a preceding
    # fixed-text part. The named group then has no part-level prefix.
    assert parse_pattern_string("-:foo", PATHNAME) == [
        _fixed("-"),
        _seg("foo"),
    ]


def test_named_group_with_optional_modifier() -> None:
    assert parse_pattern_string("/:foo?", PATHNAME) == [
        _seg("foo", prefix="/", modifier=PartModifier.OPTIONAL),
    ]


def test_named_group_with_one_or_more_modifier() -> None:
    assert parse_pattern_string("/:foo+", PATHNAME) == [
        _seg("foo", prefix="/", modifier=PartModifier.ONE_OR_MORE),
    ]


def test_named_group_with_zero_or_more_modifier() -> None:
    assert parse_pattern_string("/:foo*", PATHNAME) == [
        _seg("foo", prefix="/", modifier=PartModifier.ZERO_OR_MORE),
    ]


def test_named_group_with_custom_regexp() -> None:
    parts = parse_pattern_string(r"/:year(\d+)", PATHNAME)
    assert parts == [_re("year", r"\d+", prefix="/")]


def test_named_group_with_regexp_that_equals_segment_wildcard_collapses() -> None:
    # If the explicit regex body is exactly the segment-wildcard regex for
    # this options bundle, the part type collapses to SEGMENT_WILDCARD with
    # an empty value — the matcher gets cheaper and serialization round-trips.
    body = generate_segment_wildcard_regexp(PATHNAME)
    parts = parse_pattern_string(f"/:foo({body})", PATHNAME)
    assert parts == [_seg("foo", prefix="/")]


def test_named_group_with_dotstar_collapses_to_full_wildcard() -> None:
    parts = parse_pattern_string("/:foo(.*)", PATHNAME)
    assert parts == [_full("foo", prefix="/")]


# ---------------------------------------------------------------- bare wildcard


def test_asterisk_alone_emits_full_wildcard_with_numeric_name() -> None:
    parts = parse_pattern_string("/*", PATHNAME)
    assert parts == [_full("0", prefix="/")]


def test_two_asterisks_get_incrementing_numeric_names() -> None:
    parts = parse_pattern_string("/*/*", PATHNAME)
    assert parts[0].name == "0"
    assert parts[1].name == "1"


def test_bare_regexp_with_no_name_gets_numeric_name() -> None:
    parts = parse_pattern_string(r"(\d+)", PATHNAME)
    assert parts == [_re("0", r"\d+")]


# ------------------------------------------------------------ {...} group form


def test_explicit_group_with_no_modifier_folds_into_fixed_text() -> None:
    # Spec: a ``{...}`` with no name, no regex, no modifier just buffers the
    # inner text. So ``{foo}`` is equivalent to ``foo``.
    assert parse_pattern_string("{foo}", PATHNAME) == [_fixed("foo")]


def test_explicit_group_with_modifier_emits_modified_fixed_text() -> None:
    assert parse_pattern_string("{foo}?", PATHNAME) == [
        _fixed("foo", modifier=PartModifier.OPTIONAL),
    ]


def test_explicit_group_with_prefix_name_suffix() -> None:
    # ``{a:foo(bar)b}?`` exercises the prefix+name+regex+suffix+modifier path.
    parts = parse_pattern_string("{a:foo(bar)b}?", PATHNAME)
    assert parts == [_re("foo", "bar", prefix="a", suffix="b", modifier=PartModifier.OPTIONAL)]


def test_explicit_group_unclosed_is_error() -> None:
    with pytest.raises(TypeError, match="expected token of type 'close'"):
        parse_pattern_string("{foo", PATHNAME)


# ----------------------------------------------------------------- duplicate names


def test_duplicate_named_group_is_rejected() -> None:
    with pytest.raises(TypeError, match="duplicate matching group name"):
        parse_pattern_string("/:foo/:foo", PATHNAME)


def test_duplicate_numeric_name_through_two_anonymous_groups_is_fine() -> None:
    # Numeric names are assigned in order, so two anonymous groups get "0"
    # and "1" — never collide.
    parts = parse_pattern_string(r"(\d+)/(\d+)", PATHNAME)
    assert [p.name for p in parts] == ["0", "1"]


# ----------------------------------------------------------- encoding callback


def test_encoding_callback_applied_to_fixed_text() -> None:
    # The callback runs over every literal slice the parser flushes to the
    # part list. Using uppercase as a stand-in for canonicalization here.
    parts = parse_pattern_string("foo/bar", PATHNAME, str.upper)
    assert parts == [_fixed("FOO/BAR")]


def test_encoding_callback_applied_to_prefix_and_suffix() -> None:
    parts = parse_pattern_string("{a:foo(bar)b}?", PATHNAME, str.upper)
    assert parts[0].prefix == "A"
    assert parts[0].suffix == "B"
    # The regex body itself is *not* run through the callback — it's already
    # constrained to ASCII regex syntax by the tokenizer.
    assert parts[0].value == "bar"


def test_encoding_callback_not_applied_to_group_name() -> None:
    parts = parse_pattern_string("/:foo", PATHNAME, str.upper)
    assert parts[0].name == "foo"  # not "FOO" — names are pattern syntax


# ----------------------------------------------------------- realistic samples


def test_realistic_blog_pattern() -> None:
    # The spec's own running example.
    parts = parse_pattern_string(r"/blog/:year(\d+)/:month(\d+)", PATHNAME)
    assert parts == [
        _fixed("/blog"),
        _re("year", r"\d+", prefix="/"),
        _re("month", r"\d+", prefix="/"),
    ]


def test_realistic_optional_group_with_explicit_delimiter() -> None:
    # The whole point of ``{...}`` is to keep the leading ``/`` *out* of the
    # group's optional prefix — so it lands in the preceding fixed-text and
    # the matching ``/products`` requires a literal trailing slash.
    # Contrast this with ``/products/:id?`` where the ``/`` *is* the group's
    # prefix and disappears together with the group when ``id`` is absent.
    parts = parse_pattern_string("/products/{:id}?", PATHNAME)
    assert parts == [
        _fixed("/products/"),
        _seg("id", modifier=PartModifier.OPTIONAL),
    ]


def test_realistic_wildcard_tail() -> None:
    parts = parse_pattern_string("/products/*", PATHNAME)
    assert parts == [
        _fixed("/products"),
        _full("0", prefix="/"),
    ]
