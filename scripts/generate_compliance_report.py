#!/usr/bin/env python3
"""Generate ``docs/wpt-compliance.md`` — the full WPT conformance matrix.

Standalone script (not packaged in the wheel). Runs every WHATWG
``web-platform-tests/wpt/urlpattern/`` case against :class:`URLPattern`,
captures the outcome of each, and emits a structured Markdown report
with shields.io badges + accessible Unicode-symbol status indicators.

The script reproduces the harness logic from ``tests/test_wpt.py`` and
the auxiliary test files inline — running it does not require pytest.
``just compliance-report`` is the canonical invocation.

The output is meant for human reading on GitHub: collapsible
``<details>`` blocks per suite, summary table at the top, per-case
rows with pattern previews and pass/fail symbols. Colors come from
shields.io (high-contrast green/red/blue/grey palette that's
distinguishable for the common color-vision-deficiency types) and
never carry meaning alone — every status is paired with a symbol and
a word.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from yarlpattern import COMPONENTS, URLPattern  # noqa: E402
from yarlpattern._regex_engine import get_default_engine  # noqa: E402

WPT_ROOT = REPO / "reference" / "wpt"
WPT_DIR = WPT_ROOT / "urlpattern" / "resources"
OUTPUT = REPO / "docs" / "wpt-compliance.md"


def _wpt_ref() -> str:
    """Pinned WPT commit SHA driving this report.

    Read from the corpus checkout's ``HEAD`` so the report is always
    consistent with the bytes that were actually tested — a stale
    constant in this script can never disagree with the on-disk corpus.
    """
    try:
        # S603/S607: argv is hardcoded; ``git`` is taken from PATH because
        # cross-OS absolute paths differ. Trusted-input invocation.
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(WPT_ROOT), "rev-parse", "HEAD"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "main"  # best-effort fallback for a non-git corpus


# -------------------------- symbols + shields.io palette ---------------------
#
# Accessibility rule (matches the README): the symbol carries the meaning;
# color is decorative. Every cell pairs a Unicode glyph with a status word
# and (in summary tables) a shields.io badge whose alt text restates the
# result.

SYM_PASS = "✓"
SYM_FAIL = "✗"
SYM_XFAIL = "◐"
SYM_SKIP = "◑"
SYM_ERROR = "⚠"

# Wong-style colorblind-safe palette (paired with shape + text)
COLOR_PASS = "2ea043"  # GitHub success-green
COLOR_FAIL = "cf222e"  # GitHub danger-red
COLOR_XFAIL = "1f6feb"  # informational blue
COLOR_SKIP = "6e7681"  # muted grey
COLOR_ERROR = "bf8700"  # attention yellow


# -------------------------- result data classes -----------------------------


@dataclass(slots=True)
class CaseResult:
    """Outcome of a single WPT case."""

    index: int
    name: str
    status: str  # "pass" | "fail" | "xfail" | "skip" | "error"
    detail: str = ""  # short failure / xfail / error reason


@dataclass(slots=True)
class SuiteResult:
    """All outcomes for one WPT suite.

    The suite is identified by its **upstream WPT runner filename**
    (e.g. ``urlpattern.any.js``) — the name a WHATWG / WPT contributor
    will recognize. ``data_file`` is the optional fixture the runner
    consumes (``None`` for runners that inline their cases).
    """

    title: str
    runner_path: str  # path within `urlpattern/` (e.g. "urlpattern.any.js")
    data_path: str | None = None  # path within `urlpattern/` to the data file
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passing(self) -> int:
        return sum(1 for c in self.cases if c.status == "pass")

    @property
    def xfailing(self) -> int:
        return sum(1 for c in self.cases if c.status == "xfail")

    @property
    def skipping(self) -> int:
        return sum(1 for c in self.cases if c.status == "skip")

    @property
    def failing(self) -> int:
        return sum(1 for c in self.cases if c.status == "fail")

    @property
    def erroring(self) -> int:
        return sum(1 for c in self.cases if c.status == "error")

    @property
    def is_clean(self) -> bool:
        """True iff every case is pass / xfail / skip — no real failures."""
        return self.failing == 0 and self.erroring == 0


# -------------------------- harness for the data corpus ---------------------
#
# Mirrors ``tests/test_wpt.py``. Kept inline (not imported) so the script
# stays independent of the pytest test-collection machinery.

_EARLIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "protocol": (),
    "hostname": ("protocol",),
    "port": ("protocol", "hostname"),
    "username": (),
    "password": (),
    "pathname": ("protocol", "hostname", "port"),
    "search": ("protocol", "hostname", "port", "pathname"),
    "hash": ("protocol", "hostname", "port", "pathname", "search"),
}

_SET_OP_CASES = frozenset(
    {
        "350-pathname='/([[a-z]--a])'",
        "351-pathname='/([\\d&&[0-1]])'",
    },
)


def _expected_component_pattern(entry: dict[str, Any], component: str) -> str:
    expected_obj = entry.get("expected_obj") or {}
    if component in expected_obj:
        return expected_obj[component]
    if component in (entry.get("exactly_empty_components") or []):
        return ""
    pattern_args = entry.get("pattern", [])
    first = pattern_args[0] if pattern_args else None
    if isinstance(first, dict) and first.get(component):
        return first[component]
    if isinstance(first, dict) and any(c in first for c in _EARLIER_COMPONENTS[component]):
        return "*"
    base_url: str | None = None
    if isinstance(first, dict) and first.get("baseURL"):
        base_url = first["baseURL"]
    elif len(pattern_args) > 1 and isinstance(pattern_args[1], str):
        base_url = pattern_args[1]
    if base_url and component not in ("username", "password"):
        parts = urlsplit(base_url)
        if component == "protocol":
            return parts.scheme
        if component == "hostname":
            return parts.hostname or ""
        if component == "port":
            return str(parts.port) if parts.port is not None else ""
        if component == "pathname":
            return parts.path
        if component == "search":
            return parts.query
        if component == "hash":
            return parts.fragment
    return "*"


def _auto_populate_expected_component(entry: dict[str, Any], component: str) -> dict[str, Any]:
    expected_match = entry.get("expected_match") or {}
    existing = expected_match.get(component)
    if existing is not None:
        return existing
    if component in (entry.get("exactly_empty_components") or []):
        return {"input": "", "groups": {}}
    return {"input": "", "groups": {"0": ""}}


def _normalize_expected_groups(groups: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in groups.items() if v is not None}


def _run_data_corpus_case(idx: int, entry: dict[str, Any]) -> CaseResult:
    """Run one ``urlpatterntestdata.json`` entry against the matcher.

    Returns a :class:`CaseResult` reflecting whether the spec's expected
    behavior was observed. Cases that depend on the regex engine's
    set-op support are tagged ``xfail`` when the stdlib engine is in
    use (matching the pytest xfail logic).
    """
    case_id = _case_id_for(idx, entry)
    # Engine-gap xfail check (mirrors test_wpt.py).
    is_set_op = case_id in _SET_OP_CASES or case_id.replace("\\\\", "\\") in _SET_OP_CASES
    engine = get_default_engine()
    if is_set_op and not engine.supports_set_operations:
        return CaseResult(idx, case_id, "xfail", "engine lacks v-flag set ops")

    try:
        if entry.get("expected_obj") == "error":
            try:
                URLPattern(*entry["pattern"])
            except TypeError:
                return CaseResult(idx, case_id, "pass")
            return CaseResult(idx, case_id, "fail", "expected TypeError on construction")
        pat = URLPattern(*entry["pattern"])
        # Compiled component pattern strings.
        for component in COMPONENTS:
            expected = _expected_component_pattern(entry, component)
            actual = getattr(pat, component)
            if actual != expected:
                return CaseResult(
                    idx,
                    case_id,
                    "fail",
                    f"compiled .{component}: expected {expected!r}, got {actual!r}",
                )
        # Match phase.
        if entry.get("expected_match") == "error":
            for fn in (pat.test, pat.exec):
                try:
                    fn(*entry["inputs"])
                except TypeError:
                    continue
                return CaseResult(idx, case_id, "fail", f"{fn.__name__}: expected TypeError")
            return CaseResult(idx, case_id, "pass")
        expected_match = entry.get("expected_match")
        expected_truthy = expected_match is not None and expected_match is not False
        if pat.test(*entry["inputs"]) is not expected_truthy:
            return CaseResult(idx, case_id, "fail", f"test() != {expected_truthy}")
        exec_result = pat.exec(*entry["inputs"])
        if expected_match is None or not isinstance(expected_match, dict):
            if exec_result != expected_match:
                return CaseResult(idx, case_id, "fail", f"exec() != {expected_match}")
            return CaseResult(idx, case_id, "pass")
        # Detailed exec result check.
        expected_inputs = expected_match.get("inputs") or entry["inputs"]
        actual_inputs = exec_result.inputs
        if len(actual_inputs) != len(expected_inputs):
            return CaseResult(idx, case_id, "fail", "inputs length mismatch")
        for component in COMPONENTS:
            expected_component = _auto_populate_expected_component(entry, component)
            actual_component = getattr(exec_result, component, None)
            if actual_component is None:
                return CaseResult(idx, case_id, "fail", f"missing exec.{component}")
            if actual_component.get("input") != expected_component.get("input"):
                return CaseResult(idx, case_id, "fail", f"{component}.input mismatch")
            actual_groups = actual_component.get("groups") or {}
            expected_groups = _normalize_expected_groups(expected_component.get("groups") or {})
            if actual_groups != expected_groups:
                return CaseResult(idx, case_id, "fail", f"{component}.groups: {actual_groups!r} vs {expected_groups!r}")
        return CaseResult(idx, case_id, "pass")
    except Exception as exc:  # noqa: BLE001 — script-level catch-all for the report
        return CaseResult(idx, case_id, "error", f"{type(exc).__name__}: {exc}")


def _case_id_for(idx: int, entry: dict[str, Any]) -> str:
    pat = entry.get("pattern", [])
    if pat and isinstance(pat[0], dict):
        summary = ",".join(f"{k}={v!r}" for k, v in pat[0].items())
    elif pat and isinstance(pat[0], str):
        summary = pat[0]
    else:
        summary = "<no-pattern>"
    summary = summary.replace(" ", "")
    if len(summary) > 80:
        summary = summary[:77] + "..."
    return f"{idx:03d}-{summary}"


# -------------------------- compareComponent / generate harness -------------


def _run_compare_case(idx: int, entry: dict[str, Any]) -> CaseResult:
    """One ``urlpattern-compare-test-data.json`` entry."""
    case_id = f"{idx:03d}-{entry['component']}"
    try:
        left = URLPattern(entry["left"])
        right = URLPattern(entry["right"])
        component = entry["component"]
        expected = entry["expected"]
        if URLPattern.compareComponent(component, left, right) != expected:
            return CaseResult(idx, case_id, "fail", f"forward != {expected}")
        if URLPattern.compareComponent(component, right, left) != -expected:
            return CaseResult(idx, case_id, "fail", f"reverse != {-expected}")
        if URLPattern.compareComponent(component, left, left) != 0:
            return CaseResult(idx, case_id, "fail", "self(left) != 0")
        if URLPattern.compareComponent(component, right, right) != 0:
            return CaseResult(idx, case_id, "fail", "self(right) != 0")
    except Exception as exc:  # noqa: BLE001
        return CaseResult(idx, case_id, "error", f"{type(exc).__name__}: {exc}")
    return CaseResult(idx, case_id, "pass")


def _run_generate_case(idx: int, entry: dict[str, Any]) -> CaseResult:
    """One ``urlpattern-generate-test-data.json`` entry.

    The ``.generate()`` method is a tentative-spec feature that has
    only landed in Chromium; this library tracks the suite but does
    not implement the method, so every case reports ``skip``.
    """
    return CaseResult(
        idx,
        f"{idx:03d}-{entry.get('component')}",
        "skip",
        "URLPattern.generate() not implemented (tentative; Chromium-only)",
    )


# -------------------------- inline-test suites ------------------------------
#
# constructor and hasRegExpGroups are code-driven (no JSON corpus); we record
# their summary results only — counts come from running the actual test
# functions inline.


def _run_constructor_inline() -> list[CaseResult]:
    """Mirror of ``tests/test_wpt_constructor.py``."""
    cases: list[CaseResult] = []
    spec_cases = [
        ("unclosed_token_paren", lambda: URLPattern("https://example.org/%(")),
        ("unclosed_token_double_paren", lambda: URLPattern("https://example.org/%((")),
        ("unclosed_escape", lambda: URLPattern("(\\")),
    ]
    for idx, (name, ctor) in enumerate(spec_cases):
        try:
            ctor()
            cases.append(CaseResult(idx, name, "fail", "expected TypeError"))
        except TypeError:
            cases.append(CaseResult(idx, name, "pass"))
        except Exception as exc:  # noqa: BLE001
            cases.append(CaseResult(idx, name, "error", f"{type(exc).__name__}: {exc}"))
    # constructor-with-undefined: must NOT raise
    try:
        pat = URLPattern(None, None)
        if pat.protocol == "*" and pat.pathname == "*":
            cases.append(CaseResult(3, "constructor_with_undefined", "pass"))
        else:
            cases.append(CaseResult(3, "constructor_with_undefined", "fail", "non-wildcard defaults"))
    except Exception as exc:  # noqa: BLE001
        cases.append(CaseResult(3, "constructor_with_undefined", "error", f"{type(exc).__name__}: {exc}"))
    return cases


def _run_hasregexpgroups_inline() -> list[CaseResult]:
    """Mirror of ``tests/test_wpt_hasregexpgroups.py``.

    The corpus is a JS loop over per-component pattern templates; we
    re-emit the same per-component matrix here.
    """
    all_components = ("protocol", "username", "password", "hostname", "port", "pathname", "search", "hash")
    rich_components = tuple(c for c in all_components if c not in ("protocol", "port"))
    cases: list[CaseResult] = []

    def expect(idx: int, name: str, pattern: dict[str, str], expected: bool) -> CaseResult:
        try:
            got = URLPattern(pattern).has_regexp_groups
        except Exception as exc:  # noqa: BLE001
            return CaseResult(idx, name, "error", f"{type(exc).__name__}: {exc}")
        if got is expected:
            return CaseResult(idx, name, "pass")
        return CaseResult(idx, name, "fail", f"expected {expected}, got {got}")

    def add(name: str, pattern: dict[str, str], *, expected: bool) -> None:
        cases.append(expect(len(cases), name, pattern, expected=expected))

    add("empty-init-has-no-regex-groups", {}, expected=False)
    for c in all_components:
        add(f"wildcard-{c}", {c: "*"}, expected=False)
        add(f"segment-{c}", {c: ":foo"}, expected=False)
        add(f"optional-segment-{c}", {c: ":foo?"}, expected=False)
        add(f"named-regex-{c}", {c: ":foo(hi)"}, expected=True)
        add(f"anon-regex-{c}", {c: "(hi)"}, expected=True)
    for c in rich_components:
        add(f"mixed-wildcard-{c}", {c: "a-{:hello}-z-*-a"}, expected=False)
        add(f"mixed-regex-{c}", {c: "a-(hi)-z-(lo)-a"}, expected=True)
    add("complex-pathname-no-regex", {"pathname": "/a/:foo/:baz?/b/*"}, expected=False)
    add("complex-pathname-with-regex", {"pathname": "/a/:foo/:baz([a-z]+)?/b/*"}, expected=True)
    return cases


# -------------------------- rendering ---------------------------------------


def _badge(label: str, value: str, color: str) -> str:
    """One shields.io badge anchored at the suite's section."""
    safe_label = label.replace(" ", "%20").replace("/", "%2F")
    safe_value = value.replace(" ", "%20").replace("/", "%2F")
    return f"![{label} {value}](https://img.shields.io/badge/{safe_label}-{safe_value}-{color}?labelColor=24292f)"


