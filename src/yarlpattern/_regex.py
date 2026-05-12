"""WHATWG URLPattern §2.2 — generate a regular expression from a part list.

This module implements the §2.2 algorithm. The output is a regex source
string plus a parallel list of group names — the spec deliberately does not
use named capture groups for path-to-regexp compatibility reasons, so we
do the same and use positional captures with a side list.

JS-regex → Python-re translation
--------------------------------

The spec is defined against ECMAScript regular expressions. Almost all of
the syntax it emits is also valid Python ``re`` syntax, with one specific
exception: ``[^]`` (empty negated character class) is valid in JS and means
"any code point including newlines", but is a syntax error in Python ``re``.
The spec's :func:`generate_segment_wildcard_regexp` produces ``[^]+?`` when
the options' delimiter is the empty string, which is the only place the
construct appears.

We translate ``[^]`` → ``[\\s\\S]`` at the very end of regex generation. That
is the standard JS-to-Python regex equivalence for "match any character" and
has the same semantics. The substitution is safe even if it appears inside
a user-supplied regex body because ``[^]`` would be a syntax error in
Python ``re`` either way — we're only rescuing a regex that would otherwise
fail to compile.

We also rely on the regex being compiled with :data:`re.ASCII` so that
``\\d``, ``\\w``, and ``\\s`` behave the way JS regex specifies (ASCII-only)
rather than Python's Unicode-aware default. The compile site, not this
module, is responsible for setting the flag.
"""

from __future__ import annotations

import re as _re
from typing import Final

from yarlpattern._parts import (
    FULL_WILDCARD_REGEXP_VALUE,
    Options,
    Part,
    PartModifier,
    PartType,
    escape_regexp_string,
    generate_segment_wildcard_regexp,
)

# Single-character modifier suffix for each ``PartModifier``. Pre-built as a
# plain ``dict`` because the lookup runs once per part during compilation;
# ``dict.get`` is faster than the ``StrEnum`` ``.value`` round-trip you'd get
# from an ``if/elif`` chain.
_MODIFIER_TO_STRING: Final[dict[PartModifier, str]] = {
    PartModifier.NONE: "",
    PartModifier.OPTIONAL: "?",
    PartModifier.ZERO_OR_MORE: "*",
    PartModifier.ONE_OR_MORE: "+",
}


def _convert_modifier_to_string(modifier: PartModifier) -> str:
    """§2.2 "convert a modifier to a string"."""
    return _MODIFIER_TO_STRING[modifier]


