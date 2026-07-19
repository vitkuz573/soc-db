from __future__ import annotations

from soc_db.enrich._helpers import _has, clean
from soc_db.enrich._vendor_data import (
    FIELD_GROUPS,
    FIELD_WEIGHTS,
    MEMORY_CLOCK_FROM_TYPE,
    VENDOR_FILES,
    VENDOR_KNOWLEDGE,
)
from soc_db.enrich.aliases import infer_aliases
from soc_db.enrich.connectivity import infer_bluetooth, infer_wifi
from soc_db.enrich.cpu import infer_cpu
from soc_db.enrich.gpu import infer_gpu
from soc_db.enrich.memory import infer_memory
from soc_db.enrich.modem import infer_modem
from soc_db.enrich.npu import infer_npu
from soc_db.enrich.process import infer_process
from soc_db.enrich.scoring import compute_completeness
from soc_db.enrich.storage import infer_storage
from soc_db.enrich.year import infer_year

__all__ = [
    "VENDOR_KNOWLEDGE",
    "FIELD_GROUPS",
    "FIELD_WEIGHTS",
    "MEMORY_CLOCK_FROM_TYPE",
    "VENDOR_FILES",
    "_has",
    "clean",
    "enrich_one",
    "enrich_all",
    "infer_year",
    "infer_process",
    "infer_memory",
    "infer_gpu",
    "infer_modem",
    "infer_npu",
    "infer_wifi",
    "infer_bluetooth",
    "infer_storage",
    "infer_cpu",
    "infer_aliases",
    "compute_completeness",
]
