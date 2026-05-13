"""Public :class:`URLPattern` surface — yarl-shaped, spec-strict.

This is the user-facing layer that ties the tokenizer / parser / regex pipeline
together. Pattern strings are parsed and compiled once at construction time
(one regex per URL component); :meth:`test` and :meth:`exec` then dispatch
those compiled regexes against the input.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Final, Self, cast

from yarl import URL as _YarlURL  # noqa: N811 — module-private alias, capitalized to match the class

from yarlpattern._canonicalize import (
    _DEFAULT_PORTS,
    SPECIAL_SCHEMES,
    canonicalize_hash,
    canonicalize_hostname,
    canonicalize_ipv6_hostname_slice,
    canonicalize_password,
    canonicalize_pathname,
    canonicalize_port,
    canonicalize_protocol,
    canonicalize_search,
    canonicalize_username,
    hostname_pattern_is_ipv6_address,
    port_pattern_slice_encode,
)
from yarlpattern._constructor import parse_constructor_string
from yarlpattern._parts import (
    EncodingCallback,
    Options,
    Part,
    PartModifier,
    PartType,
    generate_segment_wildcard_regexp,
    parse_pattern_string,
    parts_to_pattern_string,
)
from yarlpattern._regex import _translate_js_regex_to_python, parts_to_regex
from yarlpattern._regex_engine import (
    CompiledRegex,
    RegexEngine,
    get_default_engine,
)
from yarlpattern._url import (
    _components_from_yarl,
    apply_input_base_url,
    apply_pattern_base_url,
    parse_url,
)

type URLPatternInit = Mapping[str, str]
# Accept a URL string, a per-component dict, or a :class:`yarl.URL`.
# yarl URLs are read directly from their parsed components — the fast
# path for ``pat.test(request.url)`` in aiohttp / yarl-based callers.
type URLPatternInput = str | _YarlURL | Mapping[str, str]

COMPONENTS: Final[tuple[str, ...]] = (
    "protocol",
    "username",
    "password",
    "hostname",
    "port",
    "pathname",
    "search",
    "hash",
)

# Per-component parser options, following §1.5 of the spec. Hostname uses
# ``.`` as the segment separator because subdomains naturally split on dots;
# pathname uses ``/`` both as segment separator and as the automatic prefix
# for matching groups (this is what makes ``/:foo`` mean "a slash then a
# group" rather than just "a group with literal-slash prefix").
_DEFAULT_OPTS: Final = Options(delimiter_code_point="", prefix_code_point="")
_HOSTNAME_OPTS: Final = Options(delimiter_code_point=".", prefix_code_point="")
_PATHNAME_OPTS: Final = Options(delimiter_code_point="/", prefix_code_point="/")

_COMPONENT_OPTIONS: Final[dict[str, Options]] = {
    "protocol": _DEFAULT_OPTS,
    "username": _DEFAULT_OPTS,
    "password": _DEFAULT_OPTS,
    "hostname": _HOSTNAME_OPTS,
    "port": _DEFAULT_OPTS,
    "pathname": _PATHNAME_OPTS,
    "search": _DEFAULT_OPTS,
    "hash": _DEFAULT_OPTS,
}


# Spec ``process_<X>_init`` strips a single leading/trailing URL-structural
# character from these three components before compile. Reflects the
# convenience syntax: ``{protocol: 'http:'}`` is treated identically to
# ``{protocol: 'http'}``, and similarly for search ``?`` / hash ``#``.
def _strip_component_prefix_suffix(component: str, value: str) -> str:
    if component == "protocol" and value.endswith(":"):
        return value[:-1]
    if component == "search" and value.startswith("?"):
        return value[1:]
    if component == "hash" and value.startswith("#"):
        return value[1:]
    return value


# Per-component canonicalization callbacks. Some components are
# protocol-aware (port and pathname change behavior based on whether the
# protocol is a special scheme) — those bind the protocol via a closure at
# the call site in :class:`URLPattern`.
_BASE_CALLBACKS: Final[dict[str, EncodingCallback]] = {
    "protocol": canonicalize_protocol,
    "username": canonicalize_username,
    "password": canonicalize_password,
    "hostname": canonicalize_hostname,
    "search": canonicalize_search,
    "hash": canonicalize_hash,
}


# ------------------------------------------------------- compareComponent
#
# Specificity ordering tables — the orderings here are the WHATWG tentative
# spec's intended ranks (which the polyfill and Chromium also implement
# consistently). Higher rank = more restrictive; tuple-compare yields the
# spec's intended order.
#
# Modifier ordering:  NONE > ONE_OR_MORE > OPTIONAL > ZERO_OR_MORE
#   ("must exist exactly once" is more restrictive than "at least once",
#    which is more restrictive than "may exist", which is more
#    restrictive than "may exist zero or more times").
#
# PartType ordering: FIXED_TEXT > REGEXP > SEGMENT_WILDCARD > FULL_WILDCARD
#   (literal text is maximally restrictive; a custom regex usually
#    constrains; segment-wildcard limits the span; full-wildcard imposes
#    nothing).
_PART_TYPE_RANK: Final[dict[PartType, int]] = {
    PartType.FULL_WILDCARD: 0,
    PartType.SEGMENT_WILDCARD: 1,
    PartType.REGEXP: 2,
    PartType.FIXED_TEXT: 3,
}
_PART_MODIFIER_RANK: Final[dict[PartModifier, int]] = {
    PartModifier.ZERO_OR_MORE: 0,
    PartModifier.OPTIONAL: 1,
    PartModifier.ONE_OR_MORE: 2,
    PartModifier.NONE: 3,
}

# Length-mismatch sentinel — used by :meth:`URLPattern.compareComponent`
# to pad the shorter part list. An empty fixed-text part is what the spec
# substitutes so that ``/foo/`` outranks ``/foo/*``: a literal-ending
# pattern is more restrictive than one that wildcards after a common prefix.
_EMPTY_FIXED_KEY: Final[tuple[int, int, str, str, str]] = (
    _PART_TYPE_RANK[PartType.FIXED_TEXT],
    _PART_MODIFIER_RANK[PartModifier.NONE],
    "",
    "",
    "",
)

# Substitution for an entirely empty component — the spec treats a
# blank pattern as equivalent to ``*``. Stored as a single-element
# key tuple so it can drop in wherever ``compare_keys`` would.
_FULL_WILDCARD_ONLY_KEYS: Final[tuple[tuple[int, int, str, str, str], ...]] = (
    (
        _PART_TYPE_RANK[PartType.FULL_WILDCARD],
        _PART_MODIFIER_RANK[PartModifier.NONE],
        "",
        "",
        "",
    ),
)


def _part_to_compare_key(part: Any) -> tuple[int, int, str, str, str]:
    """Project a :class:`Part` to its compare key.

    Names are deliberately excluded — two patterns that differ only in
    capture-group names (``:foo`` vs ``:bar``) compare equal per the
    spec. Only structure participates.
    """
    return (
        _PART_TYPE_RANK[part.type],
        _PART_MODIFIER_RANK[part.modifier],
        part.prefix,
        part.value,
        part.suffix,
    )


@dataclass(slots=True)
class _ComponentMatcher:
    """Compiled regex + per-group metadata for one URL component.

    Caching the compiled regex object here means matching is a single
    C-level ``fullmatch`` call per component per ``test`` / ``exec``;
    everything Python-level (zip, dict construction) happens only on a
    successful match.

    ``apply_ecma_narrowing`` parallels ``name_list`` — one entry per
    capture group, in document order. It feeds the post-match fixup in
    :meth:`URLPattern.exec` that bridges the gap between Python's
    "matched empty" and JS's "didn't enter" semantics for optional
    groups. See the field's docstring below for the precise rule.

    ``has_custom_regexp`` is the per-component half of the spec's
    ``hasRegExpGroups`` predicate — true iff this component's part list
    contains any ``PartType.REGEXP`` part. The parser already collapses
    canonical wildcard regex bodies to ``SEGMENT_WILDCARD`` /
    ``FULL_WILDCARD`` types, so ``REGEXP`` here always means a custom
    (user-supplied) regex body — exactly what the spec wants the flag to
    track.
    """

    pattern_string: str
    regex: CompiledRegex
    name_list: list[str]
    # Per-capture-group flag indicating whether ECMA-262 §22.2.2.5.1's
    # "no progress on min=0 quantifier" narrowing applies. True iff the
    # part has modifier ``OPTIONAL`` AND no prefix/suffix — that's the
    # *only* part-to-regex emit shape (case 1a in :mod:`yarlpattern._regex`)
    # where the underlying engine and JS disagree on an empty match. For
    # parts with prefix/suffix (case 2), the outer iteration makes
    # progress consuming the prefix/suffix, so an inner empty capture is
    # genuinely ``""`` in both engines.
    apply_ecma_narrowing: list[bool]
    # Pre-built tuple of comparison keys, one per part, used by
    # :meth:`URLPattern.compareComponent`. Each key is
    # ``(type_rank, modifier_rank, prefix, value, suffix)``; assembled
    # once at compile time so every compare-call is a C-level tuple
    # comparison (no Python-level attribute access on ``Part``).
    compare_keys: tuple[tuple[int, int, str, str, str], ...]
    # Pre-parsed part list, kept around so :meth:`URLPattern.generate` can
    # walk the per-component template at substitution time without
    # re-tokenising. The list is treated as immutable after construction.
    parts: list[Part]
    # Per-component literal-encoding callback (see :meth:`_encoding_callback_for`).
    # ``generate`` runs the supplied group value through this so the substituted
    # text is in the same canonical form as a FIXED_TEXT slice of the same
    # component would be.
    encoder: EncodingCallback
    # The component's segment-wildcard regex body (``[^<delim>]+?``), captured
    # once so the per-part validator in :meth:`URLPattern.generate` can be
    # compiled lazily without re-deriving the options bundle.
    segment_wildcard_regex: str
    has_custom_regexp: bool = False


@dataclass(slots=True)
class URLPatternResult:
    """Result of a successful :meth:`URLPattern.exec` match.

    ``inputs`` echoes the arguments originally supplied to :meth:`URLPattern.exec`.
    Each component attribute holds a ``{"input": str, "groups": dict[str, str]}``
    mapping. Optional groups that did not capture anything are *omitted from*
    ``groups`` (rather than carrying a ``None`` value) so dict-equality
    comparisons against the WPT expectations work without translation — the
    WPT data uses JSON ``null`` to mean "undefined / key absent in JS".
    """

    inputs: list[URLPatternInput]
    protocol: dict[str, Any] | None = None
    username: dict[str, Any] | None = None
    password: dict[str, Any] | None = None
    hostname: dict[str, Any] | None = None
    port: dict[str, Any] | None = None
    pathname: dict[str, Any] | None = None
    search: dict[str, Any] | None = None
    hash: dict[str, Any] | None = None


class URLPattern:
    """A compiled WHATWG URL pattern.

    Construction accepts either a :class:`URLPatternInit` dict or a
    constructor *string* (e.g. ``"https://example.com/:foo"``) plus
    optional base URL and options. Each URL component has an independent
    parser-options bundle (delimiter / prefix code points) defined in the
    spec; components not present in the input default to the ``"*"``
    pattern (matches anything).

    The compiled regex matcher behind every component is produced by a
    *regex engine* selected via :mod:`yarlpattern._regex_engine`. The
    default engine auto-picks Matthew Barnett's ``regex`` package when
    importable (handles JS ``v``-flag set operations like ``[a&&b]``
    correctly) and falls back to stdlib :mod:`re` otherwise. Pass
    ``engine=...`` to override per-instance — useful for benchmarking
    or for shipping a custom backend.
    """

    __slots__ = (
        "_engine",
        "_matchers",
        "ignore_case",
        *COMPONENTS,
    )

    protocol: str
    username: str
    password: str
    hostname: str
    port: str
    pathname: str
    search: str
    hash: str

    def __init__(
        self,
        input: URLPatternInit | str | None = None,  # noqa: A002 - matches spec param name
        base_url_or_options: str | Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        /,
        *,
        engine: RegexEngine | None = None,
    ) -> None:
        # Regex engine selection follows the pluggable-backend pattern (see
        # :mod:`yarlpattern._regex_engine`): an explicit ``engine=`` argument
        # wins, otherwise we defer to the module-level default which
        # auto-picks the third-party ``regex`` package when installed and
        # falls back to stdlib ``re`` otherwise.
        self._engine: RegexEngine = engine if engine is not None else get_default_engine()
        # ----- Resolve the constructor overload.
        #
        # String input:   URLPattern(pattern_str, [base_url_str], [options])
        # Dict input:     URLPattern(init_dict, [options])
        #
        # The string form admits an *optional* base URL as a second
        # positional; the dict form does not (a base URL belongs inside the
        # dict). When the second positional is a string, that's only legal
        # for the string-input overload.
        explicit_pattern_base_url: str | None = None
        if isinstance(input, str):
            # §1.6: parse the constructor string into a partial init dict.
            # ``parse_constructor_string`` only populates components that
            # appeared in the input, leaving the rest to default-fill below.
            parsed = parse_constructor_string(input)
            if isinstance(base_url_or_options, str):
                explicit_pattern_base_url = base_url_or_options
                effective_options = options or {}
            else:
                # No baseURL given. Spec ``new URLPattern(input, options?)``
                # overload — the third slot must therefore be unused. A
                # string in slot three with a dict in slot two means the
                # user mixed up the argument order.
                if isinstance(options, str):
                    raise TypeError(
                        "URLPattern: argument order is "
                        "(pattern, baseURL?, options?); a string in slot three "
                        "with a non-string in slot two is invalid",
                    )
                effective_options = base_url_or_options or options or {}
            # A constructor *string* that produced no protocol MUST have a
            # baseURL — otherwise the pattern is hopelessly under-specified
            # (a bare ``/foo`` could be a special-scheme path or an opaque
            # path). Note this is specifically the string-input form;
            # dict-form with just ``{pathname: '/foo'}`` is fine (the user
            # opted into the ambiguity deliberately).
            if "protocol" not in parsed and explicit_pattern_base_url is None:
                raise TypeError(
                    f"URLPattern: relative constructor string {input!r} "
                    "must have a base URL passed as the second argument",
                )
            raw_init: Mapping[str, str] = parsed
        else:
            # Dict input — a string in the second slot is illegal here.
            if isinstance(base_url_or_options, str):
                raise TypeError(
                    "URLPattern: base URL is only accepted with a string pattern; "
                    "put 'baseURL' inside the init dict for the dict-form constructor",
                )
            effective_options = base_url_or_options or options or {}
            raw_init = input or {}
        # Pattern-side baseURL inheritance: fill missing pattern strings
        # with the corresponding URL components from the baseURL. The
        # baseURL can come from either an explicit second-positional argument
        # (string-input form) or a ``baseURL`` key inside the dict (dict-input
        # form); a positional wins if both are present.
        dict_base_url = raw_init.get("baseURL") if "baseURL" in raw_init else None
        effective_base_url = explicit_pattern_base_url if explicit_pattern_base_url is not None else dict_base_url
        bare_init = {k: v for k, v in raw_init.items() if k != "baseURL"}
        if effective_base_url is not None:
            # An explicit but empty baseURL is invalid — the URL parser
            # can't make anything of ``""`` and the spec mandates a
            # TypeError at construction.
            if effective_base_url == "":
                raise TypeError("URLPattern: baseURL must not be empty")
            init_map: dict[str, str] = apply_pattern_base_url(bare_init, effective_base_url)
        else:
            init_map = bare_init

        self.ignore_case = bool(effective_options.get("ignoreCase", False))

        # The protocol pattern string is needed verbatim to decide default-
        # port stripping for the port component and special-vs-opaque
        # pathname canonicalization. We compile it first so subsequent
        # components can read its post-§2.3 form off ``self``.
        # When the *raw* port init value parses cleanly as the default port
        # number for the protocol, replace it with the empty string before
        # compile. The match has to be *exact* — a strict-integer parse that
        # rejects trailing whitespace and any non-digit suffix, mirroring
        # how the spec algorithm reads the value. That preserves both:
        # * literal ``80`` inside compound patterns like ``80{20}?`` — those
        #   don't reduce to "exactly the default port" and don't strip;
        # * single-port-pattern strings like ``80 `` (trailing space) — the
        #   trailing space takes them out of this fast path and the
        #   per-slice whitespace strip handles the value at compile time.
        if "protocol" in init_map and "port" in init_map:
            proto = init_map["protocol"]
            port_val = init_map["port"]
            default_port = _DEFAULT_PORTS.get(proto)
            if default_port is not None and port_val == default_port:
                init_map = dict(init_map, port="")

        self._matchers: dict[str, _ComponentMatcher] = {}
        for component in COMPONENTS:
            if component in init_map:
                raw = _strip_component_prefix_suffix(component, init_map[component])
            else:
                # ``"*"`` is the spec-prescribed default — compiles to a
                # full-wildcard group that matches any input string.
                raw = "*"
            self._compile_component(component, raw)

    # --------------------------------------------------------------- compile
    def _compile_component(self, component: str, pattern_string: str) -> None:
        """Tokenize → parse → regex-compile a single component pattern."""
        opts = _COMPONENT_OPTIONS[component]
        # Pathname options diverge for opaque-path (non-special) URLs:
        # empty ``delimiter_list`` / ``prefix_list`` (no automatic
        # ``/``-prefix on segment wildcards) so that patterns like
        # ``data:text/javascript,let x = 100/:tens?5;`` parse with
        # ``:tens?`` as a bare optional wildcard, not as ``/`` + wildcard.
        # The decision uses the same "protocol matches special scheme"
        # predicate that drives the pathname encode callback.
        if component == "pathname" and not self._protocol_matches_special_scheme():
            opts = _DEFAULT_OPTS
        if self.ignore_case:
            opts = Options(
                delimiter_code_point=opts.delimiter_code_point,
                prefix_code_point=opts.prefix_code_point,
                ignore_case=True,
            )
        # Hostname patterns that *look* IPv6-shaped (per the §1.5 predicate)
        # take a separate encode callback that's lenient about pattern
        # fragments — a fixed-text slice like ``]`` or ``:1]`` would be
        # rejected by IDNA but is perfectly valid as part of an IPv6
        # pattern like ``[*]:1``. The decision is per-pattern (based on the
        # raw user input), not per-slice — that's what the spec mandates.
        callback: EncodingCallback
        if component == "hostname" and hostname_pattern_is_ipv6_address(pattern_string):
            callback = canonicalize_ipv6_hostname_slice
        else:
            callback = self._encoding_callback_for(component)
        parts = parse_pattern_string(pattern_string, opts, callback)
        regex_src, name_list = parts_to_regex(parts, opts)
        # Hand the regex source to the active engine. The engine handles
        # ASCII semantics, ignore-case flag, and any backend-specific
        # quirks (FutureWarning suppression, V1 flag, etc.) — all that
        # surfaces here is a :class:`CompiledRegex` or :class:`TypeError`.
        regex = self._engine.compile(regex_src, ignore_case=self.ignore_case)
        # The user-visible attribute is the part-list serialized back to a
        # pattern string per §2.3 — not the user's raw input. This is what
        # collapses ``/foo/(.*)`` to ``/foo/*``, normalizes spacing /
        # grouping, and otherwise round-trips the parser's understanding.
        canonical_pattern_string = parts_to_pattern_string(parts, opts)
        # Per spec, ``hasRegExpGroups`` is true iff any part has type
        # ``regexp`` with a value that's not the segment-wildcard or
        # full-wildcard regexp value. Our parser already coerces canonical
        # wildcard bodies to ``SEGMENT_WILDCARD`` / ``FULL_WILDCARD`` types,
        # so any remaining ``REGEXP`` part is by definition a custom body.
        has_custom_regexp = any(p.type is PartType.REGEXP for p in parts)
        # Per-group ECMA-262 narrowing flag — see :class:`_ComponentMatcher`
        # docstring. Only the non-FIXED-TEXT parts contribute capture
        # groups, so we filter to match the regex's group numbering.
        apply_ecma_narrowing = [
            (p.modifier is PartModifier.OPTIONAL and not p.prefix and not p.suffix)
            for p in parts
            if p.type is not PartType.FIXED_TEXT
        ]
        # Compare-key tuple for :meth:`compareComponent` — built once at
        # compile time so every comparison is a pure C-level tuple-compare.
        compare_keys = tuple(_part_to_compare_key(p) for p in parts)
        self._matchers[component] = _ComponentMatcher(
            canonical_pattern_string,
            regex,
            name_list,
            apply_ecma_narrowing,
            compare_keys,
            parts,
            callback,
            generate_segment_wildcard_regexp(opts),
            has_custom_regexp,
        )
        setattr(self, component, canonical_pattern_string)

    # ------------------------------------------------------------------ test
    def test(
        self,
        input: URLPatternInput | None = None,  # noqa: A002 - matches spec param name
        base_url: str | _YarlURL | None = None,
        /,
    ) -> bool:
        """Return ``True`` iff *input* matches every component pattern.

        Accepts a URL string, a per-component dict, or a :class:`yarl.URL`.
        A bare yarl URL is the fast path: its already-parsed components
        are read directly, skipping the str-form reparse — ideal for
        ``pat.test(request.url)`` in aiohttp / yarl-based applications.

        Per the WHATWG spec, exceptions raised while *processing the input*
        (URL parsing failures, invalid scheme characters, malformed IDNA,
        etc.) are caught and surface as a "no match". Exceptions during
        pattern *construction* still propagate; only the input-side
        processing is forgiving.
        """
        if not isinstance(input, str | _YarlURL) and base_url is not None:
            # Spec: a positional base URL is only meaningful with a string
            # input. With a dict input the base URL belongs inside the dict
            # under ``baseURL``.
            raise TypeError(
                "URLPattern.test: base URL argument requires a string input",
            )
        try:
            input_map = self._resolve_input(input, base_url)
            canonical = self._canonicalize_input_components(input_map)
        except (TypeError, ValueError):
            return False
        # Short-circuit on the first failing component — a missed protocol
        # makes pathname-matching cost moot.
        for component in COMPONENTS:
            if self._matchers[component].regex.fullmatch(canonical[component]) is None:
                return False
        return True

    # ------------------------------------------------------------------ exec
    def exec(
        self,
        input: URLPatternInput | None = None,  # noqa: A002 - matches spec param name
        base_url: str | _YarlURL | None = None,
        /,
    ) -> URLPatternResult | None:
        """Return a :class:`URLPatternResult` for *input* or ``None`` on miss.

        Accepts the same input shapes as :meth:`test`. A bare
        :class:`yarl.URL` is the fast path — its already-parsed
        components are read directly.

        Like :meth:`test`, exceptions during input processing surface as
        ``None`` (no match) rather than propagating to the caller.
        """
        if not isinstance(input, str | _YarlURL) and base_url is not None:
            raise TypeError(
                "URLPattern.exec: base URL argument requires a string input",
            )
        try:
            input_map = self._resolve_input(input, base_url)
            canonical = self._canonicalize_input_components(input_map)
        except (TypeError, ValueError):
            return None

        component_results: dict[str, dict[str, Any]] = {}
        for component in COMPONENTS:
            value = canonical[component]
            matcher = self._matchers[component]
            match = matcher.regex.fullmatch(value)
            if match is None:
                return None
            # Pair positional captures with their names; drop unmatched
            # optional groups (``None``) so equality vs. WPT expectations
            # works without a translation layer.
            #
            # ECMA-262 §22.2.2.5.1 narrowing: when a quantifier with
            # ``min == 0`` matches its inner pattern at a zero-width
            # position, the JS regex engine treats it as if the group
            # never entered (avoids the otherwise-infinite-loop case for
            # ``(...)*``). Python's ``re`` and the ``regex`` package both
            # report ``""`` instead, so we apply the narrowing here using
            # the parallel ``apply_ecma_narrowing`` recorded at compile
            # time — only on the *exact* part-to-regex emit shape where
            # the engines disagree (optional, no prefix/suffix).
            groups: dict[str, str] = {}
            captured_tuple = match.groups()
            for idx, (name, narrow, captured) in enumerate(
                zip(matcher.name_list, matcher.apply_ecma_narrowing, captured_tuple, strict=True),
            ):
                if captured is None:
                    continue
                if narrow and match.start(idx + 1) == match.end(idx + 1):
                    continue
                groups[name] = captured
            component_results[component] = {"input": value, "groups": groups}

        # ``inputs`` echoes the original argument list, in spec form: the
        # input value first, then the base URL string (only when one was
        # explicitly supplied — either as a positional or as a dict key).
        # Per spec, a ``None`` input is treated as an empty dict for the
        # purposes of the echo array — the inputs list is never empty
        # because :meth:`exec` always reflects the call shape back.
        original_inputs: list[URLPatternInput] = [input if input is not None else {}]
        if base_url is not None:
            original_inputs.append(base_url)
        return URLPatternResult(inputs=original_inputs, **component_results)

    # --------------------------------------------------------- callback wiring
    def _encoding_callback_for(self, component: str) -> EncodingCallback:
        """Return the encoding callback to apply to literal slices of *component*.

        Per-slice encoding diverges from whole-component canonicalization
        in two places:

        * **Port** — the per-slice callback validates digits + whitespace
          but does *not* strip the default port. Default-port strip runs
          once on the raw init value in :meth:`__init__`; doing it again
          per-slice would erase the literal ``80`` in a compound pattern
          like ``80{20}?``.
        * **Pathname** — needs the already-compiled protocol to pick
          between special-scheme and opaque-path canonicalization. The
          compile loop iterates components in spec order, so the protocol
          matcher is in ``self._matchers`` by the time we reach pathname.
        """
        if component == "port":
            return port_pattern_slice_encode
        if component == "pathname":
            is_special = self._protocol_matches_special_scheme()
            return lambda value: canonicalize_pathname(value, is_special=is_special)
        return _BASE_CALLBACKS[component]

    def _protocol_matches_special_scheme(self) -> bool:
        """Whether the compiled protocol regex matches any WHATWG special scheme.

        The pathname canonicalization depends on whether the protocol could
        ever match a special scheme. A pattern like ``"*"`` matches every
        special scheme (because the wildcard regex matches every string),
        so it gets the "special pathname" treatment — that's the behavior
        the WPT suite assumes.
        """
        matcher = self._matchers.get("protocol")
        if matcher is None:
            # Called before the protocol component has been compiled — the
            # caller is using the conservative default.
            return True
        return any(matcher.regex.fullmatch(s) is not None for s in SPECIAL_SCHEMES)

    def _canonicalize_input_components(
        self,
        input_map: Mapping[str, str],
    ) -> dict[str, str]:
        """Canonicalize every input component in spec order.

        Done in order because port and pathname read the *already-
        canonicalized* protocol of the input — not the pattern's protocol.
        For an input ``{"protocol": "https", "port": "443"}`` the default
        port strips to ``""`` because ``input.protocol`` is ``"https"``,
        regardless of what protocol pattern the URLPattern itself uses.
        """
        out: dict[str, str] = {}
        for component in COMPONENTS:
            raw = input_map.get(component, "")
            if component == "port":
                out[component] = canonicalize_port(raw, out.get("protocol", ""))
            elif component == "pathname":
                # Empty protocol counts as special. The relevant test is
                # "non-empty AND not in special set" before routing to the
                # opaque-path branch, so an input with only a pathname (no
                # protocol) still gets dot-segment collapse.
                proto = out.get("protocol", "")
                is_special = proto == "" or proto in SPECIAL_SCHEMES
                out[component] = canonicalize_pathname(raw, is_special=is_special)
            else:
                out[component] = _BASE_CALLBACKS[component](raw)
        return out

    # ----------------------------------------------------------- input plumb
    def _resolve_input(
        self,
        input_: URLPatternInput | None,
        base_url: str | _YarlURL | None,
    ) -> dict[str, str]:
        """Normalize *input_* (+ optional *base_url*) into a complete component dict.

        Four shapes flow in:

        * ``None`` → no input; every component matches against the empty
          string (which is what a default ``*`` pattern accepts).
        * a :class:`yarl.URL` → fast path: read components directly off
          the already-parsed URL, skipping the str-form reparse. When a
          *base_url* is supplied, resolve the URL against it via yarl's
          ``.join`` first.
        * a string → parse as a URL, optionally resolved against
          ``base_url`` per WHATWG semantics. The parsed components become
          the match input.
        * a dict → use the user's component strings as-is, with optional
          ``baseURL`` (either as a dict key or as the positional argument)
          filling in components not present in the dict. Unlike the
          pattern side, ``username`` / ``password`` *do* inherit from an
          input baseURL — the input is meant to give the matcher a fully
          materialized URL context.
        """
        if input_ is None:
            return {}

        if isinstance(input_, _YarlURL):
            # Fast path: yarl already parsed the URL — extract components
            # directly. If a base URL is supplied, resolve against it via
            # yarl's :meth:`URL.join` (semantically equivalent to what
            # ``parse_url`` does internally, minus the str-form
            # special-scheme ``//`` injection that only matters when the
            # user typed a malformed URL string).
            if base_url is None:
                return dict(cast("dict[str, str]", _components_from_yarl(input_)))
            base = base_url if isinstance(base_url, _YarlURL) else _YarlURL(str(base_url))
            joined = base.join(input_)
            # Match ``parse_url``'s WHATWG-compatible fragment-drop on
            # relative inputs that don't carry their own fragment.
            if not input_.fragment:
                joined = joined.with_fragment(None)
            return dict(cast("dict[str, str]", _components_from_yarl(joined)))

        if isinstance(input_, str):
            # ``parse_url`` only accepts string base URLs; coerce a yarl URL
            # via ``str()`` so callers can pass either shape interchangeably.
            base_url_str = str(base_url) if isinstance(base_url, _YarlURL) else base_url
            components = parse_url(input_, base_url_str)
            # TypedDict is structurally identical to ``dict[str, str]`` at
            # runtime; ``cast`` here is a no-op at runtime but lets mypy
            # accept the narrower TypedDict view as a plain dict.
            return dict(cast("dict[str, str]", components))

        raw = dict(input_)
        dict_base = raw.pop("baseURL", None)
        # An explicit positional baseURL takes precedence over a dict key —
        # the spec lets either form supply the base, and the positional is
        # the more recent / typically authoritative one when both are given.
        effective_base = base_url if base_url is not None else dict_base
        if effective_base is not None:
            # ``apply_input_base_url`` accepts string base URLs only; yarl
            # URLs are stringified here. The cost is one ``str()`` on the
            # dict-form path (rare; the hot path is yarl-URL input).
            effective_base_str = str(effective_base) if isinstance(effective_base, _YarlURL) else effective_base
            return apply_input_base_url(raw, effective_base_str)
        return raw

    # ------------------------------------------------------------------- misc
    @property
    def has_regexp_groups(self) -> bool:
        """Whether any compiled component contains a custom regex body.

        Spec definition: true iff any component's part list has a part whose
        type is ``regexp`` and whose value is not the segment-wildcard or
        full-wildcard regexp value. The per-component bool was set at
        compile time from the parts list; aggregating here is a tight
        ``any()`` over the matchers (returns on first hit, no allocations).
        """
        return any(m.has_custom_regexp for m in self._matchers.values())

    @staticmethod
    def compareComponent(  # noqa: N802 — matches the WHATWG IDL method name
        component: str,
        left: URLPattern,
        right: URLPattern,
    ) -> int:
        """Three-way ordering of two patterns along a single component.

        Returns ``-1`` / ``0`` / ``1`` per the (tentative) WHATWG
        ``URLPattern.compareComponent`` specification. The ordering ranks
        patterns by *specificity*: a fully literal component outranks one
        with a regex group, which outranks a segment wildcard, which
        outranks a full wildcard. Within a type, modifiers further refine
        (mandatory > one-or-more > optional > zero-or-more), and within
        a (type, modifier) the prefix / value / suffix strings are
        compared lexicographically. Names are not part of the order.

        The comparison runs on the *parsed part list*, not the user's
        raw input — so ``/foo/{bar}/baz`` and ``/foo/bar/baz`` compare
        equal even though the surface strings differ. An entirely empty
        component is treated as ``*``.

        Raises :class:`TypeError` if *component* is not one of the eight
        spec-defined names.
        """
        if component not in COMPONENTS:
            msg = f"URLPattern.compareComponent: unknown component {component!r}; expected one of {COMPONENTS}"
            raise TypeError(msg)
        # Empty part lists stand in for ``*`` — see ``_FULL_WILDCARD_ONLY_KEYS``.
        # Calling ``.compare_keys or _FULL_WILDCARD_ONLY_KEYS`` is a free
        # truthiness check on an empty tuple; allocates nothing.
        l_keys = left._matchers[component].compare_keys or _FULL_WILDCARD_ONLY_KEYS
        r_keys = right._matchers[component].compare_keys or _FULL_WILDCARD_ONLY_KEYS
        # Fast path: two patterns with structurally identical parts share
        # equal compare_keys. The tuple-of-tuples ``==`` is a single
        # C-level call that short-circuits on first mismatch.
        if l_keys == r_keys:
            return 0
        # Lexicographic walk with synthetic-empty-FIXED padding for the
        # length-mismatch case (which makes ``/foo/`` outrank ``/foo/*``).
        for lk, rk in zip_longest(l_keys, r_keys, fillvalue=_EMPTY_FIXED_KEY):
            if lk != rk:
                return -1 if lk < rk else 1
        return 0

    # -------------------------------------------------------------- generate
    def generate(self, component: str, groups: Mapping[str, str] | None = None) -> str:
        """Produce the URL-component string that *this* pattern would have matched.

        ``generate`` reverses :meth:`exec`: given a *component* name (one of
        the eight WHATWG components) and a mapping of named-group values,
        emit the canonical-form string that, fed back through :meth:`exec`,
        would yield the same groups.

        This is a *tentative* spec feature — see
        ``urlpattern-generate.tentative.any.js`` in the upstream WPT suite.
        The 19 WPT conformance cases for ``generate()`` ship with
        yarlpattern at
        ``reference/wpt/urlpattern/resources/urlpattern-generate-test-data.json``;
        the public algorithm is anchored in those cases. yarlpattern's
        implementation is a direct walk over the per-component parsed
        part-list built at construction time.

        Raises :class:`TypeError` for any of these conditions:

        - *component* is not one of the eight known names;
        - a part with a modifier (``?``, ``*``, ``+``) — those are not
          uniquely reversible;
        - a standalone full wildcard (``*``) or an anonymous regex group
          — there is no named group to substitute into;
        - a required named group is missing from *groups*;
        - the encoded substitution would violate the part's own
          constraint (e.g. ``"bar/baz"`` substituted into ``:foo`` in a
          pathname component, where the segment-wildcard rejects ``/``).
        """
        if component not in COMPONENTS:
            msg = f"URLPattern.generate: unknown component {component!r}; expected one of {COMPONENTS}"
            raise TypeError(msg)
        matcher = self._matchers[component]
        group_map: Mapping[str, str] = groups if groups is not None else {}

        chunks: list[str] = []
        for part in matcher.parts:
            # Hoisted: a modifier on *any* kind of part means the part can
            # appear 0, 1, or many times in a matching string. ``generate``
            # has no signal for how many times to emit, so the only safe
            # answer is TypeError. This covers FIXED_TEXT parts that came
            # from ``{...}<modifier>`` syntax (WPT cases 13–15) as well as
            # modified variable parts.
            if part.modifier is not PartModifier.NONE:
                msg = (
                    f"URLPattern.generate: part {part.name or part.value!r} carries "
                    f"modifier {part.modifier.value!r}; modified parts are not uniquely "
                    f"reversible"
                )
                raise TypeError(msg)
            if part.type is PartType.FIXED_TEXT:
                # The part value is already canonical-form ASCII from compile
                # time — no re-encoding needed.
                chunks.append(part.value)
                continue
            if part.type is PartType.FULL_WILDCARD:
                msg = "URLPattern.generate: a standalone full-wildcard part has no named group to substitute"
                raise TypeError(msg)
            # SEGMENT_WILDCARD / REGEXP without a (non-anonymous) name:
            # path-to-regexp numbers anonymous groups "0", "1", ... so
            # ``isdigit()`` is the spec-aligned anonymity check.
            if not part.name or part.name.isdigit():
                msg = f"URLPattern.generate: anonymous {part.type.value} part cannot be addressed by name"
                raise TypeError(msg)
            if part.name not in group_map:
                msg = f"URLPattern.generate: required group {part.name!r} missing from groups argument"
                raise TypeError(msg)
            encoded = matcher.encoder(group_map[part.name])
            validator = self._compile_part_validator(matcher, part)
            if validator.fullmatch(encoded) is None:
                msg = (
                    f"URLPattern.generate: encoded value {encoded!r} for group "
                    f"{part.name!r} does not satisfy the part's constraint"
                )
                raise TypeError(msg)
            chunks.append(part.prefix)
            chunks.append(encoded)
            chunks.append(part.suffix)

        return "".join(chunks)

    def _compile_part_validator(self, matcher: _ComponentMatcher, part: Part) -> CompiledRegex:
        """Compile a regex that fullmatches values legal for *part*.

        Per-part validation only runs from :meth:`generate`, which is a
        cold path; compiling fresh per call (rather than caching on the
        matcher) keeps the construction-time work strictly on the
        :meth:`test` / :meth:`exec` hot path.
        """
        if part.type is PartType.REGEXP:
            body = part.value
        else:  # SEGMENT_WILDCARD — FULL_WILDCARD was already rejected upstream.
            body = matcher.segment_wildcard_regex
        # Same JS→Python regex translation the full-component compile applies
        # (see :func:`_translate_js_regex_to_python`). The only case that
        # actually rewrites is the segment-wildcard with empty delimiter
        # (``[^]+?`` → ``[\s\S]+?``), which is what fires for the
        # non-special-scheme pathname options.
        body = _translate_js_regex_to_python(body)
        return self._engine.compile(body, ignore_case=self.ignore_case)

    # --------------------------------------------------------------- dunders
    def __repr__(self) -> str:
        parts = ", ".join(f"{c}={getattr(self, c)!r}" for c in COMPONENTS)
        return f"URLPattern({parts})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, URLPattern):
            return NotImplemented
        return all(getattr(self, c) == getattr(other, c) for c in COMPONENTS)

    def __hash__(self) -> int:
        return hash(tuple(getattr(self, c) for c in COMPONENTS))

    def with_(self, **components: str) -> Self:
        """Return a copy of this pattern with selected components replaced."""
        new_init: dict[str, str] = {c: getattr(self, c) for c in COMPONENTS}
        new_init.update(components)
        return type(self)(new_init)

    # ------------------------------------------------ yarl-style with_* methods
    #
    # Single-component derivers — sugar around :meth:`with_` for callers
    # who like yarl's per-component method shape. Component *names* still
    # follow the WHATWG URLPattern spec (``protocol`` not ``scheme``,
    # ``hostname`` not ``host``, etc.) because that's what the rest of
    # the API exposes; this is purely a convenience wrapper.

    def with_protocol(self, protocol: str) -> Self:
        """Return a copy with ``protocol`` replaced."""
        return self.with_(protocol=protocol)

    def with_username(self, username: str) -> Self:
        """Return a copy with ``username`` replaced."""
        return self.with_(username=username)

    def with_password(self, password: str) -> Self:
        """Return a copy with ``password`` replaced."""
        return self.with_(password=password)

    def with_hostname(self, hostname: str) -> Self:
        """Return a copy with ``hostname`` replaced."""
        return self.with_(hostname=hostname)

    def with_port(self, port: str) -> Self:
        """Return a copy with ``port`` replaced."""
        return self.with_(port=port)

    def with_pathname(self, pathname: str) -> Self:
        """Return a copy with ``pathname`` replaced."""
        return self.with_(pathname=pathname)

    def with_search(self, search: str) -> Self:
        """Return a copy with ``search`` replaced."""
        return self.with_(search=search)

    def with_hash(self, hash: str) -> Self:  # noqa: A002 — spec param name
        """Return a copy with ``hash`` replaced."""
        return self.with_(hash=hash)
