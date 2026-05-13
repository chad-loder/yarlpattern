"""Unit tests for the public :class:`URLPattern` class.

These cover the dict-form constructor, the component property surface,
``test()``, and ``exec()`` against the simple cases. The WPT integration
suite (``test_wpt.py``) covers the full conformance corpus.
"""

from __future__ import annotations

import pytest

from yarlpattern import COMPONENTS, URLPattern

# ----------------------------------------------------- construction surface


def test_empty_init_defaults_every_component_to_wildcard() -> None:
    pat = URLPattern({})
    for component in COMPONENTS:
        assert getattr(pat, component) == "*"


def test_specified_pathname_only() -> None:
    pat = URLPattern({"pathname": "/foo/bar"})
    assert pat.pathname == "/foo/bar"
    assert pat.protocol == "*"
    assert pat.hostname == "*"


def test_repr_includes_all_components() -> None:
    pat = URLPattern({"pathname": "/foo"})
    r = repr(pat)
    for component in COMPONENTS:
        assert component in r


def test_equality_compares_all_component_strings() -> None:
    a = URLPattern({"pathname": "/foo"})
    b = URLPattern({"pathname": "/foo"})
    c = URLPattern({"pathname": "/bar"})
    assert a == b
    assert a != c
    assert hash(a) == hash(b)


def test_string_shorthand_constructor_parses_full_url() -> None:
    # §1.6 constructor-string parser splits a URL-shaped pattern into its
    # per-component pattern strings before the dict-form pipeline runs.
    pat = URLPattern("https://example.com/:foo")
    assert pat.protocol == "https"
    assert pat.hostname == "example.com"
    assert pat.pathname == "/:foo"
    # Components not present in the input get the wildcard default.
    assert pat.search == "*"
    assert pat.hash == "*"


def test_string_shorthand_constructor_with_base_url() -> None:
    # Positional base URL fills in missing components on the pattern side.
    pat = URLPattern("/:foo", "https://example.com")
    assert pat.protocol == "https"
    assert pat.hostname == "example.com"
    assert pat.pathname == "/:foo"


def test_string_shorthand_path_only_requires_base_url() -> None:
    # Per Chromium / WHATWG: a bare relative-path constructor string
    # without a baseURL is ambiguous (special-scheme path vs opaque path)
    # and must throw TypeError. Either pass a baseURL or use the dict
    # form which is permitted to leave the protocol unset.
    with pytest.raises(TypeError, match="relative constructor string"):
        URLPattern("/foo/:id")
    # With a baseURL it compiles fine.
    pat = URLPattern("/foo/:id", "https://example.com")
    assert pat.pathname == "/foo/:id"


def test_pattern_base_url_fills_missing_components() -> None:
    # baseURL inheritance on the *pattern* side: protocol/hostname/etc. get
    # filled with literal text from the baseURL; username/password do not.
    pat = URLPattern({"pathname": "/foo", "baseURL": "https://example.com"})
    assert pat.protocol == "https"
    assert pat.hostname == "example.com"
    assert pat.port == ""  # baseURL has no explicit port
    assert pat.pathname == "/foo"
    assert pat.username == "*"  # never inherited from pattern baseURL
    assert pat.password == "*"


def test_pattern_base_url_does_not_override_explicit() -> None:
    # When an earlier component (protocol) is *explicitly* specified, later
    # components do NOT inherit from baseURL — they widen back to ``*``.
    # The rationale is that pinning protocol expresses "this pattern is
    # about protocol matching"; auto-pinning hostname/path from baseURL
    # would narrow the pattern in a way the user almost never wants.
    pat = URLPattern({"protocol": "http", "baseURL": "https://example.com"})
    assert pat.protocol == "http"  # explicit wins
    assert pat.hostname == "*"  # not inherited because protocol is explicit
    assert pat.pathname == "*"


# --------------------------------------------------------------------- test()


def test_test_matches_explicit_pathname() -> None:
    pat = URLPattern({"pathname": "/foo/bar"})
    assert pat.test({"pathname": "/foo/bar"}) is True


def test_test_rejects_pathname_mismatch() -> None:
    pat = URLPattern({"pathname": "/foo/bar"})
    assert pat.test({"pathname": "/foo/baz"}) is False
    # Trailing slash difference must matter — the regex is fullmatch-anchored.
    assert pat.test({"pathname": "/foo/bar/"}) is False


def test_test_unspecified_components_default_to_wildcard_match() -> None:
    # Only pathname is constrained; protocol/hostname/etc. all match the
    # empty input (default ``*`` against ``""``).
    pat = URLPattern({"pathname": "/foo"})
    assert pat.test({"pathname": "/foo"}) is True


def test_test_named_group_match() -> None:
    pat = URLPattern({"pathname": "/blog/:slug"})
    assert pat.test({"pathname": "/blog/hello"}) is True
    assert pat.test({"pathname": "/blog/hello/world"}) is False


