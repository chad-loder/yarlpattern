"""WHATWG URLPattern §3 — per-component canonicalization callbacks.

Each function here takes a *single literal slice* of a pattern (or a full
input component string) and returns it in WHATWG canonical form: lowercased
protocol, percent-encoded userinfo / path / query / fragment, IDNA-encoded
hostnames, default-port-stripped ports, dot-segment-collapsed paths.

Two callers wire into these:

1. **Pattern parsing** (the encoding callback hook in :mod:`yarlpattern._parts`)
   — invoked once per literal slice during tokenization+parsing. Slices
   never contain pattern syntax (``:name``, ``*``, ``(...)`` are token kinds,
   handled separately), so we can canonicalize freely.

2. **Input matching** (:meth:`URLPattern.test` / :meth:`URLPattern.exec`)
   — invoked once per component input string before running the compiled
   regex. The same canonicalize functions are reused so both sides converge
   on the same byte sequence.

Idempotency is critical: ``caf%C3%A9`` must round-trip unchanged, while
``café`` must encode to ``caf%C3%A9``. Percent-encoding is implemented
in-module (table-driven with a detect-then-encode fast-path bail-out —
see :func:`_percent_encode`) rather than delegated to yarl, because the
WHATWG case-preservation rule for *existing* ``%XX`` sequences
(uppercase or lowercase, preserved verbatim) is not what yarl's quoter
does. Hostname IDNA / UTS #46 *is* delegated to yarl (:class:`yarl.URL`
in turn uses the ``idna`` package).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from yarl import URL

# ----------------------------------------------------------- percent-encoder
#
# We roll our own percent-encoder rather than going through yarl's quoter
# because the WHATWG URL spec requires preserving the case of *existing*
# percent-encoded sequences while emitting *newly* encoded bytes in upper
# case. yarl normalizes everything to upper case at quote time — fine for
# URL canonicalization, wrong for URLPattern where the WPT suite pins
# down the case-preservation behavior (cases 146 vs. 148 contrast on
# exactly this).
#
# Performance strategy — a "detect-then-encode" split inspired by the
# ``percent_encode_index`` idiom (Ada's ``unicode-inl.h``, and the
# iterator-yields-the-whole-input short-circuit in Rust's
# ``percent_encoding`` crate take a similar shape):
#
# 1. **Fast path** — a precompiled regex per encode set detects whether
#    *any* input char would need encoding. For real-world URL components
#    that are already in canonical form (the dominant case in any
#    routing workload), this returns ``None`` after a single C-level
#    scan and the function returns the original string with zero
#    allocation.
#
# 2. **Slow path** (:func:`_percent_encode_slow`) — encode to UTF-8 bytes
#    once, walk byte-by-byte using a precomputed 256-entry output
#    table per encode set. Each iteration is a single bytes-index
#    lookup + tuple-index lookup + list append (all C-level inside
#    CPython). The ``%XX`` passthrough check is folded inline.
#
# The encode set for each component is defined as a frozenset of *chars
# beyond the C0 + non-ASCII baseline that should also be percent-encoded*.
# WHATWG specifies the sets nested — query ⊂ path ⊂ userinfo, etc. — and
# we mirror that with set union so each definition stays one line of intent.

# Precomputed once at import: byte value → "%XX" string. Built once
# globally, shared across every encode set's output table.
_PERCENT_HEX: Final[tuple[str, ...]] = tuple(f"%{b:02X}" for b in range(256))

# Hex bytes for the slow path's ``%XX`` passthrough detection. Stored
# as a frozenset of int so membership is a C-level set lookup against
# ``bytes[i]`` (which yields int in Python 3).
_HEX_BYTES: Final[frozenset[int]] = frozenset(b"0123456789ABCDEFabcdef")

# Translation table mapping every UTF-16 surrogate code point (D800-DFFF)
# to U+FFFD REPLACEMENT CHARACTER. WHATWG requires surrogate halves to
# be replaced before UTF-8 encoding — Python's ``str.encode('utf-8')``
# raises on them otherwise. The translate call is C-level; we only run
# it on the surrogate-bearing exception path.
_SURROGATE_TRANS: Final[dict[int, str]] = dict.fromkeys(range(0xD800, 0xE000), "�")

# Fragment percent-encode set: C0 + SPACE + " < > `
_FRAGMENT_EXTRA: Final[frozenset[str]] = frozenset(' "<>`')

# Query percent-encode set: C0 + SPACE + " # < >
_QUERY_EXTRA: Final[frozenset[str]] = frozenset(' "#<>')

# Path percent-encode set: query + ? ` { }
_PATH_EXTRA: Final[frozenset[str]] = _QUERY_EXTRA | frozenset("?`{}")

# Userinfo percent-encode set: path + / : ; = @ [ \ ] ^ |
_USERINFO_EXTRA: Final[frozenset[str]] = _PATH_EXTRA | frozenset("/:;=@[\\]^|")


@dataclass(frozen=True, slots=True)
class _EncodeSet:
    """Precomputed lookup bundle for one WHATWG percent-encode set.

    Each set (fragment / query / path / userinfo / opaque-path) builds
    one of these at import time. The bundle holds:

    * ``needs_encode_re`` — a regex matching the first char that would
      require encoding. Used by :func:`_percent_encode` for the
      fast-path bail-out.
    * ``output_table`` — a 256-entry tuple mapping each possible UTF-8
      byte value to either the unchanged single-char string (when the
      byte is a safe pass-through) or its precomputed ``"%XX"`` form.
    """

    needs_encode_re: re.Pattern[str]
    output_table: tuple[str, ...]


def _make_encode_set(extra: frozenset[str]) -> _EncodeSet:
    """Compile a fast-lookup bundle for the given encode-set extras.

    The fast-path regex matches any char that *unconditionally* needs
    encoding: C0 controls, DEL + non-ASCII, plus the set's extras. A
    bare ``%`` not followed by two hex digits is *not* matched, to
    preserve WHATWG idempotency — already-encoded inputs round-trip
    unchanged.
    """
    extras_class = "".join(re.escape(c) for c in sorted(extra))
    needs_encode_re = re.compile(f"[\\x00-\\x1f\\x7f-\\U0010ffff{extras_class}]")
    output_table = tuple(chr(b) if 0x20 <= b < 0x7F and chr(b) not in extra else _PERCENT_HEX[b] for b in range(256))
    return _EncodeSet(needs_encode_re, output_table)


_FRAGMENT_SET: Final[_EncodeSet] = _make_encode_set(_FRAGMENT_EXTRA)
_QUERY_SET: Final[_EncodeSet] = _make_encode_set(_QUERY_EXTRA)
_PATH_SET: Final[_EncodeSet] = _make_encode_set(_PATH_EXTRA)
_USERINFO_SET: Final[_EncodeSet] = _make_encode_set(_USERINFO_EXTRA)
# Opaque-path: only C0 controls and non-ASCII are encoded. Space, ``?``,
# ``#`` etc. all pass through.
_OPAQUE_PATH_SET: Final[_EncodeSet] = _make_encode_set(frozenset())


def _percent_encode(value: str, encode_set: _EncodeSet) -> str:
    """WHATWG percent-encoding with case-preserving ``%XX`` passthrough.

    See the module-level "Performance strategy" comment for the
    two-phase design. The function is the canonical hot path under
    :mod:`yarlpattern._pattern`'s match pipeline — it runs once per
    non-empty URL component per ``.test()`` / ``.exec()`` call.
    """
    if encode_set.needs_encode_re.search(value) is None:
        return value
    return _percent_encode_slow(value, encode_set.output_table)


def _percent_encode_slow(value: str, output_table: tuple[str, ...]) -> str:
    """Slow-path encoder. Called from :func:`_percent_encode` only.

    Encodes to UTF-8 bytes once and walks the result; every per-byte
    step is a tuple-index lookup + list append (both C-level). Existing
    ``%XX`` sequences are passed through verbatim to preserve the
    user's hex case. Unpaired surrogates are pre-substituted with
    U+FFFD per the WHATWG scalar-value requirement; the substitution
    runs only when ``str.encode`` actually raises (i.e. surrogate
    halves are present), so the common slow-path case pays nothing.
    """
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = value.translate(_SURROGATE_TRANS).encode("utf-8")

    out: list[str] = []
    append = out.append
    n = len(encoded)
    i = 0
    while i < n:
        b = encoded[i]
        # Existing ``%XX`` sequence — case-preserving passthrough. The
        # hex-byte check uses int membership against a frozenset; no
        # decoding needed for the probe.
        if b == 0x25 and i + 2 < n and encoded[i + 1] in _HEX_BYTES and encoded[i + 2] in _HEX_BYTES:
            append(encoded[i : i + 3].decode("ascii"))
            i += 3
            continue
        append(output_table[b])
        i += 1
    return "".join(out)


# -------------------------------------------------------------------- protocol

# §3.1: protocol is restricted to scheme syntax — a letter followed by any
# number of ``[A-Za-z0-9+.-]``. We allow the empty match for the pattern-slice
# case where the slice is whatever literal text appeared between tokens
# (e.g. ``http`` from ``http*``).
_PROTOCOL_RE: Final = re.compile(r"^[-+.A-Za-z0-9]*$")


def canonicalize_protocol(value: str) -> str:
    """Lowercase + validate scheme-character syntax. Empty → empty."""
    if not value:
        return value
    if not _PROTOCOL_RE.match(value):
        raise TypeError(f"URLPattern: invalid protocol component {value!r}")
    return value.lower()


# ---------------------------------------------------- username / password


def canonicalize_username(value: str) -> str:
    """Percent-encode using the WHATWG userinfo encode set.

    Idempotent: already-encoded sequences pass through unchanged with their
    original hex case preserved.
    """
    if not value:
        return value
    return _percent_encode(value, _USERINFO_SET)


def canonicalize_password(value: str) -> str:
    """Percent-encode using the WHATWG userinfo encode set."""
    if not value:
        return value
    return _percent_encode(value, _USERINFO_SET)


# ---------------------------------------------------- hostname (IDNA + IPv6)

# Characters that must not appear in a domain hostname after pre-processing
# (whitespace removal + structural-delimiter truncation). Anything in this
# set is a definite parse error. IPv6 inputs (bracketed) take a different
# path and don't hit this regex. Note that ``?``, ``/``, ``#``, and ``\``
# are intentionally absent — they trigger truncation, not rejection (the
# WHATWG URL parser treats ``\`` as ``/`` for special schemes).
_INVALID_HOSTNAME_RE: Final = re.compile(r"[ #%:<>@\[\]^|]")

# Hostname pattern truncation at URL-structural delimiters. In a full URL
# these characters
# delimit hostname from search / pathname / hash (and ``\`` is normalized to
# ``/`` for special schemes), so a user-supplied hostname pattern containing
# them was very likely a paste of a full URL; respecting the prefix is more
# useful than rejecting wholesale.
#
# Implementation: a single precompiled regex is the fastest way to locate
# the first hit — ``.search`` returns ``None`` immediately on the common
# no-delimiter path. The C-level scan over a 4-char class is faster than
# four separate ``str.find`` calls + ``min`` (each ``find`` is C-level too
# but allocates an index object, and the minimum aggregation is Python-level).
_HOSTNAME_STRIP_RE: Final = re.compile(r"[?/#\\]")

_IPV6_HEX_BRACKET_COLON_RE: Final = re.compile(r"^[0-9a-fA-F\[\]:.]+$")

# A *slice* of an IPv6 hostname pattern (a fixed-text fragment between
# pattern tokens) is restricted to hex digits + ``[``, ``]``, ``:`` —
# anything else is a parse error. The regex matches the *forbidden* set
# (i.e. any char NOT in the allow list) so a single ``.search`` call
# short-circuits on the first hit, which is the common-case shape for
# "did the slice contain something weird".
_IPV6_SLICE_FORBIDDEN_RE: Final = re.compile(r"[^0-9a-fA-F\[\]:]")


def _treat_as_ipv6_hostname(value: str) -> bool:
    """An IPv6 host begins with ``[`` per WHATWG; anything else is a domain."""
    return value.startswith("[")


def canonicalize_hostname(value: str) -> str:
    """Apply IDNA (UTS #46) to a domain host, or hex-validate an IPv6 host.

    The approach is to do explicitly what other implementations get for free
    by routing the host through their URL parser — there are two WHATWG URL
    behaviors that a naive IDNA-only path would miss:

    1. The URL parser strips ``\\t``, ``\\n``, ``\\r`` from the input (URL
       §1.4 "remove all ASCII tab or newline from input"). We apply the
       same single-pass ``str.translate`` table here.
    2. For special schemes, the parser treats ``\\`` as ``/`` and stops
       parsing the hostname at the first of ``/``, ``?``, ``#``, or ``\\``.
       We truncate before handing off to yarl to match that.

    The truncation runs on every hostname slice during pattern compilation
    *and* on every dict-form input hostname during matching. The
    ``re.search`` over a 4-char class returns ``None`` immediately on the
    common no-delimiter path (one C-level scan, no allocations).
    """
    if not value:
        return value
    if _treat_as_ipv6_hostname(value):
        return _canonicalize_ipv6_hostname(value)
    # WHATWG URL §1.4: strip ASCII tab / LF / CR before any other processing.
    value = value.translate(_URL_WHITESPACE_REMOVAL)
    if not value:
        return value
    # Truncate at the first URL-structural delimiter.
    strip_match = _HOSTNAME_STRIP_RE.search(value)
    if strip_match is not None:
        value = value[: strip_match.start()]
        if not value:
            return value
    if _INVALID_HOSTNAME_RE.search(value):
        raise TypeError(f"URLPattern: invalid hostname {value!r}")
    try:
        return URL.build(scheme="x", host=value).raw_host or ""
    except (ValueError, UnicodeError) as exc:
        raise TypeError(f"URLPattern: invalid hostname {value!r}") from exc


def hostname_pattern_is_ipv6_address(value: str) -> bool:
    """§1.5 "hostname pattern is an IPv6 address".

    The predicate is intentionally coarse: it only triggers on patterns that
    *look* IPv6-shaped at the very start. A bare ``[`` (raw IPv6), a ``{[``
    (IPv6 wrapped in a non-capturing group), or a ``\\[`` (escaped bracket
    intending to begin an IPv6 literal). Anything else routes to the
    normal IDNA hostname compile.
    """
    if len(value) < 2:
        return False
    return value.startswith(("[", "{[", "\\["))


def canonicalize_ipv6_hostname_slice(value: str) -> str:
    """Lenient per-slice IPv6 hostname encode callback.

    A fixed-text fragment of an IPv6 pattern can contain only hex digits,
    ``[``, ``]``, ``:``. The result is lowercased; we deliberately do *not*
    run the URL parser's IPv6 canonicalizer here because the slice might be
    incomplete (``[``, ``]``, ``[*``, ``:1]``, etc.) — only the assembled
    regex sees the full thing.

    Empty slices pass through unchanged.
    """
    if not value:
        return value
    if _IPV6_SLICE_FORBIDDEN_RE.search(value) is not None:
        raise TypeError(f"URLPattern: invalid IPv6 hostname slice {value!r}")
    return value.lower()


def _canonicalize_ipv6_hostname(value: str) -> str:
    """Lowercase + hex/bracket/colon validation for an IPv6 literal.

    We deliberately do **not** route through yarl here: yarl's ``URL.build``
    strips IPv6 brackets, but URLPattern wants the bracketed canonical form
    (e.g. ``[::1]``). A lightweight in-place validation is enough — full
    IPv6 normalization (collapsing zero runs, etc.) is rare in patterns and
    can land later if WPT needs it.
    """
    if not _IPV6_HEX_BRACKET_COLON_RE.match(value):
        raise TypeError(f"URLPattern: invalid IPv6 hostname {value!r}")
    return value.lower()


# -------------------------------------------------------------------- port

# Default ports for the four special schemes that URLPattern needs to handle.
# The spec strips a port that matches its scheme's default during
# canonicalization — ``http://x:80`` round-trips with no explicit port.
_DEFAULT_PORTS: Final[dict[str, str]] = {
    "http": "80",
    "ws": "80",
    "https": "443",
    "wss": "443",
    "ftp": "21",
}

# The WHATWG "special schemes" — these get dot-segment-collapsed paths,
# default-port stripping, and a few other normalization rules. Anything
# outside this set is treated as an opaque-path scheme. Shared with
# :mod:`yarlpattern._pattern` for the protocol-regex check.
SPECIAL_SCHEMES: Final[frozenset[str]] = frozenset(
    {"http", "https", "ws", "wss", "ftp", "file"},
)

# Match a leading run of digits — the URL parser's port-state behavior under
# "state override" (which is what the URL.port setter uses): consume digits,
# emit the accumulated number at the first non-digit. So ``"80 "`` and
# ``"80abc"`` both yield port ``80``; ``"abc"`` yields the empty port.
_PORT_DIGIT_PREFIX: Final = re.compile(r"^[0-9]+")


def canonicalize_port(value: str, protocol: str = "") -> str:
    """Implement §3.1 "canonicalize a port".

    Mirrors the URL parser's port-state with state-override: strip ASCII
    tab/newline/CR, extract the leading digit run, validate the resulting
    number is in [0, 65535], and strip the default port when the protocol
    matches a special scheme with that default.

    Used as the *whole-value* port canonicalizer (for inputs and for
    pre-compile pattern normalization). The per-slice encode callback
    used during pattern compile is :func:`port_pattern_slice_encode`,
    which skips the default-port strip.
    """
    canonical = _port_validate_and_canonicalize(value)
    if canonical and _DEFAULT_PORTS.get(protocol) == canonical:
        return ""
    return canonical


def port_pattern_slice_encode(value: str) -> str:
    """Per-slice encode callback for port patterns.

    Validates the slice as port-like (whitespace + digits) but does
    *not* strip the default port — that step belongs to the whole-pattern
    pass in :func:`canonicalize_port` because it would otherwise erase
    the literal ``80`` slice in a compound pattern like ``80{20}?``,
    where the literal is part of a larger expression that doesn't reduce
    to "exactly the default port number".
    """
    return _port_validate_and_canonicalize(value)


def _port_validate_and_canonicalize(value: str) -> str:
    """Shared port validation logic used by both code paths.

    ASCII whitespace strip → leading-digit-run extract → range validate.
    Raises :class:`TypeError` on malformed input (non-digit content with
    no leading digits, or numeric content >65535).
    """
    value = value.translate(_URL_WHITESPACE_REMOVAL)
    if not value:
        return value
    digit_match = _PORT_DIGIT_PREFIX.match(value)
    if digit_match is None:
        raise TypeError(f"URLPattern: invalid port {value!r}")
    canonical = str(int(digit_match.group(0)))  # strips leading zeros
    if int(canonical) > 65535:
        raise TypeError(f"URLPattern: port out of range {value!r}")
    return canonical


# WHATWG URL §1.4 "remove all ASCII tab or newline from input". A single
# pre-built translation table is roughly an order of magnitude faster than
# the equivalent ``str.replace`` chain.
_URL_WHITESPACE_REMOVAL: Final = str.maketrans("", "", "\t\n\r")


# ---------------------------------------------------------------- pathname


def canonicalize_pathname(value: str, *, is_special: bool = True) -> str:
    """Percent-encode + (special-scheme only) dot-segment-collapse the pathname.

    The two code paths correspond to WHATWG's "special URL" vs "opaque
    path" distinction:

    * **Special schemes** (http/https/ws/wss/ftp/file) use the *path
      percent-encode set* (space, ``"``, ``#``, ``<``, ``>``, ``?``, `` ` ``,
      ``{``, ``}``) and then run RFC 3986 §5.2.4 dot-segment removal.
    * **Opaque-path schemes** (javascript, data, mailto, etc.) use only the
      *C0 control percent-encode set* (C0 controls + non-ASCII) — space,
      ``?``, ``#`` etc. pass through unchanged because the WHATWG URL
      "opaque path state" doesn't encode them. Skipping dot-segment removal
      is correct here too: an opaque path has no ``/`` hierarchy.

    Hex case in any pre-existing ``%XX`` sequences is preserved. We can't
    route through yarl for dot-segment removal because :class:`yarl.URL`
    upper-cases percent sequences during parse — implementing the RFC
    3986 §5.2.4 algorithm directly in Python lets us keep the user's
    original case while still collapsing ``/foo/../bar`` to ``/bar``.
    """
    if not value:
        return value

    if not is_special:
        # Opaque-path scheme: only C0 controls and non-ASCII are encoded.
        # See :data:`_OPAQUE_PATH_SET` for the precomputed lookup tables.
        return _percent_encode(value, _OPAQUE_PATH_SET)

    encoded = _percent_encode(value, _PATH_SET)
    # Dot-segment trick: when the input is a *slice* of a larger pattern
    # (e.g. the fixed-text ``.`` between a segment-wildcard and the next
    # ``/``), running dot-segment removal naively would treat the whole
    # slice as a single dot-segment and erase it — wrong, because in
    # context it's just a literal ``.``. Prepending ``/-`` anchors the
    # slice as a non-dot path so the URL parser preserves it; we strip
    # ``/-`` back off the result. The leading-slash case stays in the
    # natural dot-segment-removal flow.
    if not encoded.startswith("/"):
        prefixed = _remove_dot_segments("/-" + encoded)
        if prefixed.startswith("/-"):
            return prefixed[2:]
        # Defensive: a leading "/-" can only disappear if dot-segment
        # removal collapsed everything back, which can't happen because
        # ``/-`` is not itself a dot segment. Fall back to the bare
        # encoded form rather than returning something incoherent.
        return encoded
    return _remove_dot_segments(encoded)


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 §5.2.4 ``remove_dot_segments`` — pure-Python implementation.

    Operates on a (possibly percent-encoded) path string. Treats ``.`` and
    ``..`` as syntactic dot-segments only when they appear as whole
    segments delimited by ``/``; literal ``..`` inside a longer segment
    (like ``foo..bar``) is left alone. Idempotent — applying twice yields
    the same result.

    We rewrite the *input buffer* one prefix at a time, appending to the
    *output buffer* when a non-dot segment is consumed. The five RFC
    branches are encoded as string-prefix checks in priority order; the
    final ``else`` branch moves one segment.
    """
    input_buf = path
    output_buf = ""

    while input_buf:
        if input_buf.startswith("../"):
            input_buf = input_buf[3:]
        elif input_buf.startswith("./"):
            input_buf = input_buf[2:]
        elif input_buf.startswith("/./"):
            input_buf = "/" + input_buf[3:]
        elif input_buf == "/.":
            input_buf = "/"
        elif input_buf.startswith("/../"):
            input_buf = "/" + input_buf[4:]
            slash_idx = output_buf.rfind("/")
            output_buf = output_buf[:slash_idx] if slash_idx >= 0 else ""
        elif input_buf == "/..":
            input_buf = "/"
            slash_idx = output_buf.rfind("/")
            output_buf = output_buf[:slash_idx] if slash_idx >= 0 else ""
        elif input_buf in (".", ".."):
            input_buf = ""
        else:
            # Move the next segment (a leading ``/`` then everything up
            # to the next ``/``, or the rest of input) from input to output.
            start = 1 if input_buf.startswith("/") else 0
            next_slash = input_buf.find("/", start)
            if next_slash == -1:
                output_buf += input_buf
                input_buf = ""
            else:
                output_buf += input_buf[:next_slash]
                input_buf = input_buf[next_slash:]

    return output_buf


# ------------------------------------------------------------------- search


def canonicalize_search(value: str) -> str:
    """Percent-encode using the WHATWG query encode set."""
    if not value:
        return value
    return _percent_encode(value, _QUERY_SET)


# --------------------------------------------------------------------- hash


def canonicalize_hash(value: str) -> str:
    """Percent-encode using the WHATWG fragment encode set."""
    if not value:
        return value
    return _percent_encode(value, _FRAGMENT_SET)
