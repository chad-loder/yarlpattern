"""URL parsing and baseURL inheritance, layered on :mod:`yarl`.

The WHATWG URL pipeline is kept behind this adapter so the dependency on
yarl's specific API surface is localized — :mod:`yarlpattern._pattern`
only imports the bits it needs (``_components_from_yarl`` for the
fast-path yarl-input branch; ``parse_url`` / ``apply_*`` for everything
else). Swapping for a faster URL-parsing backend later would touch this
module.

What we use yarl for
--------------------

* **String input parsing** — when a user calls ``pattern.exec("https://...")``,
  we hand the string to yarl, then read back per-component canonical strings.
  yarl is already WHATWG-flavored (it shares roots with aiohttp's URL stack
  and applies IDNA + percent-encoding per the spec for the common cases).

* **baseURL inheritance** — both on the pattern side ("inherit missing
  pattern strings from this URL") and on the input side ("fill missing
  input component strings from this URL").

* **Reference resolution** — when a string input is paired with a baseURL,
  yarl's :meth:`URL.join` resolves the input against the base using WHATWG
  semantics, so relative paths work the same as in a browser.

What we don't use yarl for
--------------------------

* **Tokenizing pattern strings** — patterns contain syntax (``:name``,
  ``(.*)``, ``{...}?``) that would confuse a URL parser. Pattern parsing
  goes through our own tokenizer / parser.

* **Component pattern strings as patterns** — when we inherit a *pattern*
  string from a baseURL, the URL's component is used verbatim as a literal
  pattern. yarl already canonicalized it; we just treat the result as
  literal text for the tokenizer.
"""

from __future__ import annotations

from typing import Final, TypedDict

from yarl import URL

from yarlpattern._parts import escape_pattern_string


class URLComponents(TypedDict):
    """A parsed URL split into the eight URLPattern components.

    All fields are strings — empty string for "not present", never ``None`` —
    so callers can drop them straight into the matcher without re-wrapping.
    """

    protocol: str
    username: str
    password: str
    hostname: str
    port: str
    pathname: str
    search: str
    hash: str


# Earlier-component chains for baseURL inheritance (§3.2). The spec's rule is
# subtle: a component inherits from the baseURL **only when none of an
# ordered list of "earlier" components are explicitly present in the init**.
# This stops you from getting nonsense like "hostname=foo, baseURL=https://bar"
# producing a fully concrete pattern with the baseURL's protocol/path/etc. —
# specifying an earlier component is the user's signal that they want the
# later components to widen (default to ``*``), not narrow.
#
# Pattern-side: username and password are never inherited at all (the spec's
# kind==Pattern branch skips them).
# Input-side: username and password DO inherit, with their own chains that
# also include the user/password fields themselves.
_PATTERN_INHERIT_CHAIN: Final[dict[str, tuple[str, ...]]] = {
    "protocol": (),
    "hostname": ("protocol",),
    "port": ("protocol", "hostname"),
    "pathname": ("protocol", "hostname", "port"),
    "search": ("protocol", "hostname", "port", "pathname"),
    "hash": ("protocol", "hostname", "port", "pathname", "search"),
}

_INPUT_INHERIT_CHAIN: Final[dict[str, tuple[str, ...]]] = {
    "protocol": (),
    "username": ("protocol", "hostname", "port"),
    "password": ("protocol", "hostname", "port", "username"),
    "hostname": ("protocol",),
    "port": ("protocol", "hostname"),
    "pathname": ("protocol", "hostname", "port"),
    "search": ("protocol", "hostname", "port", "pathname"),
    "hash": ("protocol", "hostname", "port", "pathname", "search"),
}


def _components_from_yarl(url: URL) -> URLComponents:
    """Read all eight components off a parsed :class:`yarl.URL`.

    Each field is normalized to a plain string. ``explicit_port`` rather
    than ``port`` is used so that an unset port stays empty rather than
    being filled with the scheme's default (e.g. 443 for https) — the
    WHATWG canonical form omits default ports, and URLPattern expects the
    same.

    IPv6 hosts get their brackets re-added: yarl returns the bare IPv6
    address (``::1``) but URLPattern matches against the bracketed form
    (``[::1]``) because that's what a pattern like ``http://[::1]/``
    compiles to. The trigger is a ``:`` in the host, which only appears
    in IPv6 addresses (domain names and IPv4 use ``.``).
    """
    host = url.host or ""
    if ":" in host:
        host = f"[{host}]"
    return URLComponents(
        protocol=url.scheme,
        username=url.user or "",
        password=url.password or "",
        hostname=host,
        port=str(url.explicit_port) if url.explicit_port is not None else "",
        pathname=url.path,
        search=url.query_string,
        hash=url.fragment,
    )