def _status_cell(status: str) -> str:
    """One Unicode-symbol-and-word cell for a single case result."""
    return {
        "pass": f"<kbd>{SYM_PASS}</kbd> pass",
        "fail": f"<kbd>{SYM_FAIL}</kbd> **fail**",
        "xfail": f"<kbd>{SYM_XFAIL}</kbd> xfail",
        "skip": f"<kbd>{SYM_SKIP}</kbd> skip",
        "error": f"<kbd>{SYM_ERROR}</kbd> **error**",
    }[status]


def _suite_badge(suite: SuiteResult) -> str:
    """Header badge for one suite — picks color from the result mix."""
    if suite.is_clean and suite.passing == suite.total:
        return _badge(suite.title, f"{suite.passing}/{suite.total}", COLOR_PASS)
    if suite.is_clean and suite.skipping == suite.total:
        return _badge(suite.title, "skipped (tentative)", COLOR_SKIP)
    if suite.is_clean:
        return _badge(suite.title, f"{suite.passing}/{suite.total}", COLOR_PASS)
    return _badge(suite.title, f"{suite.failing + suite.erroring} failing", COLOR_FAIL)


def _render(suites: list[SuiteResult]) -> str:
    out: list[str] = []
    engine = get_default_engine()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    wpt_ref = _wpt_ref()
    wpt_ref_short = wpt_ref[:7] if len(wpt_ref) >= 7 else wpt_ref
    wpt_tree_url = f"https://github.com/web-platform-tests/wpt/tree/{wpt_ref}/urlpattern"
    wpt_commit_url = f"https://github.com/web-platform-tests/wpt/commit/{wpt_ref}"

    # ---- header
    out.append("# WHATWG URLPattern Conformance Report")
    out.append("")
    out.append(
        f"Generated by `scripts/generate_compliance_report.py` on **{timestamp}**, "
        f"running against [`web-platform-tests/wpt/urlpattern/`]({wpt_tree_url}) "
        f"pinned at [`{wpt_ref_short}`]({wpt_commit_url}) "
        f"with regex engine **`{engine.name}`** "
        f"(set-operation support: {'yes' if engine.supports_set_operations else 'no'}). "
        "Suite names match the upstream WPT runner basenames.",
    )
    out.append("")
    out.append(
        "> **Legend.** "
        f"<kbd>{SYM_PASS}</kbd> pass · "
        f"<kbd>{SYM_FAIL}</kbd> fail · "
        f"<kbd>{SYM_XFAIL}</kbd> xfail (known engine gap) · "
        f"<kbd>{SYM_SKIP}</kbd> skip (tentative spec, not implemented) · "
        f"<kbd>{SYM_ERROR}</kbd> error."
    )
    out.append("")

    # ---- top-of-page badges
    out.extend(_suite_badge(suite) for suite in suites)
    out.append("")

    # ---- summary table
    out.append("## Summary")
    out.append("")
    out.append("| Suite | Total | Pass | XFail | Skip | Fail | Error |")
    out.append("|-------|------:|-----:|------:|-----:|-----:|------:|")
    totals = {"total": 0, "pass": 0, "xfail": 0, "skip": 0, "fail": 0, "error": 0}
    for suite in suites:
        totals["total"] += suite.total
        totals["pass"] += suite.passing
        totals["xfail"] += suite.xfailing
        totals["skip"] += suite.skipping
        totals["fail"] += suite.failing
        totals["error"] += suite.erroring
        out.append(
            f"| [{suite.title}](#{_anchor(suite.title)}) | {suite.total} | "
            f"{suite.passing} | {suite.xfailing} | {suite.skipping} | "
            f"{suite.failing} | {suite.erroring} |",
        )
    out.append(
        f"| **All suites** | **{totals['total']}** | **{totals['pass']}** | "
        f"**{totals['xfail']}** | **{totals['skip']}** | "
        f"**{totals['fail']}** | **{totals['error']}** |",
    )
    out.append("")

    # ---- per-suite tables (collapsible)
    for suite in suites:
        out.append(f"## `{suite.title}`")
        out.append("")
        runner_url = f"https://github.com/web-platform-tests/wpt/blob/{wpt_ref}/urlpattern/{suite.runner_path}"
        line = f"Runner: [`{suite.runner_path}`]({runner_url})"
        if suite.data_path is not None:
            data_url = f"https://github.com/web-platform-tests/wpt/blob/{wpt_ref}/urlpattern/{suite.data_path}"
            line += f" &middot; Data: [`{suite.data_path.split('/')[-1]}`]({data_url})"
        out.append(line)
        out.append("")
        # Always expand if any failures; collapse if all-pass.
        open_attr = "" if suite.is_clean else " open"
        summary_line = (
            f"<summary>{suite.total} cases &mdash; "
            f"{suite.passing} pass"
            + (f", {suite.xfailing} xfail" if suite.xfailing else "")
            + (f", {suite.skipping} skip" if suite.skipping else "")
            + (f", **{suite.failing} fail**" if suite.failing else "")
            + (f", **{suite.erroring} error**" if suite.erroring else "")
            + "</summary>"
        )
        # ``markdown="1"`` opts the children back into Markdown parsing —
        # without it the inner case table renders as raw text because the
        # spec defines content of a block-level HTML element as raw HTML.
        # Requires the ``md_in_html`` extension (already in properdocs.yml).
        out.append(f"<details{open_attr} markdown='1'>")
        out.append(summary_line)
        out.append("")
        out.append("| # | Case | Status | Detail |")
        out.append("|--:|------|:------:|--------|")
        for case in suite.cases:
            # Backtick code-spans render content literally; HTML-escaping
            # apostrophes etc. would surface as ``&#x27;``. Just escape
            # table-breaking characters and collapse newlines.
            name = case.name.replace("`", "\\`").replace("|", "\\|").replace("\n", " ")
            detail = case.detail.replace("|", "\\|").replace("\n", " ") if case.detail else ""
            if len(detail) > 120:
                detail = detail[:117] + "..."
            out.append(f"| {case.index} | `{name}` | {_status_cell(case.status)} | {detail} |")
        out.append("")
        out.append("</details>")
        out.append("")

    return "\n".join(out)


