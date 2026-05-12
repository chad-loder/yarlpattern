"""Tests for the pluggable regex-engine layer.

These cover the public contract of :mod:`yarlpattern._regex_engine`:

* Both adapters satisfy the :class:`RegexEngine` Protocol via structural
  subtyping (``isinstance`` against a ``runtime_checkable`` Protocol).
* The dispatcher honors the selection priority chain.
* The engine choice is observable by callers that need to know what
  semantics they're getting (e.g. the WPT harness's xfail logic).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from yarlpattern import URLPattern
from yarlpattern._regex_engine import (
    CompiledRegex,
    RegexEngine,
    _reset_default_engine_cache,
    get_default_engine,
    get_engine_by_name,
    set_default_engine,
)

# Whether the ``regex`` package is installed in the current environment.
# Tests that exercise the third-party engine skip themselves when it
# isn't, so the suite stays green in the default-extras install.
_HAS_REGEX_PKG = importlib.util.find_spec("regex") is not None


@pytest.fixture(autouse=True)
def _isolate_engine_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset module-level engine state for each test.

    ``monkeypatch.delenv`` undoes itself at fixture teardown — that's the
    point of using monkeypatch over ``os.environ.pop`` directly. Without
    this we'd clobber a user-supplied ``URLPATTERN_REGEX_ENGINE`` for any
    test that runs after one of ours.
    """
    monkeypatch.delenv("URLPATTERN_REGEX_ENGINE", raising=False)
    set_default_engine(None)
    _reset_default_engine_cache()
    yield
    set_default_engine(None)
    _reset_default_engine_cache()


def test_re_engine_satisfies_protocol() -> None:
    engine = get_engine_by_name("re")
    assert isinstance(engine, RegexEngine)
    assert engine.name == "re"
    assert engine.supports_set_operations is False


def test_re_engine_compiles_basic_pattern() -> None:
    engine = get_engine_by_name("re")
    pat = engine.compile(r"^foo$", ignore_case=False)
    assert isinstance(pat, CompiledRegex)
    m = pat.fullmatch("foo")
    assert m is not None
    assert pat.fullmatch("bar") is None


def test_re_engine_rejects_invalid_regex_as_typeerror() -> None:
    engine = get_engine_by_name("re")
    # ``\m`` is not a valid escape in Python ``re`` — adapters surface
    # the engine's error as TypeError to keep the URLPattern API surface
    # uniform across backends.
    with pytest.raises(TypeError, match="invalid regex"):
        engine.compile(r"\m", ignore_case=False)


@pytest.mark.skipif(not _HAS_REGEX_PKG, reason="regex package not installed")
def test_regex_engine_satisfies_protocol() -> None:
    engine = get_engine_by_name("regex")
    assert isinstance(engine, RegexEngine)
    assert engine.name == "regex"
    assert engine.supports_set_operations is True


@pytest.mark.skipif(not _HAS_REGEX_PKG, reason="regex package not installed")
def test_regex_engine_handles_set_operations() -> None:
    # The whole point of the regex engine: ``[a&&b]`` (intersection),
    # ``[a--b]`` (difference) — JS v-flag features that stdlib ``re``
    # rejects (with a FutureWarning).
    engine = get_engine_by_name("regex")
    diff = engine.compile(r"^[[a-z]--a]$", ignore_case=False)
    assert diff.fullmatch("z") is not None
    assert diff.fullmatch("a") is None
    inter = engine.compile(r"^[\d&&[0-1]]$", ignore_case=False)
    assert inter.fullmatch("0") is not None
    assert inter.fullmatch("5") is None


@pytest.mark.skipif(not _HAS_REGEX_PKG, reason="regex package not installed")
def test_regex_engine_rejects_js_incompatible_syntax() -> None:
    # ``regex`` accepts ``\m`` and ``(?R)``; pre-flight via ``re.compile``
    # catches them so users get a uniform TypeError regardless of engine.
    engine = get_engine_by_name("regex")
    with pytest.raises(TypeError, match="invalid regex"):
        engine.compile(r"\m", ignore_case=False)


def test_unknown_engine_name_raises_lookup_error() -> None:
    with pytest.raises(LookupError, match="unknown regex engine"):
        get_engine_by_name("hyperscan")


def test_env_var_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("URLPATTERN_REGEX_ENGINE", "re")
    _reset_default_engine_cache()
    assert get_default_engine().name == "re"


def test_set_default_engine_overrides_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    # Module-level override wins over env-var. Useful for tests that
    # need both engines in the same process.
    monkeypatch.setenv("URLPATTERN_REGEX_ENGINE", "re")
    custom = get_engine_by_name("re")
    set_default_engine(custom)
    assert get_default_engine() is custom


def test_urlpattern_uses_default_engine() -> None:
    # The constructor without ``engine=`` uses the module default.
    set_default_engine(get_engine_by_name("re"))
    pat = URLPattern({"pathname": "/foo"})
    assert pat._engine.name == "re"


def test_urlpattern_explicit_engine_overrides_default() -> None:
    set_default_engine(get_engine_by_name("re"))
    if _HAS_REGEX_PKG:
        regex_engine = get_engine_by_name("regex")
        pat = URLPattern({"pathname": "/foo"}, engine=regex_engine)
        assert pat._engine is regex_engine
    else:
        # Without the regex package, the explicit-engine path still
        # works for the stdlib adapter.
        re_engine = get_engine_by_name("re")
        pat = URLPattern({"pathname": "/foo"}, engine=re_engine)
        assert pat._engine is re_engine
