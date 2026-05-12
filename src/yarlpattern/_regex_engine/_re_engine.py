"""Stdlib :mod:`re` adapter — the always-available default engine.

The ``re`` module covers everything WHATWG URLPattern needs *except*:

* JS ``v``-flag set operations (``[a&&b]`` / ``[a--b]``). The ``re`` engine
  emits ``FutureWarning`` for these patterns and treats the operators as
  literal characters, producing matches that diverge from JS semantics.
  Users who need set-op fidelity install the ``[regex]`` extra.

This adapter handles two JS→Python translations that ``re`` rejects:

* ``[^]`` (JS "any code point including newline") → ``[\\s\\S]``
* ``(?<name>...)`` (JS named capture) → ``(?:...)`` (drop the name; URLPattern
  surfaces captures positionally via a parallel name list, so the name has
  no callback role)

These translations live in :mod:`yarlpattern._regex` and run *before* the
source string reaches the engine — they're not the engine's concern. The
adapter's job is just to flip on ``re.ASCII`` (for the JS-flavored
``\\d``/``\\w``/``\\s`` semantics) and pass through.
"""

from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yarlpattern._regex_engine.protocols import CompiledRegex


class StdlibReEngine:
    """The stdlib :mod:`re` engine adapter — used by default."""

    name = "re"
    supports_set_operations = False

    def compile(self, pattern: str, *, ignore_case: bool) -> CompiledRegex:
        flags = re.ASCII
        if ignore_case:
            flags |= re.IGNORECASE
        try:
            # Python 3.12+ emits ``FutureWarning`` for ``[a&&b]`` / ``[a--b]``
            # (reserved for future set-intersection / set-difference syntax
            # that JS already supports under the ``v`` flag). The engine
            # treats the operators as literal characters; the warning would
            # otherwise pollute the test output without giving the user any
            # actionable fix.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                return re.compile(pattern, flags)
        except re.error as exc:
            # JS regex syntax that Python ``re`` rejects (bad escapes,
            # unsupported constructs, etc.) — surface as TypeError so the
            # spec-mandated "construction throws on invalid regex" path
            # works regardless of which engine first noticed the syntax.
            msg = f"URLPattern: invalid regex {pattern!r}: {exc}"
            raise TypeError(msg) from exc


def get_engine() -> StdlibReEngine:
    """Return the singleton stdlib-``re`` engine instance."""
    return _SINGLETON


_SINGLETON = StdlibReEngine()
