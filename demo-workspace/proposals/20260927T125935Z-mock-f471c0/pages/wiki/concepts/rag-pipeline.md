---
id: rag-pipeline
title: RAG pipeline
type: concept
summary: The stages of a retrieval-augmented generation system and where each is evaluated.
sources: [src-rag-eval-primer, src-sample-incident-review-stale-policy]
status: stable
updated: 20260927T125935Z-mock-f471c0
---
# RAG pipeline

A retrieval-augmented generation (RAG) system answers a question in two steps:
a retriever selects passages from an indexed corpus, and a generator writes an
answer grounded in those passages.

## Stages and their checks

1. **Ingest and index** — documents are chunked and embedded, with version
   metadata checked by [[source-freshness]].
2. **Retrieve** — scored by [[retrieval-quality]].
3. **Generate** — scored by [[faithfulness-evaluation]], usually with an [[llm-as-judge]].

For high-stakes questions, add a correctness check against reference answers
(see [[faithfulness-evaluation]]).

Evaluation approach summarised from [[src-rag-eval-primer]]; freshness stage
added after [[src-sample-incident-review-stale-policy]].