def test_test_with_regex_body() -> None:
    pat = URLPattern({"pathname": r"/posts/:id(\d+)"})
    assert pat.test({"pathname": "/posts/42"}) is True
    assert pat.test({"pathname": "/posts/abc"}) is False


# --------------------------------------------------------------------- exec()


def test_exec_returns_result_with_per_component_dicts() -> None:
    pat = URLPattern({"pathname": "/foo"})
    result = pat.exec({"pathname": "/foo"})
    assert result is not None
    assert result.pathname == {"input": "/foo", "groups": {}}


def test_exec_returns_none_on_miss() -> None:
    pat = URLPattern({"pathname": "/foo"})
    assert pat.exec({"pathname": "/bar"}) is None


def test_exec_captures_named_group() -> None:
    pat = URLPattern({"pathname": "/blog/:slug"})
    result = pat.exec({"pathname": "/blog/hello"})
    assert result is not None
    assert result.pathname == {"input": "/blog/hello", "groups": {"slug": "hello"}}


def test_exec_captures_numeric_group_for_anonymous_wildcard() -> None:
    pat = URLPattern({"pathname": "/files/*"})
    result = pat.exec({"pathname": "/files/path/to/file.txt"})
    assert result is not None
    assert result.pathname == {
        "input": "/files/path/to/file.txt",
        "groups": {"0": "path/to/file.txt"},
    }


def test_exec_populates_default_components_with_wildcard_capture() -> None:
    # Pattern only specifies pathname → every other component has the default
    # ``*`` pattern matching the empty input → groups["0"] == "".
    pat = URLPattern({"pathname": "/foo"})
    result = pat.exec({"pathname": "/foo"})
    assert result is not None
    assert result.protocol == {"input": "", "groups": {"0": ""}}
    assert result.hostname == {"input": "", "groups": {"0": ""}}
    assert result.hash == {"input": "", "groups": {"0": ""}}


def test_exec_echoes_inputs() -> None:
    pat = URLPattern({"pathname": "/foo"})
    inp = {"pathname": "/foo"}
    result = pat.exec(inp)
    assert result is not None
    assert result.inputs == [inp]


def test_exec_optional_group_unmatched_is_absent_from_groups_dict() -> None:
    # An optional group that didn't capture must NOT appear in the groups
    # dict — equivalent to JS ``undefined``. This is the contract that lets
    # us compare directly with WPT's JSON-stripped expected values.
    pat = URLPattern({"pathname": "/foo/:bar?"})
    result = pat.exec({"pathname": "/foo"})
    assert result is not None
    assert "bar" not in result.pathname["groups"]


def test_exec_optional_group_matched_value_in_groups_dict() -> None:
    pat = URLPattern({"pathname": "/foo/:bar?"})
    result = pat.exec({"pathname": "/foo/baz"})
    assert result is not None
    assert result.pathname["groups"]["bar"] == "baz"


# ------------------------------------------------------------ has_regexp_groups


def test_has_regexp_groups_false_for_plain_literal() -> None:
    pat = URLPattern({"pathname": "/foo"})
    assert pat.has_regexp_groups is False


def test_has_regexp_groups_false_for_segment_wildcard() -> None:
    # Per spec: a segment wildcard (``:foo``) is its own part type, not a
    # custom regexp. WPT's hasregexpgroups corpus pins this down.
    pat = URLPattern({"pathname": "/:foo"})
    assert pat.has_regexp_groups is False


def test_has_regexp_groups_true_for_custom_regex_body() -> None:
    # Spec: only ``PartType.REGEXP`` parts with non-wildcard bodies count.
    pat = URLPattern({"pathname": "/:foo([0-9]+)"})
    assert pat.has_regexp_groups is True


# ----------------------------------------------------------- compare_component


def test_compare_component_rejects_unknown_component_name() -> None:
    pat = URLPattern({"pathname": "/foo"})
    with pytest.raises(TypeError, match="unknown component"):
        URLPattern.compare_component("not-a-component", pat, pat)


def test_compare_component_self_equality_across_all_components() -> None:
    # Self-compare must be 0 on every component, regardless of pattern shape.
    pat = URLPattern({"pathname": "/foo/:id(\\d+)"})
    for component in COMPONENTS:
        assert URLPattern.compare_component(component, pat, pat) == 0


def test_compare_component_empty_treated_as_full_wildcard() -> None:
    # Explicitly empty component pattern compares equal to ``*`` — the spec
    # substitutes the same single-FULL_WILDCARD part list for both.
    empty = URLPattern({"pathname": ""})
    star = URLPattern({"pathname": "*"})
    assert URLPattern.compare_component("pathname", empty, star) == 0
    assert URLPattern.compare_component("pathname", star, empty) == 0


