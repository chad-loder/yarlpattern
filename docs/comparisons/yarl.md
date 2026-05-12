# yarlpattern vs. yarl

[yarl](https://github.com/aio-libs/yarl) is a URL parser / builder; yarlpattern is a URLPattern
matcher. They're complementary — yarlpattern depends on yarl for actual URL parsing and IDNA
hostname encoding, and the API is shaped to feel familiar to yarl users.

There are a few places where yarlpattern is *stricter* than yarl, all because the WHATWG
URLPattern spec requires it. The relevant rules:

## 1. Case-preserving `%XX` passthrough

|  | Behavior |
|---|---|
| yarl | Normalizes percent-encoded sequences to uppercase: `caf%c3%a9` → `caf%C3%A9` |
| yarlpattern | Preserves the user's case verbatim: `caf%c3%a9` stays `caf%c3%a9` |

The WHATWG URLPattern spec pins this down in the test suite — WPT cases 146 and 148 contrast
exactly on whether `caf%C3%A9` and `caf%c3%a9` round-trip as themselves. Pattern *equality*
depends on case being preserved; if yarlpattern lowercased to match yarl's convention, patterns
constructed from URL strings with mixed case would silently change meaning.

## 2. Unpaired surrogates → U+FFFD before UTF-8 encoding

|  | Behavior |
|---|---|
| yarl | Silently drops invalid sequences (`errors="ignore"`) |
| yarlpattern | Replaces with U+FFFD REPLACEMENT CHARACTER per WHATWG |

The [WHATWG URL standard §1.3](https://url.spec.whatwg.org/#percent-encoded-bytes) says
"to UTF-8 percent-encode a code point C using a percent-encode set, return the result of
running UTF-8 encode on C". UTF-8 encode requires a Unicode *scalar value*, and surrogate
halves (`D800–DFFF`) aren't scalar values — so the spec implicitly mandates U+FFFD
substitution. WPT case 157 (`{pathname: '\ud83d \udeb2'}` → `%EF%BF%BD%20%EF%BF%BD`)
locks this in.

## 3. Hostname truncation at `?` / `#` / `/` / `\`

|  | Behavior |
|---|---|
| yarl | Rejects those characters in a host string outright |
| yarlpattern | Truncates at the first one, matching Chromium |

This follows [Chromium's `CanonicalizeHostnameInternal`](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/url_pattern/url_pattern_dummy_url_canon.cc),
which strips at the first `?`, `/`, `#` and treats `\` as `/` for special schemes (the
WHATWG URL "special authority" rule). The rationale is forgiveness: a hostname pattern
containing `/` was almost certainly a paste of a full URL, and respecting the prefix is
more useful than rejecting. WPT covers this with patterns like `{hostname: 'bad#hostname'}`
expecting compiled hostname `'bad'`.

## Where yarlpattern agrees with yarl (and the rest of the aio-libs family)

The encoding philosophy is the same: **strict UTF-8, no BOM handling, no autodetection,
Python `str` at the public boundary.**

- The WHATWG URL spec mandates UTF-8 for all newly percent-encoded bytes — no encoding
  alias machinery (the kind `webencodings` provides for HTML body parsing) applies. URLs
  are sequences of Unicode code points, not encoded bytes.
- A U+FEFF BOM in a URL string is just a regular non-ASCII code point; yarlpattern
  percent-encodes it as `%EF%BB%BF` exactly like yarl would. No "strip-the-BOM-at-the-start"
  logic exists in either library because URL parsing doesn't need it.
- aiohttp follows the same "be strict, plug in autodetection if you need it" pattern for
  HTTP body charsets via its `fallback_charset_resolver` hook. URL parsing has no analog
  because no autodetection is needed — UTF-8 is unconditional.

## Component-name mapping (yarl ↔ WHATWG)

Five of eight URL component names differ between yarl and the WHATWG URLPattern spec. The
names yarlpattern uses match the spec (and the JS `URL` interface in browsers); knowing both
makes the muscle-memory transition shorter.

| yarl | yarlpattern | WHATWG / browser JS |
|---|---|---|
| `scheme` | `protocol` | `protocol` |
| `user` | `username` | `username` |
| `password` | `password` | `password` |
| `host` | `hostname` | `hostname` |
| `port` | `port` | `port` |
| `path` | `pathname` | `pathname` |
| `query` (a MultiDict) | `search` (a str) | `search` |
| `fragment` | `hash` | `hash` |

## yarl-style ergonomics

Two affordances specifically for yarl-shaped code:

**`yarl.URL` accepted as input — fast path.** `.test()` and `.exec()` accept a `yarl.URL` in
both the `input` and `base_url` positions. The matcher reads components directly off the
already-parsed URL object instead of re-stringing and re-parsing, so the typical
"`pat.test(request.url)`" call in an aiohttp handler is the fast path:

```python
pat = URLPattern("https://api.example.com/users/:id")
pat.test(request.url)                    # yarl.URL passed directly — no str() needed
pat.exec(yarl.URL("https://..."))        # parsed components consumed in place
```

**Per-component `with_*` methods.** Alongside the spec-shaped `with_(**kwargs)` deriver,
yarlpattern exposes one `with_<component>` method per URL component — same yarl convention,
WHATWG names:

```python
base = URLPattern({"hostname": "example.com"})
base.with_hostname("api.example.com")    # equivalent to base.with_(hostname="...")
base.with_pathname("/v2/:id")            # → URLPattern({hostname=example.com, pathname=/v2/:id})
```

Both methods exist; `with_(**kwargs)` is preferred when changing multiple components at once,
`with_<component>` when changing exactly one (and matches yarl's habit).
