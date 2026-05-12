# Validate inbound webhooks by URL shape

Webhook handlers from Stripe, GitHub, Slack, Twilio, and friends arrive
at *your* URL — and the URL they hit has a known, documented shape.
A small amount of defensive URL-shape validation in the handler
(before signature verification) catches misconfigured senders, scanners,
and accidentally-internet-facing dev endpoints.

## The awkward way

```python
from urllib.parse import urlparse

def is_valid_stripe_webhook(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.hostname != "hooks.acme.example":
        return False
    parts = parsed.path.split("/")
    if len(parts) != 4 or parts[1] != "stripe":
        return False
    if not parts[2].startswith("v"):
        return False
    if not parts[2][1:].isdigit():
        return False
    if parts[3] != "events":
        return False
    return True
```

Seven branches, each with its own way of failing silently. The first
time a new shape gets added (`/stripe/v2/events`, `/stripe/v1/refunds`),
you find another branch to add.

## With URLPattern

```python
from yarlpattern import URLPattern

STRIPE_WEBHOOK = URLPattern({
    "protocol": "https",
    "hostname": "hooks.acme.example",
    "pathname": "/stripe/v:version(\\d+)/events",
})

STRIPE_WEBHOOK.test("https://hooks.acme.example/stripe/v1/events")          # True
STRIPE_WEBHOOK.test("https://hooks.acme.example/stripe/v1/events/extra")    # False
STRIPE_WEBHOOK.test("http://hooks.acme.example/stripe/v1/events")           # False — plain http
STRIPE_WEBHOOK.test("https://hooks.acme.example/stripe/vbeta/events")       # False — non-digit version
```

The pattern *is* the shape contract. If the URL doesn't match exactly,
`.test()` returns `False` and the handler can 404 (or 422) before doing
any payload work. The integer-only version constraint
(`v:version(\\d+)`) is in the pattern, not in your handler.

## Adding `/stripe/v1/refunds` later

Add a second pattern, then dispatch:

```python
WEBHOOKS = [
    (URLPattern({"protocol": "https", "hostname": "hooks.acme.example",
                 "pathname": "/stripe/v:version(\\d+)/events"}),    handle_stripe_events),
    (URLPattern({"protocol": "https", "hostname": "hooks.acme.example",
                 "pathname": "/stripe/v:version(\\d+)/refunds"}),   handle_stripe_refunds),
    (URLPattern({"protocol": "https", "hostname": "hooks.acme.example",
                 "pathname": "/github/:org/push"}),                 handle_github_push),
]

def dispatch_webhook(url):
    for pattern, handler in WEBHOOKS:
        result = pattern.exec(url)
        if result is not None:
            return handler(result)
    return reject_unknown_webhook()
```

Each new webhook source is one URLPattern entry. Reading the table
tells you exactly which URL shapes your service accepts — a security
review artifact for free.

## What you get for free

- **`.test()` is a one-call validator.** No multi-branch helper to
  audit; the pattern is the audit surface.
- **Per-group regex constraints.** `v:version(\\d+)` rejects junk
  values before they reach the handler.
- **Scheme constraint in the pattern.** `protocol: "https"` rejects
  cleartext-HTTP attempts at the pattern level — no separate
  `if request.scheme != "https"` check.
- **Pattern table = security review artifact.** Reviewers can audit
  the URL-shape contract by reading the URLPattern list directly,
  without tracing imperative control flow.
