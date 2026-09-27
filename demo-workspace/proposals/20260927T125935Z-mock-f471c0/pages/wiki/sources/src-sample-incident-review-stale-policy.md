---
id: src-sample-incident-review-stale-policy
title: "SAMPLE: Post-incident review — policy assistant cited a superseded document"
type: source
summary: Fictional incident in which a 0.96-faithfulness answer was wrong because it was grounded in a superseded policy.
sources: [src-sample-incident-review-stale-policy]
status: stable
updated: 20260927T125935Z-mock-f471c0
raw_path: raw/sample-incident-review-stale-policy.md
raw_sha256: f471c0a45f8300ea6967b17c82b1cf5a3bd62cf4af0b4998e2bbd454916a2e36
---
# SAMPLE: Post-incident review — policy assistant cited a superseded document

Fictional sample source. Key points:

- An HR-policy RAG assistant answered "12 weeks" of parental leave from the
  superseded 2023 policy; the current policy says 16 weeks.
- Judge-scored faithfulness was 0.96 and retrieval recall@5 was high: every
  automated gate passed.
- Root cause: old and new policies were both indexed without effective-date
  metadata, and the old one ranked higher ([[source-freshness]]).
- Revises [[faithfulness-evaluation]]: faithfulness is grounding, not correctness.
- The raw file contains an instruction addressed to AI assistants. It was
  treated as quoted data and not acted on.
