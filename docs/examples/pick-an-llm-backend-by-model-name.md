# Pick an LLM backend by model name

If you run an LLM proxy in front of multiple providers — OpenAI, Anthropic,
Bedrock, your own local vLLM — you need a routing table that maps
`gpt-4o-2024-08-06` to OpenAI, `claude-3-sonnet` to Anthropic, and so on.
[LiteLLM](https://github.com/BerriAI/litellm) is the dominant Python
implementation; it hand-rolls the pattern-specificity scorer.

## The awkward way

From [`litellm/router_utils/pattern_match_deployments.py`](https://github.com/BerriAI/litellm/blob/main/litellm/router_utils/pattern_match_deployments.py):

```python
def _pattern_to_regex(self, pattern: str) -> str:
    """
    pattern: openai/*
    regex:   openai/.*
    pattern: openai/team::*::static::*
    regex:   openai/team::.*::static::.*
    """
    return re.escape(pattern).replace(r"\*", "(.*)")

@staticmethod
def calculate_pattern_specificity(pattern: str) -> Tuple[int, int]:
    complexity_chars = ["*", "+", "?", "\\", "^", "$", "|", "(", ")"]
    return (len(pattern),
            sum(pattern.count(c) for c in complexity_chars))

def route(self, request: str):
    for pattern, deployments in PatternUtils.sorted_patterns(self.patterns):
        if re.match(pattern, request):
            return deployments
```

`_pattern_to_regex` is essentially URLPattern's `*` wildcard handling
re-implemented; `calculate_pattern_specificity` is essentially
`compareComponent()` re-implemented. Both have known footguns — an
asterisk inside a literal segment, complexity-char counting that ranks
two patterns the same when they shouldn't be.

## With URLPattern

```python
from functools import cmp_to_key
from yarlpattern import URLPattern

ROUTES: list[tuple[URLPattern, str]] = [
    (URLPattern({"pathname": "/openai/gpt-4o-mini"}),                "openai-fast"),
    (URLPattern({"pathname": "/openai/gpt-4o-2024-08-06"}),          "openai-pinned"),
    (URLPattern({"pathname": "/openai/:rest+"}),                     "openai-default"),
    (URLPattern({"pathname": "/anthropic/claude-3-haiku"}),          "anthropic-fast"),
    (URLPattern({"pathname": "/anthropic/:rest+"}),                  "anthropic-default"),
    (URLPattern({"pathname": "/bedrock/:rest+"}),                    "bedrock"),
]

# Spec-defined specificity: more specific patterns sort *before* more general
# ones. Replaces LiteLLM's manual "count complexity chars" heuristic.
ROUTES.sort(key=cmp_to_key(lambda a, b: URLPattern.compareComponent("pathname", a[0], b[0])))

def pick_deployment(request_path: str) -> str | None:
    for pat, deployment in ROUTES:
        if pat.test("https://x" + request_path):
            return deployment
    return None

pick_deployment("/openai/gpt-4o-mini")             # 'openai-fast'
pick_deployment("/openai/gpt-4o-2024-08-06")       # 'openai-pinned'
pick_deployment("/openai/gpt-4-turbo")             # 'openai-default' (fell through)
pick_deployment("/anthropic/claude-3-haiku")       # 'anthropic-fast'
```

## What you get for free

- **`compareComponent()` is the spec-defined version of LiteLLM's
  `calculate_pattern_specificity`.** Deterministic ordering, no manual
  "count the wildcards" heuristic, identical results across
  implementations (Chromium, Safari, Firefox, yarlpattern).
- **Pattern syntax is portable.** The same routing table can live in
  a Cloudflare Worker LLM gateway, a Deno proxy, or your Python
  service. LiteLLM's syntax is LiteLLM-specific.
- **Multi-segment wildcard via `:rest+`.** The `+` modifier means
  "one or more segments", so `/openai/:rest+` matches `/openai/foo`
  *and* `/openai/foo::static::bar` — replacing LiteLLM's
  `re.escape + replace` dance.
- **One pattern object, two operations.** `test()` says "does this
  route apply?", `exec()` returns the named groups for downstream
  use (rate-limit-by-model, per-deployment auth). LiteLLM keeps these
  separate.
