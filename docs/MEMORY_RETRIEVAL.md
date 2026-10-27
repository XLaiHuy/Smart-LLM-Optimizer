# Memory Retrieval & Integration

## Implemented

`backend/app/memory/retrieval.py` retrieves persisted `Fact` and `Summary`
items from `SessionSnapshot`.

- lexical relevance from the current query;
- recency from source-message position;
- importance weighting, with facts prioritized over summaries;
- token-budget selection;
- latency and token-savings metrics;
- deterministic `recall_at_k()` based on source message IDs.

`ContextFeatures.memory` carries retrieved memory into the Hybrid Context
Manager. `ContextOptimizer` accepts an optional `MemoryRetriever`, reserves a
portion of the context budget for memory, and preserves memory IDs in the
assembled context.

## Validation

```text
42 optimizer and memory tests passed
ruff check: pass
mypy retrieval/context integration: pass
```

The implementation is deterministic and does not extract new facts or call an
LLM. Production wiring still needs to replace `NoOpMemoryManager` in the
composition root and agree on the core/orchestrator integration contract.
