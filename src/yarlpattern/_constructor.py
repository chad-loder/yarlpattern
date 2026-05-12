"""WHATWG URLPattern §1.6 — parse a constructor string into a URLPatternInit.

This is the FSM that breaks ``"https://example.com/:foo"`` into per-component
pattern strings before the §1.5 init-dict pipeline takes over. The algorithm
is an 11-state machine driven by the token list from §2.1.1 (run under the
``lenient`` policy so the ``:`` in ``https://host:port`` doesn't get rejected
as a malformed name token).

The shape of this FSM was inspired by the rust-urlpattern implementation,
which lays out the spec algorithm in a type-driven style that maps cleanly
onto Python. Variable names track the spec text directly so cross-
references in ``reference/spec/urlpattern.md`` stay legible.

Performance note: the algorithm runs *once per URLPattern construction*, so
we prioritize correctness/readability over micro-optimization. Instance
attributes use ``__slots__`` to keep the parser cheap to allocate; helpers
are kept as methods rather than free functions because most of them read
several pieces of state and the indirection cost is dominated by the regex
compile inside :meth:`_compute_protocol_matches_special_scheme`.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Final

from yarlpattern._canonicalize import SPECIAL_SCHEMES, canonicalize_protocol
from yarlpattern._parts import Options, parse_pattern_string
from yarlpattern._regex import parts_to_regex
from yarlpattern._tokenizer import Token, TokenizePolicy, TokenType, tokenize


class _State(IntEnum):
    """The 11 states from §1.6 "constructor string parser state".

    ``IntEnum`` because the states are compared frequently and only with
    each other — the integer identity is what matters, not the spec name.
    The ordering matches the spec listing for readability.
    """

    INIT = 0
    PROTOCOL = 1
    AUTHORITY = 2
    USERNAME = 3
    PASSWORD = 4
    HOSTNAME = 5
    PORT = 6
    PATHNAME = 7
    SEARCH = 8
    HASH = 9
    DONE = 10


# The protocol substring is compiled through the same parts → regex pipeline
# as the rest of URLPattern (so e.g. ``http{s}?`` correctly matches ``https``).
# We use the default Options bundle — protocol's spec options have no special
# delimiter / prefix code points.
_PROTOCOL_OPTS: Final = Options(delimiter_code_point="", prefix_code_point="")


# Token kinds that, when they appear immediately before a literal ``?``, mean
# the ``?`` is acting as a ``zero-or-one`` modifier rather than as a
# search-component prefix. This is the §1.6 "is a search prefix" subtle case:
# ``/foo:bar?`` is "/foo with optional :bar", not "/foo:bar plus an empty
# search". The Open kind (``{``) does *not* go here because ``{...}?`` parses
# as a group with no following modifier from the §1.6 perspective — the
# group's contents own the ``?`` resolution.
_MODIFIER_PRECEDING_KINDS: Final[frozenset[TokenType]] = frozenset(
    {
        TokenType.NAME,
        TokenType.REGEXP,
        TokenType.CLOSE,
        TokenType.ASTERISK,
    }
)


class _ConstructorStringParser:
    """Internal state for the §1.6 FSM."""

    __slots__ = (
        "component_start",
        "group_depth",
        "hostname_ipv6_bracket_depth",
        "input",
        "protocol_matches_special_scheme",
        "result",
        "state",
        "token_increment",
        "token_index",
        "token_list",
    )

    def __init__(self, input_: str, token_list: list[Token]) -> None:
        self.input: str = input_
        self.token_list: list[Token] = token_list
        self.result: dict[str, str] = {}
        self.component_start: int = 0
        self.token_index: int = 0
        self.token_increment: int = 1
        self.group_depth: int = 0
        self.hostname_ipv6_bracket_depth: int = 0
        self.protocol_matches_special_scheme: bool = False
        self.state: _State = _State.INIT

    # ------------------------------------------------------------------ helpers
    def _get_safe_token(self, index: int) -> Token:
        """§1.6 "get a safe token" — out-of-range returns the END sentinel."""
        if index < len(self.token_list):
            return self.token_list[index]
        # Tokenizer always emits a trailing END token, so the list is non-empty
        # and the last token is always END. Defensive assertion — a regression
        # in the tokenizer would surface here loudly.
        last = self.token_list[-1]
        assert last.kind is TokenType.END
        return last

    def _is_non_special_pattern_char(self, index: int, value: str) -> bool:
        """§1.6 "is a non-special pattern char".

        Char-kind tokens carry literal text; if the literal happens to be a
        URL-structural character (``:``, ``/``, ``@``, etc.) we treat it as
        that structural character. Escaped-char tokens also count because the
        tokenizer hands back ``"\\?"`` as an escaped-char with value ``"?"``,
        and the user explicitly chose to escape it — meaning the literal
        meaning, not the modifier meaning.
        """
        token = self._get_safe_token(index)
        if token.value != value:
            return False
        return token.kind in (
            TokenType.CHAR,
            TokenType.ESCAPED_CHAR,
            TokenType.INVALID_CHAR,
        )

    def _is_protocol_suffix(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, ":")

    def _is_password_prefix(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, ":")

    def _is_port_prefix(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, ":")

    def _is_pathname_start(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, "/")

    def _is_identity_terminator(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, "@")

    def _is_hash_prefix(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, "#")

    def _is_ipv6_open(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, "[")

    def _is_ipv6_close(self) -> bool:
        return self._is_non_special_pattern_char(self.token_index, "]")

    def _is_search_prefix(self) -> bool:
        """§1.6 "is a search prefix" — distinguishes ``?`` query from modifier.

        The non-special-pattern-char form covers escaped ``\\?`` and char
        ``?`` immediately. The trickier case is a bare ``?`` token (kind
        ``other-modifier`` in the tokenizer's worldview): we need to peek
        the previous token to see whether it's something that *could* take
        a modifier. If not, the ``?`` is a search prefix even though the
        tokenizer classified it as a modifier.
        """
        if self._is_non_special_pattern_char(self.token_index, "?"):
            return True
        if self.token_list[self.token_index].value != "?":
            return False
        if self.token_index == 0:
            return True
        previous_token = self._get_safe_token(self.token_index - 1)
        return previous_token.kind not in _MODIFIER_PRECEDING_KINDS

    def _is_group_open(self) -> bool:
        return self.token_list[self.token_index].kind is TokenType.OPEN

    def _is_group_close(self) -> bool:
        return self.token_list[self.token_index].kind is TokenType.CLOSE

    def _next_is_authority_slashes(self) -> bool:
        if not self._is_non_special_pattern_char(self.token_index + 1, "/"):
            return False
        return self._is_non_special_pattern_char(self.token_index + 2, "/")

    # ---------------------------------------------------------- state helpers
    def _make_component_string(self) -> str:
        """§1.6 "make a component string" — slice the original input.

        ``component_start`` and ``token_index`` are *token* indices; we map
        them to *input* offsets via the tokens' ``.index`` field (the offset
        of the first code point of that token in the original string). The
        slice is therefore safe even though pattern syntax (``{``, ``(``,
        ``:``) is not preserved in the tokens themselves — the offsets point
        into the raw input, which still has it.
        """
        assert self.token_index < len(self.token_list)
        end_token = self.token_list[self.token_index]
        start_token = self._get_safe_token(self.component_start)
        return self.input[start_token.index : end_token.index]

    def _change_state(self, new_state: _State, skip: int) -> None:
        """§1.6 "change state" — commit the current component and advance.

        Beyond the obvious "stash the substring under the right key", this
        method handles a pile of subtle defaults:

        * Skipping the authority entirely (going Protocol → Pathname when the
          input is ``mailto:user@example.com``) means there's no Hostname
          state to set ``hostname = ""``; we fill that in here.
        * Likewise for special-scheme inputs that go straight to Search /
          Hash without ever entering Pathname — we synthesize the default
          pathname (``"/"`` for special, ``""`` for opaque) so the result
          matches a fully-parsed URL.
        * Hash with no preceding Search gets ``search = ""``.
        """
        # 1) Commit the substring under the current state's key.
        committed = self.state
        if committed is _State.PROTOCOL:
            self.result["protocol"] = self._make_component_string()
        elif committed is _State.USERNAME:
            self.result["username"] = self._make_component_string()
        elif committed is _State.PASSWORD:
            self.result["password"] = self._make_component_string()
        elif committed is _State.HOSTNAME:
            self.result["hostname"] = self._make_component_string()
        elif committed is _State.PORT:
            self.result["port"] = self._make_component_string()
        elif committed is _State.PATHNAME:
            self.result["pathname"] = self._make_component_string()
        elif committed is _State.SEARCH:
            self.result["search"] = self._make_component_string()
        elif committed is _State.HASH:
            self.result["hash"] = self._make_component_string()
        # INIT / AUTHORITY / DONE: nothing to commit.

        # 2) Default-fill skipped components.
        if committed is not _State.INIT and new_state is not _State.DONE:
            # Skipped hostname: any pre-host state transitioning to a
            # post-host state without setting hostname leaves it empty.
            if (
                committed
                in (
                    _State.PROTOCOL,
                    _State.AUTHORITY,
                    _State.USERNAME,
                    _State.PASSWORD,
                )
                and new_state
                in (
                    _State.PORT,
                    _State.PATHNAME,
                    _State.SEARCH,
                    _State.HASH,
                )
                and "hostname" not in self.result
            ):
                self.result["hostname"] = ""

            # Skipped pathname: jumping past pathname into search / hash.
            # Special schemes get ``"/"`` as the default path; opaque
            # schemes (mailto, data, etc.) get the empty string.
            if (
                committed
                in (
                    _State.PROTOCOL,
                    _State.AUTHORITY,
                    _State.USERNAME,
                    _State.PASSWORD,
                    _State.HOSTNAME,
                    _State.PORT,
                )
                and new_state in (_State.SEARCH, _State.HASH)
                and "pathname" not in self.result
            ):
                self.result["pathname"] = "/" if self.protocol_matches_special_scheme else ""

            # Skipped search: jumping into hash without a search component
            # implies an empty search.
            if (
                committed
                in (
                    _State.PROTOCOL,
                    _State.AUTHORITY,
                    _State.USERNAME,
                    _State.PASSWORD,
                    _State.HOSTNAME,
                    _State.PORT,
                    _State.PATHNAME,
                )
                and new_state is _State.HASH
                and "search" not in self.result
            ):
                self.result["search"] = ""

        # 3) Advance.
        self.state = new_state
        self.token_index += skip
        self.component_start = self.token_index
        self.token_increment = 0

    def _rewind(self) -> None:
        """§1.6 "rewind" — restart the current component at the saved start."""
        self.token_index = self.component_start
        self.token_increment = 0

    def _rewind_and_set_state(self, state: _State) -> None:
        self._rewind()
        self.state = state

    def _compute_protocol_matches_special_scheme(self) -> None:
        """§1.6 "compute protocol matches a special scheme flag".

        Compiles the *current* protocol substring through the full part-list
        → regex pipeline (with the same canonicalization callback used at
        URLPattern construction) and tests it against each of the WHATWG
        special schemes. If any match, the flag is set — which then drives
        Protocol → Authority/Pathname routing and pathname defaults below.

        This is the only point in the parser that calls into the rest of
        URLPattern; it has to, because deciding whether ``https`` or
        ``ftp`` is "special" is part of the spec algorithm itself.
        """
        protocol_string = self._make_component_string()
        try:
            parts = parse_pattern_string(
                protocol_string,
                _PROTOCOL_OPTS,
                canonicalize_protocol,
            )
            regex_src, _name_list = parts_to_regex(parts, _PROTOCOL_OPTS)
            regex = re.compile(regex_src, re.ASCII)
        except (re.error, TypeError, ValueError):
            # An invalid protocol pattern will fail again — and louder —
            # when the per-component compile reaches it. Here we just stay
            # conservative and treat the protocol as non-special.
            return
        for scheme in SPECIAL_SCHEMES:
            if regex.fullmatch(scheme) is not None:
                self.protocol_matches_special_scheme = True
                return


def parse_constructor_string(input_: str) -> dict[str, str]:
    """Implement §1.6 "parse a constructor string".

    Returns a partially populated init dict (``protocol``, ``hostname``,
    etc.) suitable for handing to the dict-form URLPattern constructor.
    Keys are present iff that component appeared (or was synthesized as a
    default) in *input_*.

    The FSM runs in lenient tokenize mode so URL separators don't trip the
    strict-mode validation. The strict tokenizer is reserved for compiling
    the resulting per-component pattern strings, where pattern syntax
    *is* the entire language.
    """
    token_list = tokenize(input_, TokenizePolicy.LENIENT)
    parser = _ConstructorStringParser(input_, token_list)

    while parser.token_index < len(parser.token_list):
        parser.token_increment = 1

        # End-of-input handling. Three branches:
        # * Still in INIT — the entire input is a path / search / hash with
        #   no protocol prefix. Rewind and re-process under the appropriate
        #   single-component state.
        # * In AUTHORITY — the authority never resolved into username /
        #   password / hostname (e.g. just ``//`` with nothing after it).
        #   Rewind into Hostname and let the loop handle it.
        # * Anywhere else — commit and stop.
        if parser.token_list[parser.token_index].kind is TokenType.END:
            if parser.state is _State.INIT:
                parser._rewind()
                if parser._is_hash_prefix():
                    parser._change_state(_State.HASH, 1)
                elif parser._is_search_prefix():
                    parser._change_state(_State.SEARCH, 1)
                else:
                    parser._change_state(_State.PATHNAME, 0)
                parser.token_index += parser.token_increment
                continue
            if parser.state is _State.AUTHORITY:
                parser._rewind_and_set_state(_State.HOSTNAME)
                parser.token_index += parser.token_increment
                continue
            parser._change_state(_State.DONE, 0)
            break

        # Pattern-group tracking. Inside a ``{ ... }`` or ``( ... )`` group
        # the FSM ignores URL-structural characters — a ``:`` inside a
        # group is part of the pattern syntax, not a port prefix.
        if parser._is_group_open():
            parser.group_depth += 1
            parser.token_index += parser.token_increment
            continue
        if parser.group_depth > 0:
            if parser._is_group_close():
                parser.group_depth -= 1
            else:
                parser.token_index += parser.token_increment
                continue

        # Per-state dispatch. Each branch mirrors §1.6's state table.
        state = parser.state
        if state is _State.INIT:
            if parser._is_protocol_suffix():
                parser._rewind_and_set_state(_State.PROTOCOL)
        elif state is _State.PROTOCOL:
            if parser._is_protocol_suffix():
                parser._compute_protocol_matches_special_scheme()
                # Default next state is Pathname (opaque URL like ``data:..``)
                # unless we see ``//`` (authority) or the protocol turned
                # out to be a special scheme (implicit authority).
                next_state = _State.PATHNAME
                skip = 1
                if parser._next_is_authority_slashes():
                    next_state = _State.AUTHORITY
                    skip = 3
                elif parser.protocol_matches_special_scheme:
                    next_state = _State.AUTHORITY
                parser._change_state(next_state, skip)
        elif state is _State.AUTHORITY:
            if parser._is_identity_terminator():
                # Saw ``@`` — the leading portion was username[:password].
                parser._rewind_and_set_state(_State.USERNAME)
            elif parser._is_pathname_start() or parser._is_search_prefix() or parser._is_hash_prefix():
                # No ``@`` materialized; the authority was just a hostname.
                parser._rewind_and_set_state(_State.HOSTNAME)
        elif state is _State.USERNAME:
            if parser._is_password_prefix():
                parser._change_state(_State.PASSWORD, 1)
            elif parser._is_identity_terminator():
                parser._change_state(_State.HOSTNAME, 1)
        elif state is _State.PASSWORD:
            if parser._is_identity_terminator():
                parser._change_state(_State.HOSTNAME, 1)
        elif state is _State.HOSTNAME:
            # IPv6 literals like ``[::1]`` contain ``:`` characters that
            # would otherwise be misread as a port prefix. Track bracket
            # depth and only honor the port prefix outside brackets.
            if parser._is_ipv6_open():
                parser.hostname_ipv6_bracket_depth += 1
            elif parser._is_ipv6_close():
                parser.hostname_ipv6_bracket_depth -= 1
            elif parser._is_port_prefix() and parser.hostname_ipv6_bracket_depth == 0:
                parser._change_state(_State.PORT, 1)
            elif parser._is_pathname_start():
                parser._change_state(_State.PATHNAME, 0)
            elif parser._is_search_prefix():
                parser._change_state(_State.SEARCH, 1)
            elif parser._is_hash_prefix():
                parser._change_state(_State.HASH, 1)
        elif state is _State.PORT:
            if parser._is_pathname_start():
                parser._change_state(_State.PATHNAME, 0)
            elif parser._is_search_prefix():
                parser._change_state(_State.SEARCH, 1)
            elif parser._is_hash_prefix():
                parser._change_state(_State.HASH, 1)
        elif state is _State.PATHNAME:
            if parser._is_search_prefix():
                parser._change_state(_State.SEARCH, 1)
            elif parser._is_hash_prefix():
                parser._change_state(_State.HASH, 1)
        elif state is _State.SEARCH:
            if parser._is_hash_prefix():
                parser._change_state(_State.HASH, 1)
        elif state is _State.HASH:
            pass
        # _State.DONE is unreachable inside the loop — _change_state(DONE)
        # is followed by a break.

        parser.token_index += parser.token_increment

    # §1.6 trailing fixup: if a hostname appeared but no port did, set
    # port to the empty string so dict-form processing knows to override
    # any base-URL inherited port (rather than letting baseURL's port leak
    # through into the pattern).
    if "hostname" in parser.result and "port" not in parser.result:
        parser.result["port"] = ""

    return parser.result
