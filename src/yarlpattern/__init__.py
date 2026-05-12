"""Pure-Python implementation of the WHATWG URLPattern Standard.

Public surface modelled after :mod:`yarl` — a single immutable class that
exposes per-component pattern strings as attributes and offers ``test`` /
``exec`` matchers. See https://urlpattern.spec.whatwg.org/ for the standard.
"""

from __future__ import annotations

from yarlpattern._parts import (
    FULL_WILDCARD_REGEXP_VALUE,
    EncodingCallback,
    Options,
    Part,
    PartModifier,
    PartType,
    escape_pattern_string,
    escape_regexp_string,
    generate_segment_wildcard_regexp,
    parse_pattern_string,
    parts_to_pattern_string,
)
from yarlpattern._pattern import COMPONENTS, URLPattern, URLPatternResult
from yarlpattern._regex import parts_to_regex
from yarlpattern._tokenizer import Token, TokenizePolicy, TokenType, tokenize
from yarlpattern._version import __version__

__all__ = [
    "COMPONENTS",
    "FULL_WILDCARD_REGEXP_VALUE",
    "EncodingCallback",
    "Options",
    "Part",
    "PartModifier",
    "PartType",
    "Token",
    "TokenType",
    "TokenizePolicy",
    "URLPattern",
    "URLPatternResult",
    "__version__",
    "escape_pattern_string",
    "escape_regexp_string",
    "generate_segment_wildcard_regexp",
    "parse_pattern_string",
    "parts_to_pattern_string",
    "parts_to_regex",
    "tokenize",
]
