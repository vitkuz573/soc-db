"""Benchmark and profile enrichment CPU usage.

Measures per-chip CPU time and total pipeline throughput to determine
whether ProcessPoolExecutor is warranted for CPU-bound enrichment work
when called from the async API.

Recommendation threshold: if total pipeline time exceeds 500ms for the
full chip set, ProcessPoolExecutor should be considered.
"""

import json
import time
from pathlib import Path

from soc_db.common import enrich_one


def load_all_chips():
    chips = []
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    for path in sorted(data_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        with open(path) as f:
            chips.extend(json.load(f))
    return chips


CHIPS = load_all_chips()


class TestEnrichOneThroughput:
    """Measure end-to-end enrichment throughput on the full chip set."""

    def test_enrich_one_throughput(self, benchmark):
        """Time for enrich_one() on ALL chips (wall-clock, single-threaded)."""
        @benchmark
        def run():
            for chip in CHIPS:
                enrich_one(chip)

    def test_enrich_one_single(self, benchmark):
        """Time for enrich_one() on a single representative chip."""
        chip = CHIPS[0]
        benchmark(enrich_one, chip)


class TestEnrichOneCpuProfile:
    """CPU profiling to determine if process pool is warranted."""

    def test_enrich_one_total_cpu_time(self):
        """Measure total CPU time for enriching ALL chips.

        This test runs outside the pytest-benchmark fixture to capture
        precise timing without benchmark overhead.  Result is printed
        as a recommendation.
        """
        sample_size = min(len(CHIPS), 500)
        sample = CHIPS[:sample_size]

        start = time.perf_counter()
        for chip in sample:
            enrich_one(chip)
        elapsed = time.perf_counter() - start

        per_chip_ms = (elapsed / sample_size) * 1000
        total_estimated_s = elapsed * (len(CHIPS) / sample_size)

        print(f"\n{'='*60}")
        print(f"Enrichment CPU Profile ({sample_size}/{len(CHIPS)} chips)")
        print(f"{'='*60}")
        print(f"  Sample size:      {sample_size}")
        print(f"  Total chips:      {len(CHIPS)}")
        print(f"  Wall-clock time:  {elapsed:.3f}s for {sample_size} chips")
        print(f"  Per chip:         {per_chip_ms:.2f}ms")
        print(f"  Estimated full:   {total_estimated_s:.1f}s for {len(CHIPS)} chips")
        print(f"{'='*60}")

        if total_estimated_s > 0.5:
            print("  >> RECOMMENDATION: Use ProcessPoolExecutor for enrichment")
            print(f"  >> Estimated {total_estimated_s:.1f}s would block the event loop")
        else:
            print("  >> RECOMMENDATION: No process pool needed")
            print(f"  >> Estimated {total_estimated_s:.1f}s is acceptable inline (<500ms threshold)")
        print(f"{'='*60}\n")

        # Assert not performing assertion — this is informational
        assert per_chip_ms > 0  # Sanity check
