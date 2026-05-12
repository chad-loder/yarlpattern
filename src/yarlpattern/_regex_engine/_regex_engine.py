"""Third-party ``regex`` package adapter — opt-in via the ``[regex]`` extra.

Matthew Barnett's ``regex`` package is a ``re`` superset that adds, among
many other things, the set-operation syntax that ECMAScript's ``v`` flag
introduces: ``[a&&b]`` (intersection), ``[a--b]`` (difference), nested
character classes, etc. Enabling these features requires the ``(?V1)``
inline flag at the start of the pattern — that's the only substantive
upgrade we want.

Because ``regex`` is *also* a Perl/Python-flavored superset of JS regex
(it accepts ``\\m`` as a literal, ``(?R)`` recursion, atomic groups, named
backrefs, etc.), we run every pattern through ``re.compile`` first as a
strict JS-compatibility check. ``re`` rejects all the JS-incompatible
constructs ``regex`` would silently accept, so this pre-flight catches
them with the same ``TypeError`` users get under the stdlib adapter. The
authoritative matcher is still the ``regex``-compiled object — we just
discard the ``re`` result after it served as a validator.

This module is imported lazily by :mod:`yarlpattern._regex_engine`;
importing it without ``regex`` installed raises ``ImportError``, which
the parent package catches and falls back to the stdlib engine.
"""

from __future__ import annotations

import re
import warnings
from typing import TYPE_CHECKING, cast

import regex  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from yarlpattern._regex_engine.protocols import CompiledRegex


class RegexPackageEngine:
    """Adapter over the third-party ``regex`` package.

    Patterns are prefixed with the inline ``(?V1)`` flag so the engine
    activates its Version-1 dialect — nested character classes plus the
    JS-``v``-flag-style set operators (``&&``, ``--``, ``||``, ``~~``).
    """

    name = "regex"
    supports_set_operations = True

    def compile(self, pattern: str, *, ignore_case: bool) -> CompiledRegex:
        # Pre-flight: ``re.compile`` rejects JS-incompatible syntax that
        # ``regex`` would silently accept (``\\m``, ``(?R)``, etc.). The
        # FutureWarning suppression is for ``[a&&b]`` / ``[a--b]`` —
        # those compile fine under ``re`` (treated as literal chars) and
        # we'll get the correct semantics from ``regex`` on the second
        # pass; the warning just leaks otherwise.
        re_flags = re.ASCII
        if ignore_case:
            re_flags |= re.IGNORECASE
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                re.compile(pattern, re_flags)
        except re.error as exc:
            msg = f"URLPattern: invalid regex {pattern!r}: {exc}"
            raise TypeError(msg) from exc

        flags = regex.ASCII | regex.VERSION1
        if ignore_case:
            flags |= regex.IGNORECASE
        try:
            # ``regex`` exposes ``Pattern`` / ``Match`` without inline-typed
            # ``.fullmatch`` annotations, so mypy can't statically verify
            # the structural fit. The cast here is a no-op at runtime.
            return cast("CompiledRegex", regex.compile(pattern, flags))
        except regex.error as exc:
            msg = f"URLPattern: invalid regex {pattern!r}: {exc}"
            raise TypeError(msg) from exc


def get_engine() -> RegexPackageEngine:
    """Return the singleton ``regex``-package engine instance."""
    return _SINGLETON


_SINGLETON = RegexPackageEngine()
