# Examples

Worked examples — each page is one real problem, the awkward way to solve it
without URLPattern, and the URLPattern-shaped replacement. Every snippet has
been verified against the test suite.

## Web routing

- [Route a multi-tenant API by subdomain](route-a-multi-tenant-api-by-subdomain.md)
- [Add subdomain routing to aiohttp](add-subdomain-routing-to-aiohttp.md)
- [Add subdomain routing to FastAPI](add-subdomain-routing-to-fastapi.md)
- [Validate inbound webhooks by URL shape](validate-inbound-webhooks-by-url-shape.md)

## Security

- [Avoid regex hostname-allowlist credential leaks](avoid-regex-hostname-allowlist-vulns.md)

## AI / model serving

- [Match the KServe `/v2/models` inference path](match-the-kserve-v2-inference-path.md)
- [Pick an LLM backend by model name](pick-an-llm-backend-by-model-name.md)
- [Replace MCP resource URI templates](replace-mcp-resource-uri-templates.md)
- [Translate `google.api.http` to URLPattern](translate-google-api-http-to-urlpattern.md)

## Text + data pipelines

- [Classify GitHub URLs in markdown](classify-github-urls-in-markdown.md)
- [Extract YouTube video IDs from any URL form](extract-youtube-video-ids-from-any-url-form.md)
- [Match Slack callback IDs with structured data](match-slack-callback-ids-with-structured-data.md)

---

Every example follows the same shape:

1. **The problem** — what someone is actually trying to do, with a real public
   reference (issue link, blog post, framework doc).
2. **The awkward way** — typical Python today: `urlparse` + `if host == …`
   ladders, hand-rolled regex, or framework-specific config gymnastics.
3. **With URLPattern** — one declarative pattern, structured match result.
4. **What you get for free** — which URLPattern feature carried the weight
   (cross-component matching, optional segments, named groups with regex,
   `compareComponent()`, custom-scheme support, …).