def test_camelcase_aliases_resolve_to_same_callable_and_property() -> None:
    # ``compareComponent`` and ``hasRegExpGroups`` are kept as IDL-faithful
    # camelCase aliases so code ported verbatim from the spec / browser JS
    # reads identically. They must dispatch to the snake-case canonical
    # forms, not duplicate the logic.
    pat = URLPattern({"pathname": "/foo/:id(\\d+)"})
    other = URLPattern({"pathname": "/foo/:id(\\d+)"})
    assert URLPattern.compareComponent is URLPattern.compare_component
    assert URLPattern.compareComponent("pathname", pat, other) == 0
    assert pat.hasRegExpGroups is pat.has_regexp_groups


# ---------------------------------------------------------------------- with_


def test_with_replaces_one_component() -> None:
    pat = URLPattern({"pathname": "/foo"})
    new = pat.with_(pathname="/bar")
    assert pat.pathname == "/foo"
    assert new.pathname == "/bar"
    assert new.hostname == "*"  # unchanged


def test_per_component_with_methods_match_with_kwargs() -> None:
    # Each ``with_<component>`` should be exactly equivalent to passing
    # the same kwarg through ``with_(**kwargs)``. yarl-style ergonomics
    # without changing the semantic of the base method.
    base = URLPattern({"hostname": "example.com", "pathname": "/foo"})
    assert base.with_protocol("https") == base.with_(protocol="https")
    assert base.with_username("admin") == base.with_(username="admin")
    assert base.with_password("s3cret") == base.with_(password="s3cret")  # noqa: S106 — test fixture value, not a real credential
    assert base.with_hostname("api.example.com") == base.with_(hostname="api.example.com")
    assert base.with_port("8080") == base.with_(port="8080")
    assert base.with_pathname("/bar") == base.with_(pathname="/bar")
    assert base.with_search("q=1") == base.with_(search="q=1")
    assert base.with_hash("frag") == base.with_(hash="frag")


# -------------------------------------------------- yarl.URL input acceptance


def test_test_accepts_yarl_url_input() -> None:
    # yarl.URL is the request.url type in aiohttp; pat.test should accept
    # it directly without the caller having to str() it first.
    from yarl import URL  # noqa: PLC0415 — yarl is a runtime dep; import-locality is fine here.

    pat = URLPattern("https://api.example.com/users/:id")
    assert pat.test(URL("https://api.example.com/users/42")) is True
    assert pat.test(URL("https://api.example.com/users/abc")) is True
    assert pat.test(URL("https://other.example.com/users/42")) is False


def test_exec_yarl_url_input_extracts_groups() -> None:
    from yarl import URL  # noqa: PLC0415

    pat = URLPattern("https://*.example.com/users/:id(\\d+)")
    result = pat.exec(URL("https://api.example.com/users/42"))
    assert result is not None
    assert result.pathname["groups"]["id"] == "42"


def test_test_accepts_yarl_url_base_url() -> None:
    from yarl import URL  # noqa: PLC0415

    pat = URLPattern({"pathname": "/foo/bar"})
    # Both inputs as yarl URLs (input must be relative; base supplies host).
    assert pat.test(URL("foo/bar"), URL("https://example.com")) is True


# --------------------------------------------------------- ignore_case option


# --------------------------------------------------------- string input / baseURL


def test_exec_with_string_input() -> None:
    pat = URLPattern({"pathname": "/foo"})
    result = pat.exec("https://example.com/foo")
    assert result is not None
    assert result.pathname["input"] == "/foo"
    assert result.protocol["input"] == "https"
    assert result.hostname["input"] == "example.com"


def test_exec_with_string_input_and_base_url() -> None:
    # A relative string is resolved against the baseURL using WHATWG
    # semantics — yarl's URL.join does the heavy lifting.
    pat = URLPattern({"pathname": "/blog/post1"})
    result = pat.exec("post1", "https://example.com/blog/")
    assert result is not None
    assert result.pathname["input"] == "/blog/post1"


def test_exec_with_dict_input_baseURL_fills_missing_components() -> None:
    pat = URLPattern({"pathname": "/foo"})
    result = pat.exec({"pathname": "/foo", "baseURL": "https://example.com"})
    assert result is not None
    # Components not in the input dict are filled from the baseURL.
    assert result.protocol["input"] == "https"
    assert result.hostname["input"] == "example.com"
    # The dict's explicit value wins over the baseURL.
    assert result.pathname["input"] == "/foo"


def test_exec_inputs_echo_includes_base_url() -> None:
    # The result must echo BOTH positional arguments so callers can
    # reconstruct what was matched. Use a pattern that will succeed under
    # the resolved URL, otherwise exec returns None and we never see the
    # echo.
    pat = URLPattern({"pathname": "/blog/post1"})
    result = pat.exec("post1", "https://example.com/blog/")
    assert result is not None
    assert result.inputs == ["post1", "https://example.com/blog/"]


def test_ignore_case_option() -> None:
    pat = URLPattern({"pathname": "/Foo"}, {"ignoreCase": True})
    assert pat.test({"pathname": "/foo"}) is True
    assert pat.test({"pathname": "/FOO"}) is True
    pat_strict = URLPattern({"pathname": "/Foo"})
    assert pat_strict.test({"pathname": "/foo"}) is False
