# Explanation

How yarlpattern is built and why it's built that way.

- [**Architecture**](architecture.md) — module layout, the
  compile-time and match-time pipelines, the pluggable
  regex-engine `Protocol` seam (stdlib `re` is the default; opt
  into the `regex` package for full WPT conformance; a future
  PyO3-backed engine plugs in next to those), and the three
  places yarlpattern's implementation deliberately diverges from
  the simplest possible shape (`yarl.URL` fast path, `with_*`
  derivers, the WHATWG-strictness rules).
