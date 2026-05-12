# Match Slack callback IDs with structured data

[Slack Bolt for Python](https://github.com/slackapi/bolt-python) handles
inbound Slack interactions: shortcuts, action buttons, slash commands,
modal submissions. Every one is keyed by a `callback_id` — and the
Bolt API takes `Union[str, re.Pattern]` for every dispatch method,
because real apps encode structured data inside the callback_id.

## The awkward way

A Bolt app that supports a per-task complete-button — one button per
task — usually encodes the task id and acting user inside the
callback_id and re-parses it in the handler:

```python
import re
from slack_bolt import App

app = App(...)

@app.action(re.compile(r"^task_complete:(\d+):([a-z]+)$"))
def handle_task_complete(ack, payload):
    ack()
    action_id = payload["actions"][0]["action_id"]
    parts = action_id.split(":")
    task_id = int(parts[1])
    user = parts[2]
    complete_task(task_id, user)
```

Two pieces of duplication: the regex pattern says "task_complete:N:user"
but the handler then re-parses it with `.split(":")` to actually
extract the values. If the format changes — say you add a workspace
prefix `workspace_complete:WORKSPACE:TASK:USER` — both the dispatch
regex *and* the handler's `.split(":")` indexing must change in lockstep.

## With URLPattern

URLPattern matches *URLs*, not arbitrary strings, but a Bolt
`callback_id` round-trips cleanly through the `pathname` component:

```python
from yarlpattern import URLPattern

TASK_COMPLETE = URLPattern({
    "pathname": "/task_complete/:task_id(\\d+)/:user([a-z]+)",
})

def _decode(callback_id: str):
    """Match against the callback_id by treating it as a pathname."""
    return TASK_COMPLETE.exec(f"https://x.example/{callback_id}")

@app.action(re.compile(r"^task_complete/.*"))  # broad gate
def handle_task_complete(ack, payload):
    ack()
    action_id = payload["actions"][0]["action_id"]
    result = _decode(action_id)
    if result is None:
        return  # malformed; let it 404
    groups = result.pathname["groups"]
    complete_task(int(groups["task_id"]), groups["user"])
```

Two wins:

1. **The pattern declares the field types.** `:task_id(\\d+)` and
   `:user([a-z]+)` mean the values are pre-validated by the time the
   handler runs.
2. **No `.split(":")` in the handler.** `result.pathname["groups"]`
   *is* the structured data. Adding a workspace prefix
   (`/workspace/:workspace/task_complete/:task_id/:user`) doesn't
   touch the handler at all — the new group just appears in
   `result.pathname["groups"]["workspace"]`.

The Bolt-side `@app.action()` is still required for routing (it's
Bolt's mechanism), but it becomes a broad gate. The structural
parsing — what the regex was *really* doing — lives in URLPattern.

## What you get for free

- **Named groups with per-group regex.** `:task_id(\\d+)` is type
  enforcement *and* destructuring in one declaration. The hand-rolled
  regex separated those concerns.
- **Single source of truth.** The pattern is the schema; the schema
  is the parser. The Bolt-style `Union[str, Pattern]` keeps validation
  and extraction in two different places.
- **Extends without surgery.** Adding `:workspace` to the front of
  the callback_id is one segment in the pattern. The split-index
  refactor that would have been required disappears.
- **Reusable beyond Slack.** Any structured-id situation — GitHub
  issue numbers in branch names, Stripe metadata keys, BigQuery
  resource IDs — uses the same pattern.
