"""Structural protocols for pluggable regex engines.

URLPattern's compile + match pipeline is parameterized by a regex engine —
an object that knows how to translate WHATWG-flavored regex source into a
matcher with the right semantics. Two adapters ship in-tree:

* :mod:`yarlpattern._regex_engine._re_engine` — stdlib :mod:`re` (default).
  Covers the common case; falls short on the JS ``v`` flag's set operations
  (``[a&&b]`` / ``[a--b]``) because Python's ``re`` doesn't implement them.
* :mod:`yarlpattern._regex_engine._regex_engine` — the third-party ``regex``
  package (Matthew Barnett's). Activated via the ``[regex]`` install extra.
  Adds set-op support through the ``(?V1)`` flag, and otherwise stays
  drop-in-compatible.

The Protocol surface here is deliberately tiny — three callables in total —
so adding a future engine (e.g. a PyO3 binding to a JS-grade regex engine)
is a single adapter module away. All three protocols are
:func:`typing.runtime_checkable` so duck-typed engines work without
inheritance ceremony.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CompiledMatch(Protocol):
    """The subset of ``re.Match`` / ``regex.Match`` URLPattern needs.

    Both stdlib and third-party match objects satisfy this structurally;
    no wrapping is performed on the hot path.
    """

    def groups(self) -> tuple[str | None, ...]:
        """Captured groups in document order. Unmatched groups → ``None``."""
        ...

    def start(self, group: int = 0, /) -> int:
        """Inclusive start offset of *group* in the matched string."""
        ...

    def end(self, group: int = 0, /) -> int:
        """Exclusive end offset of *group* in the matched string."""
        ...


@runtime_checkable
class CompiledRegex(Protocol):
    """The subset of ``re.Pattern`` / ``regex.Pattern`` URLPattern needs.

    URLPattern only ever calls ``.fullmatch`` (anchored) — the spec
    compiles every component pattern to a ``^...$`` regex.
    """

    def fullmatch(self, string: str, /) -> CompiledMatch | None:
        """Return a :class:`CompiledMatch` iff *string* fully matches."""
        ...


@runtime_checkable
class RegexEngine(Protocol):
    """Compile WHATWG-style regex source into a :class:`CompiledRegex`.

    The engine's job is to (a) make the JS-flavored regex source emitted by
    URLPattern's part-to-regex compiler legal in its target regex flavor and
    (b) honor the structural flags URLPattern asks for. Anything beyond that
    — set operations, named-group quirks, group disposition — is the
    adapter's responsibility to translate or document as a gap.
    """

    @property
    def name(self) -> str:
        """Short identifier (e.g. ``"re"``, ``"regex"``). Used in error messages."""
        ...

    @property
    def supports_set_operations(self) -> bool:
        """Whether ``[a&&b]`` / ``[a--b]`` are interpreted as JS ``v`` flag.

        URLPattern uses this flag to mark engine-gap tests as ``xfail`` when
        the active engine doesn't support those constructs.
        """
        ...

    def compile(self, pattern: str, *, ignore_case: bool) -> CompiledRegex:
        """Compile *pattern* with WHATWG semantics.

        Adapters are responsible for:

        * Mapping URLPattern's "ASCII-only ``\\d``/``\\w``/``\\s``" requirement
          onto whatever flag the underlying engine uses.
        * Translating JS-only constructs that the underlying engine rejects
          (e.g. JS named-capture syntax ``(?<name>...)`` in stdlib ``re``).
        * Suppressing engine-specific deprecation warnings that the user
          can't action.

        Construction failure must raise :class:`TypeError`.
        """
        ...
