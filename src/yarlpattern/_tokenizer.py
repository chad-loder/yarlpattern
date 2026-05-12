"""WHATWG URLPattern §2.1.1–2.1.2 — tokens and tokenizer.

This module implements the spec's tokenizer, optimized for CPython 3.12+:

* All loop state lives in function locals (not on a class) so PEP 659 can
  specialize the bytecode and so attribute lookups don't dominate the inner
  loop.
* Tokens are :class:`NamedTuple` instances — C-implemented, three-field shape,
  near-zero overhead vs. plain tuples but with named access at call sites.
* Helper sub-routines from the spec (``add a token``, ``add a token with
  default length`` etc.) are *inlined* rather than wrapped as closures, since
  closures with ``nonlocal`` defeat the interpreter's local-variable fast path.

The spec defines the tokenizer over Unicode *code points*; Python's ``str``
is already a sequence of code points (PEP 393), so ``input[i]`` and
``len(input)`` line up directly with the spec's ``code point substring`` and
``code point length`` operations. No UTF-16 surrogate gymnastics are needed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, NamedTuple


class TokenType(StrEnum):
    """One of the ten token kinds in §2.1.1.

    ``StrEnum`` members compare equal to their string values, which keeps spec
    text and our checks in lockstep without forcing every comparison to go
    through enum machinery.
    """

    OPEN = "open"
    CLOSE = "close"
    REGEXP = "regexp"
    NAME = "name"
    CHAR = "char"
    ESCAPED_CHAR = "escaped-char"
    OTHER_MODIFIER = "other-modifier"
    ASTERISK = "asterisk"
    END = "end"
    INVALID_CHAR = "invalid-char"


class TokenizePolicy(StrEnum):
    """Tokenize policy from §2.1.2.

    ``strict`` raises :class:`TypeError` on the first malformed token. The
    constructor-string parser uses ``lenient`` so that ambiguous protocol /
    pathname boundaries (e.g. the ``:`` in ``https://host:port``) can be
    resolved by later phases rather than rejected at tokenization.
    """

    STRICT = "strict"
    LENIENT = "lenient"


class Token(NamedTuple):
    """Tokenizer output entry.

    ``index`` is the position of the first code point of the token in the
    original input. ``value`` is the substring of the input that the token
    represents — for ``escaped-char`` / ``regexp`` / ``name`` this is the
    payload *without* the surrounding syntax characters (``\\``, ``()``, ``:``).
    """

    kind: TokenType
    # ``index`` shadows ``tuple.index`` (a method); the field name comes from
    # the spec so we keep it and silence the false-positive override warning.
    index: int  # type: ignore[assignment]
    value: str


# Fast-path identifier tables. URLPattern uses ECMAScript IdentifierStart /
# IdentifierPart for ``:name`` validation; in practice well over 99% of real-
# world patterns use only ASCII identifier characters, so we resolve those
# inline with a frozenset membership check (O(1), no Python-level call) and
# only fall back to the slower Unicode path for non-ASCII code points.
_ASCII_NAME_START: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$",
)
_ASCII_NAME_CONTINUE: Final[frozenset[str]] = _ASCII_NAME_START | frozenset("0123456789")

# ZWNJ / ZWJ are explicitly allowed in IdentifierPart by ECMA-262 even though
# they are not in Unicode ID_Continue. We special-case them at the boundary so
# the slow path can lean on ``str.isidentifier`` for everything else.
_ZWNJ: Final = "‌"
_ZWJ: Final = "‍"


def _is_valid_name_codepoint(cp: str, *, first: bool) -> bool:
    """Implement §2.1.2 "is a valid name code point".

    Fast path (ASCII): frozenset membership. Slow path (non-ASCII): defer to
    :meth:`str.isidentifier`, which uses Unicode XID_Start / XID_Continue —
    the Unicode-stability-normalized version of ID_Start / ID_Continue. The
    XID variants are a strict subset of ID_*, so any name we *accept* is also
    valid under the spec; the rare patterns where a code point is in ID_* but
    not XID_* (a handful of historical Unicode chars) would be rejected here
    but accepted by a browser. We accept that tradeoff for now to stay in
    pure stdlib; if it shows up in WPT we can wire in the `unicodedata` PUA
    table directly.
    """
    if first:
        if cp in _ASCII_NAME_START:
            return True
        if ord(cp) < 0x80:
            return False
        return cp.isidentifier()
    if cp in _ASCII_NAME_CONTINUE:
        return True
    if ord(cp) < 0x80:
        return False
    if cp in (_ZWNJ, _ZWJ):
        return True
    # ``isidentifier`` on a single non-ASCII char checks XID_Start. To check
    # XID_Continue we prepend an ASCII letter (definitely a start) so the test
    # becomes "is this a valid identifier continuation?".
    return ("a" + cp).isidentifier()


def tokenize(input_: str, policy: TokenizePolicy = TokenizePolicy.STRICT) -> list[Token]:
    """Tokenize *input_* per §2.1.2.

    Returns the token list including the trailing ``end`` token. The token's
    ``index`` field uses the spec convention — position of the *first* code
    point of the token. ``value`` is the payload substring.

    On a malformed token, raises :class:`TypeError` under ``strict`` and emits
    an ``invalid-char`` token under ``lenient`` (matching the constructor-
    string parser's expectations).
    """
    tokens: list[Token] = []
    append = tokens.append  # hoist to local; saves a LOAD_ATTR per token
    n = len(input_)
    index = 0  # token start position (spec: tokenizer's "index")
    strict = policy is TokenizePolicy.STRICT

    while index < n:
        cp = input_[index]
        next_index = index + 1

        # ---- single-character tokens ---------------------------------------
        if cp == "*":
            append(Token(TokenType.ASTERISK, index, cp))
            index = next_index
            continue
        if cp in {"+", "?"}:
            append(Token(TokenType.OTHER_MODIFIER, index, cp))
            index = next_index
            continue
        if cp == "{":
            append(Token(TokenType.OPEN, index, cp))
            index = next_index
            continue
        if cp == "}":
            append(Token(TokenType.CLOSE, index, cp))
            index = next_index
            continue

        # ---- escape sequence: \ <char> -------------------------------------
        if cp == "\\":
            if next_index >= n:
                # backslash at EOF — spec: "if index equals input length − 1"
                if strict:
                    raise TypeError(
                        f"URLPattern: trailing backslash at index {index}",
                    )
                append(Token(TokenType.INVALID_CHAR, index, cp))
                index = next_index
                continue
            escaped_value_pos = next_index
            # consume the escaped code point itself
            next_index += 1
            append(
                Token(
                    TokenType.ESCAPED_CHAR,
                    index,
                    input_[escaped_value_pos:next_index],
                ),
            )
            index = next_index
            continue

        # ---- :name ----------------------------------------------------------
        if cp == ":":
            name_start = next_index
            name_pos = name_start
            while name_pos < n:
                if not _is_valid_name_codepoint(
                    input_[name_pos],
                    first=(name_pos == name_start),
                ):
                    break
                name_pos += 1
            if name_pos <= name_start:
                if strict:
                    raise TypeError(
                        f"URLPattern: ':' at index {index} not followed by a valid name",
                    )
                append(Token(TokenType.INVALID_CHAR, index, cp))
                index = next_index
                continue
            append(
                Token(
                    TokenType.NAME,
                    index,
                    input_[name_start:name_pos],
                ),
            )
            index = name_pos
            continue

        # ---- (regexp) -------------------------------------------------------
        if cp == "(":
            consumed, payload, ok = _consume_regexp(input_, next_index, n)
            if not ok:
                if strict:
                    raise TypeError(
                        f"URLPattern: malformed regexp group starting at index {index}",
                    )
                append(Token(TokenType.INVALID_CHAR, index, cp))
                index = next_index
                continue
            append(Token(TokenType.REGEXP, index, payload))
            index = consumed
            continue

        # ---- ordinary character --------------------------------------------
        append(Token(TokenType.CHAR, index, cp))
        index = next_index

    append(Token(TokenType.END, index, ""))
    return tokens


def _consume_regexp(input_: str, start: int, n: int) -> tuple[int, str, bool]:
    """Scan a ``(...)`` regexp group from *start* (just past the opening paren).

    Returns ``(end_index_just_past_closing_paren, payload, ok)``. Mirrors the
    inner loop of §2.1.2 around ``U+0028 (`(`)`` — balanced-paren tracking
    with ASCII-only enforcement, leading-``?`` rejection, and the requirement
    that any *nested* ``(`` must be immediately followed by ``?`` (i.e. a
    non-capturing or assertion group).

    The regexp body is returned **as-is**; we never parse inside it. That's
    why a Python ``re`` engine can pick it up later without translation:
    the spec already constrains it to a JS-regex-compatible ASCII subset
    that is also valid Python ``re`` syntax for the constructs URLPattern
    permits.
    """
    depth = 1
    pos = start
    while pos < n:
        ch = input_[pos]
        ch_ord = ord(ch)

        if ch_ord >= 0x80:
            return 0, "", False
        if pos == start and ch == "?":
            return 0, "", False

        if ch == "\\":
            if pos >= n - 1:
                return 0, "", False
            nxt = input_[pos + 1]
            if ord(nxt) >= 0x80:
                return 0, "", False
            pos += 2
            continue

        if ch == ")":
            depth -= 1
            if depth == 0:
                # §2.1.2: "If regexp length is zero, run process a
                # tokenizing error." An empty body ``()`` is malformed.
                if pos == start:
                    return 0, "", False
                return pos + 1, input_[start:pos], True
            pos += 1
            continue

        if ch == "(":
            depth += 1
            # Any nested ``(`` must be ``(?...`` — capturing groups are
            # forbidden by the spec so the resulting regex always matches in
            # the same group numbering as URLPattern expects.
            if pos >= n - 1 or input_[pos + 1] != "?":
                return 0, "", False
            pos += 1
            continue

        pos += 1

    # ran off the end without finding a closing paren
    return 0, "", False
