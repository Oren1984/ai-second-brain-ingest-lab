---
id: faithfulness-evaluation
title: Faithfulness evaluation
type: concept
summary: Whether every claim in a generated answer is supported by the retrieved context.
sources: [src-rag-eval-primer]
status: stable
updated: seed
---
# Faithfulness evaluation

Faithfulness checks that each claim in an answer is supported by the passages
the [[rag-pipeline]] retrieved. It is typically scored by an [[llm-as-judge]].

## Current conclusion

A high faithfulness score (>= 0.9) is the signal that an answer is **correct
and safe to ship**; the pilot adopted it as the release gate
([[src-rag-eval-primer]]).
