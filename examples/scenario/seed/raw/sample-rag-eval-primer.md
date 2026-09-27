# SAMPLE SOURCE — RAG evaluation primer (fictional teaching note)

> Sample material written for the ai-second-brain-ingest-lab demo. Not a real
> publication and not a claim about any real system.

A retrieval-augmented generation (RAG) system is usually evaluated at two points.

**Retrieval** is scored with recall@k and context relevance: did the retriever
bring back the passages a good answer needs?

**Generation** is scored with *faithfulness*: is every claim in the answer
supported by the retrieved passages? Faithfulness is often scored by a second
model acting as a judge ("LLM-as-judge"), because human grading does not scale.

In our pilot, answers with a judge-scored faithfulness above 0.9 were rarely
flagged by reviewers. The team therefore adopted faithfulness >= 0.9 as the
release gate: a high faithfulness score is treated as the signal that an answer
is correct and safe to ship.

Known caveat: judge models can be lenient toward fluent answers and should be
spot-checked against human labels.
