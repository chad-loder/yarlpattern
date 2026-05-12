"""WHATWG URLPattern §2.1.3–§2.1.5 — parts, options, and the pattern parser.

The parser consumes the token stream produced by :mod:`yarlpattern._tokenizer`
and emits a list of :class:`Part` records that describe, in order, what must
appear in a component string for the pattern to match. The token-stream
abstraction lets us cleanly separate lexical concerns (where a ``:name``
starts and ends, what's inside a balanced ``(...)``) from grammatical ones
(prefix/name/regexp/suffix grouping, modifier attachment).

This module also defines two small helpers — :func:`escape_regexp_string` and
:func:`generate_segment_wildcard_regexp` — that are shared with the
part-list→regex layer in §2.2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from yarlpattern._tokenizer import (
    Token,
    TokenizePolicy,
    TokenType,
    _is_valid_name_codepoint,
    tokenize,
)


class PartType(StrEnum):
    """Four kinds of part, per §2.1.3."""

    FIXED_TEXT = "fixed-text"
    REGEXP = "regexp"
    SEGMENT_WILDCARD = "segment-wildcard"
    FULL_WILDCARD = "full-wildcard"


class PartModifier(StrEnum):
    """Per-part modifier from §2.1.3."""

    NONE = "none"
    OPTIONAL = "optional"
    ZERO_OR_MORE = "zero-or-more"
    ONE_OR_MORE = "one-or-more"


@dataclass(slots=True)
class Part:
    """A single piece of a parsed pattern.

    Carries at most one matching group plus its surrounding fixed prefix /
    suffix and a modifier. See §2.1.3.
    """

    type: PartType
    value: str
    modifier: PartModifier
    name: str = ""
    prefix: str = ""
    suffix: str = ""


@dataclass(frozen=True, slots=True)
class Options:
    """Pattern-parser options from §2.1.4.

    The fields correspond to the spec's struct entries. They are frozen
    because a single ``Options`` instance is shared across all parts
    emitted from one parse, and we never need to mutate it.
    """

    delimiter_code_point: str = ""
    prefix_code_point: str = ""
    ignore_case: bool = False


EncodingCallback = Callable[[str], str]
"""Per §2.1.5 — validate and encode a literal text slice from a pattern.

