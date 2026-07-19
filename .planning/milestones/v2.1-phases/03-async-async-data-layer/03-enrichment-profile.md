# Enrichment CPU Profile Results

**Date:** 2026-07-19

## Results

- Sample size: 500/1761 chips
- Wall-clock time: 0.052s
- Per chip: 0.10ms
- Estimated full set: 0.2s

## Recommendation

No process pool needed — enrichment is not CPU-bound enough to warrant offloading.

## Rationale

The total estimated enrichment time for the full chip set is 0.2 seconds, well under the
500ms threshold where event-loop blocking becomes a concern. At 0.10ms per chip,
enrichment consumes negligible CPU time. When called from the async API, running
enrichment inline (within the async handler's thread) is acceptable — it will not
measurably block the event loop.

If enrichment logic becomes significantly more expensive in the future (e.g., adding
external API calls or ML inference), the profiling infrastructure in
`tests/benchmark/test_enrich_one.py` will detect the increase and flag the need for
process pool deployment.
