# Security policy

## Reporting a vulnerability

We prefer **transparency**: if you find a security problem in `yarlpattern`, you are
welcome to open a **pull request** (or a public **issue** if a PR is not
practical) so the fix and any discussion can happen in the open.

If you need **private coordination** first—for example, you believe disclosure
should wait until a patch is ready—use GitHub’s security advisory flow:

**<https://github.com/chad-loder/yarlpattern/security/advisories/new>**

In either case, we aim to acknowledge reports within 72 hours.

## Supported versions

`yarlpattern` is pre-1.0, so only the latest published minor version is
actively maintained. Once a stable 1.x line ships, this policy will be
updated to cover at least the current and previous minor releases.

## Scope

In scope:

- Regular-expression denial-of-service (ReDoS) from a benign-looking
  pattern that compiles to a catastrophic-backtracking regex.
- Spec deviations that could let an attacker bypass a routing check —
  e.g. a URL that should not match a pattern but does, or vice versa,
  when the application uses ``URLPattern`` for authorization decisions.
- Memory exhaustion from inputs accepted by the constructor.

Out of scope:

- Issues in dependencies (report to ``yarl`` or ``regex`` directly).
- ReDoS that requires the application to compile patterns supplied by
  an untrusted user. Treat user-supplied patterns the same way you
  would treat user-supplied regular expressions: don't.
- Self-DoS from passing absurd inputs to the API.
