# API reference

Auto-extracted from yarlpattern's docstrings by
[mkdocstrings](https://mkdocstrings.github.io). Items are grouped by
audience: the primary public API, the escape helpers most callers
eventually need, and the lower-level building blocks reserved for
advanced use.

## Primary API

The 95% surface: one class, one result type, one tuple of component
names.

::: yarlpattern.URLPattern
    options:
      show_source: false
      show_root_heading: true
      members_order: source

::: yarlpattern.URLPatternResult
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.COMPONENTS
    options:
      show_source: false
      show_root_heading: true

## Escape helpers

When you're building a pattern from a string whose contents might
contain pattern metacharacters (`:`, `*`, `(`, `)`, `{`, `}`), escape
it first.

::: yarlpattern.escape_pattern_string
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.escape_regexp_string
    options:
      show_source: false
      show_root_heading: true

## Low-level building blocks

The spec-aligned tokenizer, parser, and regex generator are public
because they're useful for tools that compose URLPatterns
programmatically — a route-table linter, a static analyzer for
overlapping patterns, a code generator emitting JavaScript URLPattern
strings from a Python source of truth.

Most users never need these.

### Tokenizer

::: yarlpattern.tokenize
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.Token
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.TokenType
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.TokenizePolicy
    options:
      show_source: false
      show_root_heading: true

### Parts

A *part* is one syntactic element of a pattern: a literal text run,
a named segment-wildcard, a regex group, or a full wildcard.

::: yarlpattern.parse_pattern_string
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.parts_to_pattern_string
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.Part
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.PartType
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.PartModifier
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.Options
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.EncodingCallback
    options:
      show_source: false
      show_root_heading: true

### Regex generation

::: yarlpattern.parts_to_regex
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.generate_segment_wildcard_regexp
    options:
      show_source: false
      show_root_heading: true

::: yarlpattern.FULL_WILDCARD_REGEXP_VALUE
    options:
      show_source: false
      show_root_heading: true
