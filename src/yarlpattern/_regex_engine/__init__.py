"""Pluggable regex engine selection for URLPattern.

URLPattern compiles every component pattern into a regex; the *engine* that
backs that compile-and-match pipeline is swappable. Two ship in-tree:

* **``re``** — the stdlib :mod:`re` module. Always available. Falls short
  on JS ``v``-flag set operations (``[a&&b]`` / ``[a--b]``); they're
  syntactically tolerated but treated as literals.
* **``regex``** — Matthew Barnett's third-party ``regex`` package. Opt-in
  via ``pip install yarlpattern[regex]``. Handles the set operations and
  closes those WPT conformance gaps.

Selection priority, highest first:

1. Explicit ``engine=...`` argument to :class:`yarlpattern.URLPattern`.
2. The ``URLPATTERN_REGEX_ENGINE`` environment variable (``re`` / ``regex``).
3. Module-level :func:`set_default_engine` override.
4. Auto-probe: if ``import regex`` succeeds, use it; otherwise stdlib ``re``.

The probe runs once at import time; the result is cached. Tests can reset
the cache via :func:`_reset_default_engine_cache` (private — for the test
suite, not application code).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yarlpattern._regex_engine.protocols import RegexEngine

from yarlpattern._regex_engine.protocols import (
    CompiledMatch,
    CompiledRegex,
    RegexEngine,
)

__all__ = [
    "CompiledMatch",
    "CompiledRegex",
    "RegexEngine",
    "get_default_engine",
    "get_engine_by_name",
    "set_default_engine",
]

_ENV_VAR = "URLPATTERN_REGEX_ENGINE"

# Module-level default. ``None`` means "fall through to the probe". Setting
# via :func:`set_default_engine` skips probing on subsequent calls.
_override: RegexEngine | None = None

# Cache for the probe result. ``None`` means "not yet probed".
_probed: RegexEngine | None = None


def get_engine_by_name(name: str) -> RegexEngine:
    """Return the engine adapter for *name* (``"re"`` or ``"regex"``).

    Importing the ``regex`` adapter triggers an ``import regex``; if the
    package isn't installed, a :class:`LookupError` is raised with a hint to
    install the ``[regex]`` extra. The ``re`` adapter is always available.
    """
    if name == "re":
        from yarlpattern._regex_engine import _re_engine

        return _re_engine.get_engine()
    if name == "regex":
        try:
            from yarlpattern._regex_engine import _regex_engine
        except ImportError as exc:
            msg = (
                "URLPattern: the 'regex' engine requires the third-party "
                "regex package — install with `pip install yarlpattern[regex]`"
            )
            raise LookupError(msg) from exc
        return _regex_engine.get_engine()
    msg = f"URLPattern: unknown regex engine {name!r}; expected 're' or 'regex'"
    raise LookupError(msg)


def set_default_engine(engine: RegexEngine | None) -> None:
    """Override the default engine globally.

    Pass ``None`` to clear the override and fall back to the env-var /
    auto-probe behavior. Useful for tests that want to exercise both
    engines from the same process.
    """
    global _override  # noqa: PLW0603 — module-level singleton state by design
    _override = engine


def get_default_engine() -> RegexEngine:
    """Return the active engine per the selection-priority rules."""
    if _override is not None:
        return _override

    env_value = os.environ.get(_ENV_VAR, "").strip()
    if env_value:
        return get_engine_by_name(env_value)

    global _probed  # noqa: PLW0603 — cached probe result, not a runtime mutation
    if _probed is None:
        _probed = _probe()
    return _probed


def _probe() -> RegexEngine:
    """Auto-pick: prefer the ``regex`` package when importable.

    Falls back to stdlib ``re`` if ``regex`` isn't installed. Either way
    URLPattern works; the only difference is conformance on the set-op
    fringe of the WPT corpus.
    """
    try:
        from yarlpattern._regex_engine import _regex_engine

        return _regex_engine.get_engine()
    except ImportError:
        from yarlpattern._regex_engine import _re_engine

        return _re_engine.get_engine()


def _reset_default_engine_cache() -> None:
    """Clear the cached probe result. **Test-suite only.**"""
    global _probed  # noqa: PLW0603 — clearing the cache is the function's purpose
    _probed = None
