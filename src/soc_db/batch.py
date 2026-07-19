"""Batch enrichment with checkpointing and crash recovery.

The ``BatchEnricher`` processes chip records in configurable batch sizes,
persisting progress to a checkpoint JSON file after each batch. If the
process is interrupted, it resumes from the last completed batch,
avoiding redundant re-processing.

Usage::

    enricher = BatchEnricher(batch_size=500)
    chips = load_all_chips()
    result = enricher.enrich_all(chips)  # or enricher.run(chips)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from soc_db.common import enrich_one

logger = logging.getLogger(__name__)

# Default checkpoint directory (under CACHE_DIR)
DEFAULT_CHECKPOINT_DIR = Path(
    os.environ.get("SOC_DB_CACHE_DIR", "/tmp")
) / "soc-db-checkpoints"


class BatchEnricher:
    """Enrich chip records in batches with crash recovery.

    Attributes:
        batch_size: Number of chips per batch (default 500).
        checkpoint_dir: Directory to store checkpoint JSON files.
        checkpoint_path: Full path to the current checkpoint file.
        progress: Number of chips processed so far in the current run.
        start_time: Monotonic timestamp at which the current run started.
    """

    def __init__(
        self,
        batch_size: int = 500,
        checkpoint_dir: str | Path | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.checkpoint_dir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.checkpoint_dir / "batch_enrich.json"
        self.progress = 0
        self.start_time = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich_all(self, chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich all chips with checkpointing and crash recovery.

        Loads the last checkpoint (if any), resumes from that point, and
        saves a new checkpoint every ``batch_size`` chips.

        Args:
            chips: The full list of chip records to enrich (modified
                   in-place).

        Returns:
            The enriched chip list (same objects as the input).
        """
        self.start_time = time.monotonic()
        self.progress = self._load_checkpoint()
        total = len(chips)

        if self.progress > 0:
            logger.info(
                "Resuming from checkpoint — %d / %d chips already processed",
                self.progress,
                total,
            )

        # Enrich the remainder in batches
        for batch_start in range(self.progress, total, self.batch_size):
            batch_end = min(batch_start + self.batch_size, total)
            batch = chips[batch_start:batch_end]

            for chip in batch:
                enrich_one(chip)

            self.progress = batch_end
            self._save_checkpoint(self.progress)

            elapsed = time.monotonic() - self.start_time
            rate = self.progress / max(elapsed, 0.001)
            logger.info(
                "Batch [%d:%d] — %d / %d chips (%.1f chips/sec)",
                batch_start,
                batch_end,
                self.progress,
                total,
                rate,
            )

        # Clean up checkpoint on successful completion
        self._clear_checkpoint()
        elapsed = time.monotonic() - self.start_time
        logger.info(
            "Batch enrichment complete — %d chips in %.1fs (%.1f chips/sec)",
            total,
            elapsed,
            total / max(elapsed, 0.001),
        )

        return chips

    def run(self, chips: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Alias for :meth:`enrich_all`."""
        return self.enrich_all(chips)

    def get_progress(self) -> int:
        """Return the number of chips processed in the current run."""
        return self.progress

    def get_elapsed(self) -> float:
        """Return the elapsed wall-clock time in seconds."""
        return time.monotonic() - self.start_time

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    def _load_checkpoint(self) -> int:
        """Load progress from the checkpoint file.

        Returns:
            The number of chips already processed (0 if no checkpoint
            exists or the file is corrupt).
        """
        if not self.checkpoint_path.exists():
            return 0
        try:
            data = json.loads(self.checkpoint_path.read_text("utf-8"))
            count: int = data.get("processed", 0)
            logger.info("Loaded checkpoint: %d chips processed", count)
            return count
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Corrupt checkpoint file — starting fresh: %s", exc)
            return 0

    def _save_checkpoint(self, count: int) -> None:
        """Persist progress to the checkpoint JSON file.

        Args:
            count: Number of chips successfully enriched so far.
        """
        data = {
            "processed": count,
            "timestamp": time.time(),
            "batch_size": self.batch_size,
        }
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.write_text(
            json.dumps(data, indent=2), "utf-8"
        )

    def _clear_checkpoint(self) -> None:
        """Remove the checkpoint file after successful completion."""
        try:
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
                logger.debug("Checkpoint file removed")
        except OSError as exc:
            logger.warning("Could not remove checkpoint file: %s", exc)
