---
id: faithfulness-evaluation
title: Faithfulness evaluation
type: concept
summary: Whether every claim in a generated answer is supported by the retrieved context — a grounding check, not a correctness check.
sources: [src-rag-eval-primer, src-sample-incident-review-stale-policy]
status: needs-review
updated: 20260927T125935Z-mock-f471c0
---
# Faithfulness evaluation

Faithfulness checks that each claim in an answer is supported by the passages
the [[rag-pipeline]] retrieved. It is typically scored by an [[llm-as-judge]].

## What it measures — and what it does not

Faithfulness measures grounding in *what was retrieved*. It says nothing about
whether the retrieved passages are current or correct. A fully faithful answer
can still be wrong when retrieval returns a superseded document; see
[[source-freshness]].

## Current conclusion (revised)

A high faithfulness score (>= 0.9) is a **necessary but not sufficient**
release signal. Keep it as a gate — it catches unsupported claims — but pair it
with a [[source-freshness]] check and, for high-stakes questions, a correctness
check against reference answers.

## Contradictions and revisions

- **Earlier claim:** faithfulness >= 0.9 means an answer is correct and safe to
  ship ([[src-rag-eval-primer]]).
- **New evidence:** an answer scored 0.96 faithfulness yet quoted a superseded
  policy and gave an employee wrong information ([[src-sample-incident-review-stale-policy]]).
- **Resolution:** the earlier conclusion is narrowed, not discarded. Status is
  `needs-review` until a second, independent source corroborates it.
