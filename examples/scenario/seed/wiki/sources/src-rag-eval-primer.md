---
id: src-rag-eval-primer
title: "SAMPLE: RAG evaluation primer"
type: source
summary: Fictional teaching note describing retrieval and faithfulness metrics and a faithfulness >= 0.9 release gate.
sources: [src-rag-eval-primer]
status: stable
updated: seed
raw_path: raw/sample-rag-eval-primer.md
raw_sha256: 4b8d6afcd0ec4318647d4436883ebcfe2de21f22c5e35e078ebe72d3a535ac14
---
# SAMPLE: RAG evaluation primer

Fictional sample source. Key points:

- Retrieval is scored with recall@k and context relevance ([[retrieval-quality]]).
- Generation is scored with faithfulness, usually by an [[llm-as-judge]].
- The pilot adopted faithfulness >= 0.9 as the release gate ([[faithfulness-evaluation]]).
