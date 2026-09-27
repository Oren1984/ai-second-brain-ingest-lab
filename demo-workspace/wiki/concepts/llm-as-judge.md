---
id: llm-as-judge
title: LLM-as-judge
type: concept
summary: Using a second model to score answers when human grading does not scale.
sources: [src-rag-eval-primer]
status: stable
updated: seed
---
# LLM-as-judge

A judge model scores another model's output against a rubric, for example the
[[faithfulness-evaluation]] of a RAG answer.

## Caveats

- Judges can be lenient toward fluent answers; spot-check against human labels
  ([[src-rag-eval-primer]]).
