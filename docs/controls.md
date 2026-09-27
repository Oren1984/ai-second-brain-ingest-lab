# Controls

Controls sized for a local, single-user tool. Each row names where it lives and which test exercises it
(`tests/test_ingest.py`).

## Governance

| Control | Where | Test |
|---|---|---|
| Written contract for what the agent may change | `schema/WIKI_SCHEMA.md` | — |
| Human decision required for every change before apply | `record_review`, `apply_run` | `test_review_requires_a_decision_for_every_change` |
| Reviewer can correct a change (edit the staged file) and the edit is recorded | `record_review`, `apply_run` (`edited_by_reviewer`) | `test_approved_ingest_updates_existing_page_links_index_and_log` |
| Rejection leaves the wiki byte-identical | `apply_run` | `test_rejecting_everything_leaves_wiki_byte_identical` |
| Proposals go stale if their target pages change | `apply_run` (base sha256 per change) | `test_apply_refuses_stale_proposal` |

## Security

| Control | Where | Test |
|---|---|---|
| Raw and generated content separated; engine never writes `raw/` | `Workspace._check_writable` allowlist | `test_engine_cannot_write_to_raw_or_outside_workspace` |
| `add` never overwrites an existing raw source | `add_source` | — |
| Page ids must be slugs — no paths, no traversal | `check_proposal` (`ID_RE`) | `test_invalid_or_hostile_model_output_fails_without_writing[path traversal id]` |
| Model cannot write index, log, other source pages, or delete | `check_proposal` | same test, other cases |
| Source text treated as data: sanitised, wrapped in `<untrusted_source>`, closing-tag escape neutralised | `sanitise_source`, `build_prompt` | `test_injection_text_is_flagged_and_wrapped_as_data` |
| Instruction-like text flagged and shown to the reviewer | `injection_flags` | same |
| Model has no tools; output is only a proposal | `AnthropicProvider` (no `tools` param) | — |
| `<script>` / `javascript:` rejected in page content | `validate.check_pages` | — |
| API key read only from `ANTHROPIC_API_KEY`, never written; errors redacted | `providers.py`, `workspace.redact` | `test_secrets_are_redacted_from_logged_errors` |
| LLM mode without a key sends nothing | `AnthropicProvider._get_client` | `test_llm_mode_without_credentials_sends_nothing_and_writes_nothing` |
| Site escapes every string before inserting HTML | `site/app.js` (`esc`) | reviewed manually |
| Demo reset refuses directories it didn't create | `tools/demo.py safe_reset` | `test_demo_reset_refuses_directories_it_did_not_create` |

**Honest limit:** the injection flagging is a heuristic regex list and will miss rephrased attacks. The
real protection is structural — the model has no tools, its output is policy-checked, and a human
approves every change before it is written.

## Observability

`runs/<run-id>.json` records: run id (includes mode), mode label, provider and model, source path and
sha256, stage events with timestamps, security flags, the proposal (interpretation, contradictions,
changes with diffs, validation preview), reviewer and decisions, applied/rejected change ids,
whether each was edited, final validation, and errors. `wiki/log.md` gets a human-readable entry
only when something was applied. `python -m brain status` lists runs.

## Quality

`python -m brain validate` (also run as preflight and after apply):

- errors: missing required fields, invalid ids, id/file/type mismatch, broken `[[links]]`,
  unknown or non-source entries in `sources`, concept pages without sources, source page without
  `raw_path`/`raw_sha256`, raw file missing or changed (sha256), duplicate ids or titles, stale index,
  forbidden content
- warnings: `status: needs-review` (the contradiction signal), concept pages with no inbound links

Tests: `test_validator_catches_broken_links_missing_fields_and_duplicates`,
`test_raw_sources_are_never_modified_and_tampering_is_detected`,
`test_apply_is_all_or_nothing_when_approved_set_is_invalid`,
`test_repeat_ingest_of_unchanged_source_is_a_noop`.
