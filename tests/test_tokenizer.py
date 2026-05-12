"""Unit tests for the §2.1.2 tokenizer.

These exercise each individual production from the spec algorithm. The big
WPT integration suite in ``test_wpt.py`` catches end-to-end conformance; these
catch regressions in a single token kind quickly.
"""

from __future__ import annotations

import pytest

from yarlpattern._tokenizer import (
    Token,
    TokenizePolicy,
    TokenType,
    tokenize,
)


def _kinds(tokens: list[Token]) -> list[TokenType]:
    return [t.kind for t in tokens]


def _values(tokens: list[Token]) -> list[str]:
    return [t.value for t in tokens]


def test_empty_input_emits_only_end_token() -> None:
    out = tokenize("")
    assert out == [Token(TokenType.END, 0, "")]


def test_plain_char_run() -> None:
    out = tokenize("abc")
    assert _kinds(out) == [
        TokenType.CHAR,
        TokenType.CHAR,
        TokenType.CHAR,
        TokenType.END,
    ]
    assert _values(out) == ["a", "b", "c", ""]
    assert [t.index for t in out] == [0, 1, 2, 3]


def test_single_character_syntax_tokens() -> None:
    out = tokenize("{}*+?")
    assert _kinds(out) == [
        TokenType.OPEN,
        TokenType.CLOSE,
        TokenType.ASTERISK,
        TokenType.OTHER_MODIFIER,
        TokenType.OTHER_MODIFIER,
        TokenType.END,
    ]
    assert _values(out) == ["{", "}", "*", "+", "?", ""]


def test_escaped_char_strips_backslash_from_value() -> None:
    out = tokenize(r"\*")
    assert out[0].kind == TokenType.ESCAPED_CHAR
    # value is the escaped code point only — the backslash is consumed
    assert out[0].value == "*"
    assert out[0].index == 0


def test_trailing_backslash_is_strict_error() -> None:
    with pytest.raises(TypeError, match="trailing backslash"):
        tokenize("foo\\")


def test_trailing_backslash_is_invalid_char_in_lenient_mode() -> None:
    out = tokenize("foo\\", TokenizePolicy.LENIENT)
    assert _kinds(out) == [
        TokenType.CHAR,
        TokenType.CHAR,
        TokenType.CHAR,
        TokenType.INVALID_CHAR,
        TokenType.END,
    ]


def test_named_group_simple() -> None:
    out = tokenize(":foo")
    assert out[0] == Token(TokenType.NAME, 0, "foo")
    assert out[0].index == 0
    # the END token's index is *past* the consumed name, not just past the ':'
    assert out[-1] == Token(TokenType.END, 4, "")


def test_named_group_with_digits_after_first_char() -> None:
    out = tokenize(":foo123")
    assert out[0] == Token(TokenType.NAME, 0, "foo123")


def test_named_group_first_char_cannot_be_digit() -> None:
    # ':' followed by '0' (not a valid IdentifierStart) → strict error
    with pytest.raises(TypeError, match="not followed by a valid name"):
        tokenize(":0bad")


def test_named_group_first_char_cannot_be_digit_lenient() -> None:
    out = tokenize(":0bad", TokenizePolicy.LENIENT)
    assert out[0] == Token(TokenType.INVALID_CHAR, 0, ":")


def test_named_group_with_underscore_and_dollar() -> None:
    out = tokenize(":_$x")
    assert out[0] == Token(TokenType.NAME, 0, "_$x")


def test_named_group_stops_at_punctuation() -> None:
    out = tokenize(":foo/bar")
    assert out[0] == Token(TokenType.NAME, 0, "foo")
    assert out[1] == Token(TokenType.CHAR, 4, "/")


def test_regexp_simple() -> None:
    out = tokenize("(abc)")
    assert out[0] == Token(TokenType.REGEXP, 0, "abc")
    assert out[-1] == Token(TokenType.END, 5, "")


def test_regexp_with_escaped_char_inside() -> None:
    # \) inside the regex must not close the group; the parser must accept
    # the escape and continue paren-counting after it.
    out = tokenize(r"(\))")
    assert out[0].kind == TokenType.REGEXP
    assert out[0].value == r"\)"


def test_regexp_nested_must_be_noncapturing() -> None:
    out = tokenize("((?:x))")
    assert out[0].kind == TokenType.REGEXP
    assert out[0].value == "(?:x)"


def test_regexp_nested_capturing_is_rejected_strict() -> None:
    with pytest.raises(TypeError, match="malformed regexp"):
        tokenize("((x))")


def test_regexp_nested_capturing_is_invalid_char_lenient() -> None:
    out = tokenize("((x))", TokenizePolicy.LENIENT)
    assert out[0] == Token(TokenType.INVALID_CHAR, 0, "(")


def test_regexp_empty_body_rejected() -> None:
    with pytest.raises(TypeError):
        tokenize("()")


def test_regexp_leading_question_mark_rejected() -> None:
    # Per spec, the regex body cannot *start* with '?'.
    with pytest.raises(TypeError):
        tokenize("(?abc)")


def test_regexp_unbalanced_paren_rejected() -> None:
    with pytest.raises(TypeError):
        tokenize("(abc")


def test_regexp_non_ascii_rejected() -> None:
    with pytest.raises(TypeError):
        tokenize("(café)")


def test_regexp_non_ascii_lenient() -> None:
    out = tokenize("(café)", TokenizePolicy.LENIENT)
    assert out[0] == Token(TokenType.INVALID_CHAR, 0, "(")
    # the rest of the input is then re-tokenized as plain chars
    assert _kinds(out)[1:6] == [TokenType.CHAR] * 5


def test_mixed_pattern_smoke() -> None:
    out = tokenize("/:year(\\d+)/:month(\\d+)")
    assert _kinds(out) == [
        TokenType.CHAR,  # /
        TokenType.NAME,  # :year
        TokenType.REGEXP,  # (\d+)
        TokenType.CHAR,  # /
        TokenType.NAME,  # :month
        TokenType.REGEXP,  # (\d+)
        TokenType.END,
    ]
    assert out[1].value == "year"
    assert out[2].value == r"\d+"
    assert out[4].value == "month"
    assert out[5].value == r"\d+"


def test_indexes_are_first_code_point_positions() -> None:
    # Index field must point to the START of the token, not the end. This is
    # easy to get wrong because the spec's "add a token" updates the cursor
    # *after* recording the index.
    out = tokenize("a:foo*")
    assert [t.index for t in out] == [0, 1, 5, 6]


def test_optional_group_shape() -> None:
    out = tokenize("{:foo}?")
    assert _kinds(out) == [
        TokenType.OPEN,
        TokenType.NAME,
        TokenType.CLOSE,
        TokenType.OTHER_MODIFIER,
        TokenType.END,
    ]