def _anchor(title: str) -> str:
    """Slugify a heading for an in-page link."""
    return title.lower().replace(" ", "-").replace(".", "").replace("`", "").replace("(", "").replace(")", "")


# -------------------------- entry point -------------------------------------


def main() -> int:
    suites: list[SuiteResult] = []

    # Suite titles are the upstream WPT runner filenames so a WHATWG /
    # WPT contributor browsing this report can map our rows to upstream
    # test files at a glance. ``runner_path`` / ``data_path`` are
    # relative to ``web-platform-tests/wpt/urlpattern/``.

    # 1. urlpattern.any.js  (data-driven via urlpatterntestdata.json)
    data_path = WPT_DIR / "urlpatterntestdata.json"
    suite = SuiteResult(
        title="urlpattern.any.js",
        runner_path="urlpattern.any.js",
        data_path="resources/urlpatterntestdata.json",
    )
    for idx, entry in enumerate(json.loads(data_path.read_text(encoding="utf-8"))):
        suite.cases.append(_run_data_corpus_case(idx, entry))
    suites.append(suite)

    # 2. urlpattern-constructor.any.js  (cases inlined in the runner)
    suite = SuiteResult(
        title="urlpattern-constructor.any.js",
        runner_path="urlpattern-constructor.any.js",
    )
    suite.cases = _run_constructor_inline()
    suites.append(suite)

    # 3. urlpattern-hasregexpgroups.any.js  (data file is a JS module)
    suite = SuiteResult(
        title="urlpattern-hasregexpgroups.any.js",
        runner_path="urlpattern-hasregexpgroups.any.js",
        data_path="resources/urlpattern-hasregexpgroups-tests.js",
    )
    suite.cases = _run_hasregexpgroups_inline()
    suites.append(suite)

    # 4. urlpattern-compare.tentative.any.js  (tentative-spec method)
    compare_path = WPT_DIR / "urlpattern-compare-test-data.json"
    suite = SuiteResult(
        title="urlpattern-compare.tentative.any.js",
        runner_path="urlpattern-compare.tentative.any.js",
        data_path="resources/urlpattern-compare-test-data.json",
    )
    for idx, entry in enumerate(json.loads(compare_path.read_text(encoding="utf-8"))):
        suite.cases.append(_run_compare_case(idx, entry))
    suites.append(suite)

    # 5. urlpattern-generate.tentative.any.js  (tentative-spec method)
    generate_path = WPT_DIR / "urlpattern-generate-test-data.json"
    suite = SuiteResult(
        title="urlpattern-generate.tentative.any.js",
        runner_path="urlpattern-generate.tentative.any.js",
        data_path="resources/urlpattern-generate-test-data.json",
    )
    for idx, entry in enumerate(json.loads(generate_path.read_text(encoding="utf-8"))):
        suite.cases.append(_run_generate_case(idx, entry))
    suites.append(suite)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    # WPT case names (e.g. case 157) contain unpaired surrogates by design
    # to exercise our U+FFFD substitution. They can't be UTF-8 encoded, so
    # we escape them with backslashreplace before writing the file.
    OUTPUT.write_bytes(_render(suites).encode("utf-8", errors="backslashreplace"))

    total = sum(s.total for s in suites)
    failing = sum(s.failing + s.erroring for s in suites)
    print(f"Wrote {OUTPUT.relative_to(REPO)}: {total} cases, {failing} failing.")
    return 0 if failing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