def parts_to_regex(
    part_list: list[Part],
    options: Options,
) -> tuple[str, list[str]]:
    """Implement §2.2 "generate a regular expression and name list".

    Returns ``(regex_source, name_list)``. ``regex_source`` is anchored
    (``^...$``) and uses positional capture groups in document order.
    ``name_list`` has one entry per capture group, in the same order — caller
    is expected to zip these with ``re.Match.groups()`` to build a names dict.

    The body is a tight ``list.append`` + ``"".join`` loop rather than
    ``result += ...`` because long pattern strings with many parts can
    otherwise quadratic on CPython.
    """
    pieces: list[str] = ["^"]
    append = pieces.append
    name_list: list[str] = []
    seg_wildcard_regexp = generate_segment_wildcard_regexp(options)

    for part in part_list:
        # ---------------------------------------------------------- fixed-text
        if part.type is PartType.FIXED_TEXT:
            escaped = escape_regexp_string(part.value)
            if part.modifier is PartModifier.NONE:
                append(escaped)
            else:
                append("(?:")
                append(escaped)
                append(")")
                append(_convert_modifier_to_string(part.modifier))
            continue

        # ----------------------------------------------------- matching group
        # Per spec assertion — a non-fixed-text part always has a name.
        # We add it to the parallel name list whether or not the regex body
        # itself ends up empty.
        name_list.append(part.name)

        # Resolve the effective regex body for this group.
        regexp_value = part.value
        if part.type is PartType.SEGMENT_WILDCARD:
            regexp_value = seg_wildcard_regexp
        elif part.type is PartType.FULL_WILDCARD:
            regexp_value = FULL_WILDCARD_REGEXP_VALUE

        mod_str = _convert_modifier_to_string(part.modifier)
        no_prefix_no_suffix = not part.prefix and not part.suffix

        # Case 1: no prefix/suffix.
        if no_prefix_no_suffix:
            if part.modifier in (PartModifier.NONE, PartModifier.OPTIONAL):
                # ``(<re>)<mod>``
                append("(")
                append(regexp_value)
                append(")")
                append(mod_str)
            else:
                # Repeating w/o prefix/suffix: ``((?:<re>)<mod>)``.
                # The outer capture sees the whole repetition so $1 is the
                # joined match, not just the last iteration — matches JS.
                append("((?:")
                append(regexp_value)
                append(")")
                append(mod_str)
                append(")")
            continue

        # Case 2: non-repeating w/ prefix and/or suffix.
        # ``(?:<prefix>(<re>)<suffix>)<mod>``
        if part.modifier in (PartModifier.NONE, PartModifier.OPTIONAL):
            append("(?:")
            append(escape_regexp_string(part.prefix))
            append("(")
            append(regexp_value)
            append(")")
            append(escape_regexp_string(part.suffix))
            append(")")
            append(mod_str)
            continue

        # Case 3: repeating w/ prefix and/or suffix — the complex form.
        # ``(?:<p>((?:<re>)(?:<s><p>(?:<re>))*)<s>)`` with an optional ``?``
        # at the very end when modifier is zero-or-more.
        escaped_prefix = escape_regexp_string(part.prefix)
        escaped_suffix = escape_regexp_string(part.suffix)
        append("(?:")
        append(escaped_prefix)
        append("((?:")
        append(regexp_value)
        append(")(?:")
        append(escaped_suffix)
        append(escaped_prefix)
        append("(?:")
        append(regexp_value)
        append("))*)")
        append(escaped_suffix)
        append(")")
        if part.modifier is PartModifier.ZERO_OR_MORE:
            append("?")

    append("$")
    result = "".join(pieces)
    return _translate_js_regex_to_python(result), name_list


# JS named-capture syntax ``(?<name>...)``. Python uses ``(?P<name>...)`` and
# rejects the JS form as a syntax error. We strip user-supplied named groups
# entirely by rewriting to ``(?:`` — dropping the name is safe because the
# URLPattern spec exposes captures positionally via its parallel name_list,
# not through user-chosen group names.
#
# The lookahead ``(?![=!])`` is crucial: ``(?<=...)`` and ``(?<!...)`` are
# zero-width lookbehind assertions, valid in *both* JS and Python regex and
# must pass through untouched.
_JS_NAMED_CAPTURE: _re.Pattern[str] = _re.compile(r"\(\?<(?![=!])[A-Za-z_][A-Za-z0-9_]*>")


def _translate_js_regex_to_python(regex: str) -> str:
    """Patch JS-regex constructs that Python ``re`` rejects.

    Two translations:

    * ``[^]`` (JS's "any char including newline") → ``[\\s\\S]``. Python
      ``re`` rejects ``[^]`` as a syntax error. The substitution is global
      so user-supplied regex bodies that use the construct also compile.

    * ``(?<name>...)`` (JS named capture) → ``(?:...)``. The named-capture
      form is invalid in Python ``re`` (which uses ``?P<name>``); rather
      than try to preserve the name, we strip the capture entirely because
      URLPattern surfaces captures via its own positional name list.
      Lookbehind assertions ``(?<=...)`` / ``(?<!...)`` are explicitly
      preserved.
    """
    if "[^]" in regex:
        regex = regex.replace("[^]", r"[\s\S]")
    if "(?<" in regex:
        regex = _JS_NAMED_CAPTURE.sub("(?:", regex)
    return regex
