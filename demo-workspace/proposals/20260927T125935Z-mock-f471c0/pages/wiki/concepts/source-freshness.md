---
id: source-freshness
title: Source freshness and versioning
type: concept
summary: Whether retrieved passages come from the current version of a document; the cause of stale-but-faithful answers.
sources: [src-sample-incident-review-stale-policy]
status: stable
updated: 20260927T125935Z-mock-f471c0
---
# Source freshness and versioning

A [[rag-pipeline]] can retrieve a passage that is relevant and well ranked but
comes from a superseded version of a document. [[retrieval-quality]] metrics
such as recall@k do not detect this, and [[faithfulness-evaluation]] rewards an
answer that faithfully repeats the outdated passage.

## Controls

- Attach `effective_date` and `superseded_by` metadata at ingestion.
- Filter or down-rank superseded chunks at retrieval time.
- For high-stakes questions, compare answers with maintained reference answers.

Evidence: [[src-sample-incident-review-stale-policy]] (a single fictional incident).