Each URL component supplies its own callback so canonicalization runs while
the parser already knows which slices are literal vs. matching-group syntax.
"""


def identity_encoding_callback(input_: str) -> str:
    """Encoding callback that returns input unchanged.

    Useful as a default for tests and for the regexp-only path where no
    canonicalization is wanted.
    """
    return input_


# Per §2.2 "The full wildcard regexp value is the string '.*'.".
FULL_WILDCARD_REGEXP_VALUE: Final = ".*"


# Per §2.2 "escape a regexp string" — characters that need a leading backslash
# when emitting a literal into the generated regex. Pre-computed as a
# ``str.maketrans`` table: every special character maps to its escaped form,
# making the whole operation a single C-level :meth:`str.translate` call.
_REGEXP_ESCAPE_CHARS: Final = ".+*?^${}()[]|/\\"
_REGEXP_ESCAPE_TABLE: Final = str.maketrans({c: "\\" + c for c in _REGEXP_ESCAPE_CHARS})


def escape_regexp_string(input_: str) -> str:
    """Implement §2.2 "escape a regexp string".

    The spec asserts the input is ASCII; we don't enforce that at the call
    boundary because the canonicalization layer above us already guarantees
    it, and adding an assertion would only show up as overhead. If a future
    caller feeds non-ASCII text through here, the resulting regex will still
    be syntactically valid — just potentially semantically off, which we'd
    rather surface in the matcher than re-validate on every call.
    """
    return input_.translate(_REGEXP_ESCAPE_TABLE)


def generate_segment_wildcard_regexp(options: Options) -> str:
    """Per §2.1.5 "generate a segment wildcard regexp": ``[^<delim>]+?``."""
    return "[^" + escape_regexp_string(options.delimiter_code_point) + "]+?"


# §2.3 "escape a pattern string" — characters that must be backslash-escaped
# when emitting a literal text slice back into a pattern string. Smaller set
# than the regexp escape set: only pattern-syntax characters.
_PATTERN_ESCAPE_CHARS: Final = "+*?:{}()\\"
_PATTERN_ESCAPE_TABLE: Final = str.maketrans({c: "\\" + c for c in _PATTERN_ESCAPE_CHARS})


def escape_pattern_string(input_: str) -> str:
    """Implement §2.3 "escape a pattern string".

    Single C-level :meth:`str.translate` call. Like ``escape_regexp_string``
    we skip the ASCII assertion — the canonicalization layer is responsible
    for the input being ASCII before reaching here.
    """
    return input_.translate(_PATTERN_ESCAPE_TABLE)


# §2.3 "convert a modifier to a string" — single-character suffix per modifier.
# Kept as a module-level dict so the part-string serializer can do one lookup
# per part instead of an if-chain.
_MODIFIER_SUFFIX: Final[dict[PartModifier, str]] = {
    PartModifier.NONE: "",
    PartModifier.OPTIONAL: "?",
    PartModifier.ZERO_OR_MORE: "*",
    PartModifier.ONE_OR_MORE: "+",
}


def _modifier_suffix(modifier: PartModifier) -> str:
    return _MODIFIER_SUFFIX[modifier]


def parts_to_pattern_string(part_list: list[Part], options: Options) -> str:
    """Implement §2.3 "generate a pattern string".

    Inverse of :func:`parse_pattern_string` — turns a part list back into its
    canonical pattern-string form. This is what the URLPattern instance
    exposes via ``pattern.<component>``: not the user's raw input, but the
    parser's "normalized" understanding of it. That means ``/foo/(.*)``
    round-trips as ``/foo/*``, and ``/foo/([^\\/]+?)`` round-trips as
    ``/foo/:0`` — collapsing equivalent forms onto the shorter pattern
    syntax.

    The function is one tight loop with several "needs grouping" heuristics
    that handle ambiguity cases — e.g. ``/:a`` followed by literal ``b``
    would parse as the *name* ``:ab`` if emitted unwrapped, so we wrap it
    as ``{/:a}b``. Those heuristics live inline because each one references
    properties of the current / previous / next part.
    """
    pieces: list[str] = []
    append = pieces.append
    n = len(part_list)

    for index, part in enumerate(part_list):
        prev_part = part_list[index - 1] if index > 0 else None
        next_part = part_list[index + 1] if index < n - 1 else None

        # ---------------------------------------------------------- fixed-text
        if part.type is PartType.FIXED_TEXT:
            if part.modifier is PartModifier.NONE:
                append(escape_pattern_string(part.value))
                continue
            # Fixed text with a modifier must be wrapped so the modifier
            # binds to the right characters: ``{foo}?`` not ``foo?``.
            append("{")
            append(escape_pattern_string(part.value))
            append("}")
            append(_modifier_suffix(part.modifier))
            continue

        # ----------------------------------------------------- matching group
        # ``custom_name`` is true when the user wrote ``:foo``; false for the
        # numeric names the parser assigns to anonymous wildcards / regexps.
        custom_name = bool(part.name) and not part.name[0].isdecimal()

        needs_grouping = bool(part.suffix) or (bool(part.prefix) and part.prefix != options.prefix_code_point)

        # Disambiguation 1: a named segment wildcard ``:foo`` followed
        # immediately by a token that would extend the name needs explicit
        # ``{...}`` braces. ``:foobar`` would otherwise parse as one name.
        if (
            not needs_grouping
            and custom_name
            and part.type is PartType.SEGMENT_WILDCARD
            and part.modifier is PartModifier.NONE
            and next_part is not None
            and not next_part.prefix
            and not next_part.suffix
        ):
            if next_part.type is PartType.FIXED_TEXT:
                if next_part.value and _is_valid_name_codepoint(
                    next_part.value[0],
                    first=False,
                ):
                    needs_grouping = True
            elif next_part.name and next_part.name[0].isdecimal():
                # An adjacent anonymous wildcard would attach to this name.
                needs_grouping = True

        # Disambiguation 2: this part has no prefix but the previous
        # fixed-text ends with the prefix code point — without explicit
        # braces the prefix code point would auto-attach as this part's
        # prefix, changing semantics on re-parse.
        if (
            not needs_grouping
            and not part.prefix
            and prev_part is not None
            and prev_part.type is PartType.FIXED_TEXT
            and prev_part.value
            and prev_part.value[-1] == options.prefix_code_point
        ):
            needs_grouping = True

        # ---------------------------------------------------------- emit group
        if needs_grouping:
            append("{")
        append(escape_pattern_string(part.prefix))
        if custom_name:
            append(":")
            append(part.name)

        if part.type is PartType.REGEXP:
            append("(")
            append(part.value)
            append(")")
        elif part.type is PartType.SEGMENT_WILDCARD and not custom_name:
            # Anonymous segment wildcard: emit its full regex body so the
            # round-trip doesn't lose the semantics. Custom-named segment
            # wildcards just use ``:name`` and skip the regex body.
            append("(")
            append(generate_segment_wildcard_regexp(options))
            append(")")
        elif part.type is PartType.FULL_WILDCARD:
            # Collapse to the shorthand ``*`` only when there's no risk of
            # mis-parsing on re-tokenization. Otherwise emit the explicit
            # ``(.*)`` form so the part survives round-tripping unchanged.
            shorthand_ok = not custom_name and (
                prev_part is None
                or prev_part.type is PartType.FIXED_TEXT
                or prev_part.modifier is not PartModifier.NONE
                or needs_grouping
                or bool(part.prefix)
            )
            if shorthand_ok:
                append("*")
            else:
                append("(")
                append(FULL_WILDCARD_REGEXP_VALUE)
                append(")")

        # Suffix escape edge case: a named segment wildcard followed by a
        # suffix whose first char *would be* a valid name continuation needs
        # a literal backslash so the re-tokenizer doesn't swallow it into
        # the name.
        if (
            part.type is PartType.SEGMENT_WILDCARD
            and custom_name
            and part.suffix
            and _is_valid_name_codepoint(part.suffix[0], first=False)
        ):
            append("\\")
        append(escape_pattern_string(part.suffix))

        if needs_grouping:
            append("}")

        append(_modifier_suffix(part.modifier))

    return "".join(pieces)


@dataclass(slots=True)
class _PatternParser:
    """Internal state container mirroring the spec's "pattern parser" struct.

    Kept as a private class (rather than free function with locals) because
    the spec leans heavily on shared mutable state across helper algorithms
    — ``try to consume a token``, ``consume text``, ``maybe add a part from
    the pending fixed value``, and ``add a part`` all read and write parser
    fields. A class mirrors that structure 1:1 and makes the spec mapping
    obvious; the per-call overhead is small relative to the surrounding
    tokenizer + regex-compile work.
    """

    token_list: list[Token]
    encoding_callback: EncodingCallback
    segment_wildcard_regexp: str
    part_list: list[Part] = field(default_factory=list)
    pending_fixed_value: str = ""
    index: int = 0
    next_numeric_name: int = 0

    # ------------------------------------------------------------------ consume
    def try_to_consume_token(self, kind: TokenType) -> Token | None:
        """§2.1.5 "try to consume a token"."""
        # No assertion guard here: ``parse_pattern_string`` always feeds in a
        # token list ending with an END token, so ``index`` can't run past it.
        token = self.token_list[self.index]
        if token.kind is not kind:
            return None
        self.index += 1
        return token

    def try_to_consume_modifier_token(self) -> Token | None:
        """§2.1.5 "try to consume a modifier token" — matches ``?`` ``+`` ``*``."""
        token = self.try_to_consume_token(TokenType.OTHER_MODIFIER)
        if token is not None:
            return token
        return self.try_to_consume_token(TokenType.ASTERISK)

    def try_to_consume_regexp_or_wildcard_token(
        self,
        name_token: Token | None,
    ) -> Token | None:
        """§2.1.5 "try to consume a regexp or wildcard token".

        The bare ``*`` (asterisk) only counts as a wildcard *value* when
        there's no preceding name; with a name, ``*`` is a repetition
        modifier instead. This branch is what keeps that disambiguation
        local to one place.
        """
        token = self.try_to_consume_token(TokenType.REGEXP)
        if name_token is None and token is None:
            token = self.try_to_consume_token(TokenType.ASTERISK)
        return token

    def consume_required_token(self, kind: TokenType) -> Token:
        """§2.1.5 "consume a required token"."""
        result = self.try_to_consume_token(kind)
        if result is None:
            raise TypeError(
                f"URLPattern: expected token of type {kind.value!r} at parser index {self.index}",
            )
        return result

    def consume_text(self) -> str:
        """§2.1.5 "consume text" — concatenate adjacent ``char`` / ``escaped-char`` values."""
        # Accumulate via list + ''.join to avoid repeated O(n) string copies.
        # In practice the loop terminates within a few iterations per call, but
        # the loop's worst case (a long literal inside ``{...}``) is what the
        # str-list pattern is designed for.
        pieces: list[str] = []
        while True:
            token = self.try_to_consume_token(TokenType.CHAR)
            if token is None:
                token = self.try_to_consume_token(TokenType.ESCAPED_CHAR)
            if token is None:
                break
            pieces.append(token.value)
        return "".join(pieces)

    # --------------------------------------------------------------- emit parts
    def maybe_add_part_from_pending_fixed_value(self) -> None:
        """§2.1.5 "maybe add a part from the pending fixed value"."""
        if not self.pending_fixed_value:
            return
        encoded = self.encoding_callback(self.pending_fixed_value)
        self.pending_fixed_value = ""
        self.part_list.append(
            Part(type=PartType.FIXED_TEXT, value=encoded, modifier=PartModifier.NONE),
        )

    def add_part(
        self,
        prefix: str,
        name_token: Token | None,
        regexp_or_wildcard_token: Token | None,
        suffix: str,
        modifier_token: Token | None,
    ) -> None:
        """§2.1.5 "add a part" — the heart of parse-to-part conversion."""
        modifier = _modifier_from_token(modifier_token)

        # Case 1: bare ``{...}`` grouping with no matching group, no modifier
        # → fold the prefix back into the pending fixed value so it can merge
        # with surrounding literal text.
        if name_token is None and regexp_or_wildcard_token is None and modifier is PartModifier.NONE:
            self.pending_fixed_value += prefix
            return

        # Anything else means we need to flush pending fixed text first, then
        # emit the part itself.
        self.maybe_add_part_from_pending_fixed_value()

        # Case 2: ``{prefix}?`` — a modified literal group with no group inside.
        if name_token is None and regexp_or_wildcard_token is None:
            assert not suffix, "suffix must be empty when no matching group is present"
            if not prefix:
                return
            self.part_list.append(
                Part(
                    type=PartType.FIXED_TEXT,
                    value=self.encoding_callback(prefix),
                    modifier=modifier,
                ),
            )
            return

        # Case 3: there's an actual matching group. Resolve its regex body,
        # collapse to ``segment-wildcard`` / ``full-wildcard`` part types when
        # the body matches the canonical forms, and pick a name.
        regexp_value = _regexp_value_for_token(
            regexp_or_wildcard_token,
            self.segment_wildcard_regexp,
        )

        part_type = PartType.REGEXP
        if regexp_value == self.segment_wildcard_regexp:
            part_type = PartType.SEGMENT_WILDCARD
            regexp_value = ""
        elif regexp_value == FULL_WILDCARD_REGEXP_VALUE:
            part_type = PartType.FULL_WILDCARD
            regexp_value = ""

        name = ""
        if name_token is not None:
            name = name_token.value
        elif regexp_or_wildcard_token is not None:
            name = str(self.next_numeric_name)
            self.next_numeric_name += 1

        if self._is_duplicate_name(name):
            raise TypeError(f"URLPattern: duplicate matching group name {name!r}")

        encoded_prefix = self.encoding_callback(prefix)
        encoded_suffix = self.encoding_callback(suffix)
        self.part_list.append(
            Part(
                type=part_type,
                value=regexp_value,
                modifier=modifier,
                name=name,
                prefix=encoded_prefix,
                suffix=encoded_suffix,
            ),
        )

    def _is_duplicate_name(self, name: str) -> bool:
        """§2.1.5 "is a duplicate name".

        Linear scan is fine: real patterns rarely have more than a handful
        of named groups, so the constant-factor win of a ``set`` doesn't
        pay for itself on inputs this small.
        """
        return any(p.name == name for p in self.part_list)


def _modifier_from_token(modifier_token: Token | None) -> PartModifier:
    """Map a modifier token to its :class:`PartModifier` member."""
    if modifier_token is None:
        return PartModifier.NONE
    value = modifier_token.value
    if value == "?":
        return PartModifier.OPTIONAL
    if value == "*":
        return PartModifier.ZERO_OR_MORE
    if value == "+":
        return PartModifier.ONE_OR_MORE
    return PartModifier.NONE


def _regexp_value_for_token(
    regexp_or_wildcard_token: Token | None,
    segment_wildcard_regexp: str,
) -> str:
    """§2.1.5 "convert the regexp or wildcard token into a regular expression"."""
    if regexp_or_wildcard_token is None:
        return segment_wildcard_regexp
    if regexp_or_wildcard_token.kind is TokenType.ASTERISK:
        return FULL_WILDCARD_REGEXP_VALUE
    return regexp_or_wildcard_token.value


def parse_pattern_string(
    input_: str,
    options: Options,
    encoding_callback: EncodingCallback = identity_encoding_callback,
) -> list[Part]:
    """Parse *input_* into a :class:`Part` list per §2.1.5.

    Mirrors the spec algorithm exactly. The two top-level branches of the
    outer loop correspond to the two grouping forms the spec illustrates:

    * ``<prefix-char><name><regexp><modifier>`` — an inline matching group,
      possibly with a single literal prefix character (the spec's "automatic
      prefix" — only kicks in when that character equals
      ``options.prefix_code_point``).
    * ``<open><prefix-text><name><regexp><suffix-text><close><modifier>`` —
      an explicit ``{...}`` grouping, with arbitrary literal text on either
      side of the matching group and a required modifier afterwards.
    """
    parser = _PatternParser(
        token_list=tokenize(input_, TokenizePolicy.STRICT),
        encoding_callback=encoding_callback,
        segment_wildcard_regexp=generate_segment_wildcard_regexp(options),
    )

    while parser.index < len(parser.token_list):
        # Try the inline-group form first.
        char_token = parser.try_to_consume_token(TokenType.CHAR)
        name_token = parser.try_to_consume_token(TokenType.NAME)
        regexp_or_wildcard_token = parser.try_to_consume_regexp_or_wildcard_token(name_token)

        if name_token is not None or regexp_or_wildcard_token is not None:
            prefix = ""
            if char_token is not None:
                prefix = char_token.value
            # A prefix character that *isn't* the configured automatic prefix
            # gets folded into the pending fixed text instead of becoming a
            # part prefix. This is why pathname's ``/`` is treated specially
            # (the default prefix code point) while, say, ``-`` is not.
            if prefix and prefix != options.prefix_code_point:
                parser.pending_fixed_value += prefix
                prefix = ""
            parser.maybe_add_part_from_pending_fixed_value()
            modifier_token = parser.try_to_consume_modifier_token()
            parser.add_part(prefix, name_token, regexp_or_wildcard_token, "", modifier_token)
            continue

        # No matching group on this iteration — accumulate fixed text instead.
        fixed_token = char_token
        if fixed_token is None:
            fixed_token = parser.try_to_consume_token(TokenType.ESCAPED_CHAR)
        if fixed_token is not None:
            parser.pending_fixed_value += fixed_token.value
            continue

        # Try the explicit ``{...}`` grouping form.
        open_token = parser.try_to_consume_token(TokenType.OPEN)
        if open_token is not None:
            prefix = parser.consume_text()
            name_token = parser.try_to_consume_token(TokenType.NAME)
            regexp_or_wildcard_token = parser.try_to_consume_regexp_or_wildcard_token(name_token)
            suffix = parser.consume_text()
            parser.consume_required_token(TokenType.CLOSE)
            modifier_token = parser.try_to_consume_modifier_token()
            parser.add_part(prefix, name_token, regexp_or_wildcard_token, suffix, modifier_token)
            continue

        # Nothing else matched — must be the end token. Flush any pending
        # fixed text and require an END to close out cleanly.
        parser.maybe_add_part_from_pending_fixed_value()
        parser.consume_required_token(TokenType.END)
        break

    return parser.part_list
