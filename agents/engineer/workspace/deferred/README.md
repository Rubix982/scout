# Deferred code

Not in the import path. Kept for reference, not execution.

## `openai_enrichment.py`

Was `src/clients/openai.py`. Removed from `src/` in E-001 because decision O-001
took LLM-as-search off the critical path, and E-007 then dropped the `openai`
dependency — leaving the module unimportable and `src/` incoherent.

Do not reinstate as-is. It issued six `gpt-4o` completions per company asking
questions like "Any recent news about {company}?" with no web access or search
tool, which cannot be a freshness mechanism. If LLM enrichment returns, it is for
*soft* signals only (positioning, funding narrative), search-grounded, with
citations retained — never for role data, which comes from ATS APIs, and never
for contact emails.