_SPECIAL_SCHEMES_URL: Final[frozenset[str]] = frozenset(
    {"http", "https", "ws", "wss", "ftp", "file"},
)


def _normalize_special_scheme_input(input_: str) -> str:
    """Inject ``//`` after a bare special-scheme colon.

    WHATWG URL parser quirk: when a special scheme (``http``/``https``/etc.)
    is followed by ``:`` but not ``://``, the parser falls through to the
    "special authority ignore slashes state" with a validation error and
    parses whatever follows as an authority. Concretely:
    ``https:user:pw@host`` resolves to ``https://user:pw@host``.

    yarl is stricter and treats anything after ``scheme:`` (without
    ``//``) as an opaque path. We pre-normalize so the rest of the
    pipeline sees the WHATWG-canonical form. The transformation is a
    pure prefix rewrite — cheap enough to run on every input.
    """
    colon_idx = input_.find(":")
    if colon_idx <= 0:
        return input_
    scheme = input_[:colon_idx].lower()
    if scheme not in _SPECIAL_SCHEMES_URL:
        return input_
    rest = input_[colon_idx + 1 :]
    if rest.startswith("//"):
        return input_
    return f"{scheme}://{rest}"


def parse_url(input_: str, base_url: str | None = None) -> URLComponents:
    """Parse *input_* as a URL, optionally resolved against *base_url*.

    Raises :class:`TypeError` on malformed input — the URLPattern spec
    surfaces every URL parsing failure as ``TypeError``, so we translate
    yarl's :class:`ValueError` (and the rare :class:`Exception` shape it
    falls back to for some path-only inputs) at the boundary. That keeps
    the public API surface a single exception type for "the user gave us
    something we can't make sense of".

    Also enforces the WHATWG "cannot-be-a-base URL" rule: when *base_url*
    is a non-special scheme with an opaque path (e.g. ``data:foo``,
    ``javascript:alert(1)``), it cannot anchor a relative input — ``new
    URL('foo', 'data:...')`` throws in JS, so we do the same here. yarl
    happily joins those, but the result diverges from WHATWG semantics in
    ways that break WPT matching.
    """
    try:
        url = URL(_normalize_special_scheme_input(input_))
        if base_url is not None:
            base = URL(_normalize_special_scheme_input(base_url))
            # A baseURL must itself be an absolute URL — i.e. have a
            # scheme. yarl will happily parse ``'not|a|valid|url'`` into
            # a relative URL (scheme=''), but WHATWG rejects it outright.
            if base.scheme == "":
                raise TypeError(
                    f"URLPattern: baseURL {base_url!r} must be absolute",
                )
            # Cannot-be-a-base check: non-special scheme with no authority
            # (``host`` is None) is opaque-path-only. It can't anchor a
            # relative input. Only applies when the input itself is
            # relative (lacks a scheme).
            if url.scheme == "" and base.scheme not in _SPECIAL_SCHEMES_URL and base.host is None:
                raise TypeError(
                    f"URLPattern: cannot resolve {input_!r} against opaque baseURL {base_url!r}",
                )
            joined = base.join(url)
            # yarl quirk: ``base.join`` preserves base's fragment when the
            # relative URL is query-only (``?bar``). WHATWG's relative
            # state initializes the fragment to *empty* — only an explicit
            # ``#`` in the input sets it. Strip the inherited fragment
            # when the input doesn't carry one of its own.
            if "#" not in input_:
                joined = joined.with_fragment(None)
            url = joined
    except (ValueError, TypeError) as exc:
        raise TypeError(f"URLPattern: failed to parse URL {input_!r}") from exc
    return _components_from_yarl(url)


def parse_base_url(base_url: str) -> URLComponents:
    """Parse a baseURL string into its components.

    Wraps :func:`parse_url` so that the call sites read clearly — pattern
    construction always treats baseURL as an absolute URL with no further
    resolution, whereas input-side parsing uses :func:`parse_url` directly
    with the input string + optional baseURL pair.
    """
    return parse_url(base_url)


