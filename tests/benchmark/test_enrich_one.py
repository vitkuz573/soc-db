"""Benchmark tests for enrich_one."""

import json
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


class TestEnrichOneBenchmark:
    def test_enrich_one_throughput(self, benchmark):
        @benchmark
        def run():
            for chip in CHIPS:
                enrich_one(chip)

    def test_enrich_one_single(self, benchmark):
        chip = CHIPS[0]
        benchmark(enrich_one, chip)
