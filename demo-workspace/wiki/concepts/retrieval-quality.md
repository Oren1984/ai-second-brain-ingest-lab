---
id: retrieval-quality
title: Retrieval quality
type: concept
summary: How well the retriever returns the passages an answer needs (recall@k, context relevance).
sources: [src-rag-eval-primer]
status: stable
updated: seed
---
# Retrieval quality

Retrieval quality asks whether the retriever in a [[rag-pipeline]] returned the
passages a good answer needs.

- **recall@k** — share of relevant passages found in the top *k* results.
- **Context relevance** — whether the retrieved passages are on-topic for the question.

Both are measured before generation, so they are independent of
[[faithfulness-evaluation]]. Source: [[src-rag-eval-primer]].