def _is_absolute_pathname(pathname: str, *, is_pattern: bool) -> bool:
    """Polyfill ``isAbsolutePathname``.

    A pathname counts as absolute if it starts with ``/``. In *pattern*
    context (constructor side), two additional prefixes count: ``\\/`` (an
    escaped leading slash) and ``{/`` (a group whose first content is a
    slash). Input context (match side) uses only the plain ``/`` form
    because escape syntax has no meaning in a parsed URL.
    """
    if len(pathname) == 0:
        return False
    if pathname[0] == "/":
        return True
    if not is_pattern or len(pathname) < 2:
        return False
    return (pathname[0] == "\\" and pathname[1] == "/") or (pathname[0] == "{" and pathname[1] == "/")


def _resolve_relative_pathname(
    pathname: str,
    base_pathname: str,
    *,
    is_pattern: bool,
) -> str:
    """Prepend the base URL's pathname *directory* to a relative pathname.

    The "directory" is everything up to and including the **last** ``/`` in
    *base_pathname*. If the base has no slash (a degenerate / opaque path),
    we leave the original pathname alone — there's no hierarchical context
    to anchor against.

    Same effective behavior as the ``applyInit`` step in the spec algorithm.
    """
    if _is_absolute_pathname(pathname, is_pattern=is_pattern):
        return pathname
    slash_idx = base_pathname.rfind("/")
    if slash_idx < 0:
        return pathname
    return base_pathname[: slash_idx + 1] + pathname


def _apply_inheritance(
    init_map: dict[str, str],
    base_components: URLComponents,
    chain: dict[str, tuple[str, ...]],
    *,
    is_pattern: bool,
) -> dict[str, str]:
    """Fill missing components per a chain table.

    Shared core for :func:`apply_pattern_base_url` and
    :func:`apply_input_base_url`. A component inherits only when (a) it is
    not already present in ``init_map`` AND (b) none of its earlier
    components per ``chain`` are present in the *original* ``init_map``.
    The "original" qualifier matters: filling in protocol from baseURL
    must not then prevent hostname from also inheriting.

    Pathname has special handling: when *pathname is present* in init but
    is *not* absolute, the baseURL's pathname-directory is prepended
    instead of being inherited wholesale.

    On the pattern side, base URL component values that *flow into a
    pattern slot* must have their pattern-punctuator characters escaped
    (``+ * ? : { } ( ) \\``) — otherwise a base URL like
    ``https://example.com/?q=*`` would inject a wildcard into the search
    pattern.
    """
    original_keys = frozenset(init_map)
    out: dict[str, str] = dict(init_map)
    for component, earlier in chain.items():
        if component in out:
            continue
        if any(earlier_comp in original_keys for earlier_comp in earlier):
            continue
        value: str = base_components[component]  # type: ignore[literal-required]
        if is_pattern and value:
            value = escape_pattern_string(value)
        out[component] = value
    # Relative-pathname resolution. This applies even when pathname *was*
    # present in init — the rule is about the value itself starting with
    # ``/``, not about the key being absent.
    if "pathname" in original_keys:
        base_pathname = base_components["pathname"]
        if is_pattern and base_pathname:
            base_pathname = escape_pattern_string(base_pathname)
        out["pathname"] = _resolve_relative_pathname(
            out["pathname"],
            base_pathname,
            is_pattern=is_pattern,
        )
    return out


def apply_pattern_base_url(
    init_map: dict[str, str],
    base_url: str,
) -> dict[str, str]:
    """Fill missing pattern strings from *base_url*'s components.

    Per the spec, ``username`` and ``password`` are **not** inherited on
    the pattern side — they are simply absent from ``_PATTERN_INHERIT_CHAIN``
    and so default to ``"*"`` in the surrounding compilation step.

    Returns a new dict; the caller's ``init_map`` is left alone.
    """
    base_components = parse_base_url(base_url)
    return _apply_inheritance(
        init_map,
        base_components,
        _PATTERN_INHERIT_CHAIN,
        is_pattern=True,
    )


def apply_input_base_url(
    input_map: dict[str, str],
    base_url: str,
) -> dict[str, str]:
    """Fill missing input component strings from *base_url*'s components.

    Unlike pattern inheritance, the input side **does** inherit
    ``username`` and ``password`` — the input baseURL is meant to give a
    complete URL context for the match.

    Returns a new dict; the caller's ``input_map`` is left alone.
    """
    base_components = parse_base_url(base_url)
    return _apply_inheritance(
        input_map,
        base_components,
        _INPUT_INHERIT_CHAIN,
        is_pattern=False,
    )
