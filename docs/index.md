# yarlpattern

**WHATWG URLPattern for Python.** 100% specification-strict, pure Python,
optimized and yarl-compatible.

```python
from yarlpattern import URLPattern

pat = URLPattern("https://api.example.com/users/:id(\\d+)")
pat.test("https://api.example.com/users/42")  # True
pat.exec("https://api.example.com/users/42").pathname.groups  # {'id': '42'}
```

This site is a work in progress. For the moment, the
[project README](https://github.com/chad-loder/yarlpattern#readme) is the most
complete reference: installation, the engine-pluggability story, the WHATWG
conformance matrix, and the comparisons with other Python routers.

The [WPT conformance report](wpt-compliance.md) is the canonical evidence —
auto-regenerated against the upstream WPT corpus.
