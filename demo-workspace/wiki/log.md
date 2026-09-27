# Log

Append-only record of applied ingests. Written by the engine; one entry per applied run.

## [seed] initial knowledge base | hand-written sample

- 4 concept pages and 1 source page written by hand for the demo scenario; no ingest run.

## [2026-09-27 12:59 UTC] ingest | SAMPLE: Post-incident review — policy assistant cited a superseded document

- run: `20260927T125935Z-mock-f471c0` — mode: **mock** (MOCK — deterministic hand-authored fixture, no LLM call)
- source: `raw/sample-incident-review-stale-policy.md` (sha256 `f471c0a45f83…`) → [[src-sample-incident-review-stale-policy]]
- approved c1: update [[faithfulness-evaluation]]
- approved c2: create [[source-freshness]]
- approved c3: create [[src-sample-incident-review-stale-policy]]
- approved c4: update [[rag-pipeline]] (edited by reviewer)
- rejected c5: update llm-as-judge — Misreads the source: the judge scored faithfulness correctly. The gap was freshness, covered by c1 and c2.
- contradiction on [[faithfulness-evaluation]]: Narrow the conclusion: faithfulness is necessary but not sufficient; add freshness and correctness checks; mark needs-review until corroborated.
- reviewer: demo reviewer (pre-recorded decisions file, not typed live)
- validation: passed (0 error(s), 1 warning(s))
