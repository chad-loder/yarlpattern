# Avoid regex hostname-allowlist credential leaks

A common pattern: keep a list of "trusted" hosts and attach a credential
(API token, cookie, signed header) when a request URL matches one of them.
The obvious implementation — pick a regex per trusted host — has a security
pitfall that's easy to miss in code review and even easier to exploit.

## The vulnerability

The seed case is
[`invoke-ai/InvokeAI#7518`](https://github.com/invoke-ai/InvokeAI/issues/7518):
a configuration field where users register one regex per trusted upstream,
each paired with the credential the client should send when the URL matches.

```yaml
remote_api_tokens:
  - url_regex: 'private.example'
    token: 'secret'
```

The author's intent reads cleanly: *"when the request URL is for `private.example`,
attach `secret`."* But Python's `re.search` looks for a substring match anywhere
in the URL string, and a regex source is not a hostname — it's a flat character
sequence with a different grammar. Two URL shapes that an attacker controls also
match this regex:

1. **Path-segment fallthrough.** A `re.search` on the URL string finds
   `private.example` inside `https://malicious.example/private.example/theft.safetensors`.
   The path contains the literal regex text, so the regex matches, the
   credential is attached to the outbound request, and the secret lands on the
   attacker's server.
2. **Subdomain shadowing.** The same regex matches
   `https://private.example.malicious.example/theft.safetensors`. The attacker
   simply registers a subdomain whose label is the legitimate host's name; the
   regex sees `private.example` as a substring and attaches the credential.

It is *possible* to write a regex that resists both — something like
`^https://([^[@/:]+\.)?private\.example/` — but the difference between the
naive version and the correct one is not visually obvious, and there's no
compiler warning when a user gets it wrong. Every shipped configuration
becomes a separate audit problem.

## With URLPattern

URLPattern matches on parsed URL *components*, not flat strings. A pattern
constrained on the `hostname` component is structurally incapable of matching
a path segment that happens to spell the same text, and a `hostname` literal
matches the whole component — not a substring within it.

```python
from yarlpattern import URLPattern

TRUSTED = URLPattern({
    "protocol": "https",
    "hostname": "private.example",
})

# Intended traffic
TRUSTED.test("https://private.example/models/sd-xl.safetensors")          # True

# The two attacks from above
TRUSTED.test("https://malicious.example/private.example/theft.safetensors")    # False
TRUSTED.test("https://private.example.malicious.example/theft.safetensors")    # False

# Cleartext is rejected at the pattern level
TRUSTED.test("http://private.example/models/sd-xl.safetensors")           # False
```

The first negative case fails because `private.example` (a path segment) is
not the *hostname* — URLPattern parsed the URL first, then asked "does the
hostname literal match?" The second fails because `private.example.malicious.example`
is the full hostname, and `private.example` (the pattern) does not equal it.
The third fails because `protocol: "https"` is in the pattern; there is no
separate "and also require HTTPS" check to forget elsewhere.

## Allowing legitimate subdomains

If the desired policy is *"`private.example` itself or any of its subdomains,"*
spell that as a component-aware pattern — not a regex tweak:

```python
TRUSTED = URLPattern({
    "protocol": "https",
    "hostname": "{:subdomain.}*private.example",
})

TRUSTED.test("https://private.example/models/sd-xl.safetensors")        # True
TRUSTED.test("https://eu.private.example/models/sd-xl.safetensors")     # True

# Still rejected — the attacker cannot prepend the legit host as a label
TRUSTED.test("https://private.example.malicious.example/theft.safetensors")   # False
```

The `{:subdomain.}*` part matches zero or more dot-separated labels *before*
the suffix `private.example`. It is parsed against the hostname component,
so a host like `private.example.malicious.example` — whose final label is
`malicious` — cannot satisfy the suffix constraint.

## Multi-host allowlist

A list of trusted hosts is one URLPattern per host, kept next to the credential.
The pattern table is a security-review artifact: a reviewer can read the
allowlist directly without auditing imperative control flow.

```python
TRUSTED_UPSTREAMS = [
    (URLPattern({"protocol": "https", "hostname": "private.example"}),
     "secret-private-example"),
    (URLPattern({"protocol": "https", "hostname": "{:subdomain.}*models.acme.example"}),
     "secret-acme-models"),
    (URLPattern({"protocol": "https", "hostname": "huggingface.co"}),
     "secret-hf"),
]

def credential_for(url: str) -> str | None:
    for pattern, token in TRUSTED_UPSTREAMS:
        if pattern.test(url):
            return token
    return None
```

If `credential_for` returns `None`, the client sends the request unauthenticated.
There is no way for an attacker-controlled URL to "almost match" a trusted entry.

## What you get for free

- **Component-aware matching by construction.** A hostname pattern matches
  the hostname; a pathname pattern matches the pathname. The grammar of the
  matcher mirrors the structure of the URL, so substring-fallthrough attacks
  cannot reach the wrong field.
- **WHATWG URL parsing under the hood.** Inputs are parsed via
  [`yarl`](https://github.com/aio-libs/yarl) — the same WHATWG-flavoured rules
  browsers apply — *before* the pattern is asked anything. Userinfo, ports,
  trailing dots, and IDN labels are normalised the way an attacker's
  ambiguity tricks expect them to *not* be.
- **No manual scheme check.** `protocol: "https"` lives in the pattern;
  cleartext HTTP cannot match. One fewer thing to forget in the call site.
- **Auditable allowlist.** The list of trusted-host patterns is the
  allowlist. Reviewers don't have to trace imperative control flow.

## Further reading

- The seed issue:
  [`invoke-ai/InvokeAI#7518` — "remote_api_tokens should use URL Patterns instead of regular expressions"](https://github.com/invoke-ai/InvokeAI/issues/7518)
- The class of bug: substring-vs-component confusion in URL-allowlist regexes
  has produced public CVEs in routing and reverse-proxy code repeatedly;
  searching CVE databases for "ReDoS" or "host header bypass via regex" turns
  up real examples in projects far larger than InvokeAI.
- Background on why the URLPattern spec exists in the first place — service
  workers needed component-aware scope matching for exactly this reason:
  see [**Overview → What is URLPattern?**](../overview/what-is-urlpattern.md).
