"""UUID-based canonical chip identity and multi-strategy dedup engine.

The ``DedupEngine`` provides deterministic UUID5 generation from
(vendor, model) fingerprints and a multi-strategy matcher that tries
exact model → alias registry → vendor regex → Wikidata QID → rapidfuzz
fuzzy matching in order.  The existing slug-based ``id`` is preserved
as a backward-compatible identifier; UUID is stored separately as
``chip["uuid"]``.
"""

from __future__ import annotations

import logging
import re
import uuid as _uuid
from typing import Any

from soc_db.enrich._vendor_data import VENDOR_KNOWLEDGE

logger = logging.getLogger(__name__)

# DNS namespace UUID for deterministic UUID5 generation
_UUID_NS = _uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


# ---------------------------------------------------------------------------
# UUID generation
# ---------------------------------------------------------------------------

def chip_uuid(vendor: str, model: str) -> str:
    """Generate a deterministic UUID5 from a (vendor, model) fingerprint.

    Args:
        vendor: Manufacturer name (e.g. ``"Qualcomm"``).
        model:  Model number (e.g. ``"SM8550"``).

    Returns:
        32-character lowercase hex string (no hyphens).
    """
    key = f"{vendor.strip().lower()}:{model.strip().lower()}"
    return _uuid.uuid5(_UUID_NS, key).hex


# ---------------------------------------------------------------------------
# Alias registry
# ---------------------------------------------------------------------------

CHIP_ALIASES: dict[str, list[str]] = {
    # Qualcomm Snapdragon
    "sm8750": ["kalama", "snapdragon 8 gen 4", "snapdragon 8 elite"],
    "sm8735": ["sunny", "snapdragon 8s gen 3"],
    "sm8650": ["pineapple", "snapdragon 8 gen 3"],
    "sm8635": ["crow", "snapdragon 8s gen 2"],
    "sm8550": ["kalama", "snapdragon 8 gen 2"],
    "sm8475": ["cape", "snapdragon 8+ gen 1"],
    "sm8450": ["taro", "waipio", "snapdragon 8 gen 1"],
    "sm8350": ["lahaina", "snapdragon 888"],
    "sm8250": ["kona", "snapdragon 865"],
    "sm8150": ["msmnile", "snapdragon 855"],
    "sm7250": ["lito", "snapdragon 765"],
    "sm7150": ["sm6150", "snapdragon 730"],
    "sdm865": ["kona", "snapdragon 860"],
    "sdm855": ["msmnile", "snapdragon 855"],
    "sdm845": ["sdm850", "snapdragon 845"],
    "sdm835": ["msm8998", "snapdragon 835"],
    "sdm820": ["msm8996", "snapdragon 820"],
    # MediaTek Dimensity
    "mt6989": ["dimensity 9300"],
    "mt6985": ["dimensity 9200"],
    "mt6983": ["dimensity 9000"],
    "mt6895": ["dimensity 8100"],
    "mt6879": ["dimensity 1300"],
    "mt6877": ["dimensity 1200"],
    "mt6873": ["dimensity 1000"],
    "mt6785": ["helio g90"],
    "mt6779": ["helio p90"],
    "mt6768": ["helio p70"],
    # Samsung Exynos
    "exynos 2200": ["exynos2200"],
    "exynos 2100": ["exynos2100"],
    "exynos 990": ["exynos990"],
    "exynos 9825": ["exynos9825"],
    "exynos 9820": ["exynos9820"],
    "exynos 9810": ["exynos9810"],
    # Apple Silicon
    "t8103": ["apl1102", "apple m1", "apple a14"],
    "t8112": ["apl1103", "apple m1 pro"],
    "t8116": ["apl1104", "apple m1 max"],
    "t6000": ["apl1109", "apple m2"],
    "t8130": ["apl1201", "apple a17 pro"],
    "t8120": ["apl1110", "apple a16 bionic"],
    "t8310": ["apl1w15", "apple a15 bionic"],
    # Rockchip
    "rk3588": ["rk3588s"],
    "rk3399": ["rk3399pro"],
    # HiSilicon Kirin
    "kirin 9000": ["kirin9000"],
    "kirin 990": ["kirin990"],
    "kirin 980": ["kirin980"],
    "kirin 970": ["kirin970"],
    "kirin 960": ["kirin960"],
    # Google Tensor
    "gs201": ["tensor g2", "cloudripper"],
    "gs101": ["tensor g1", "whitechapel"],
    "gs301": ["tensor g3", "zuma"],
    "gs501": ["tensor g4", "zumapro"],
}

# Preserved set of well-known codename-to-model aliases derived from
# VENDOR_KNOWLEDGE process_map / gpu_map keys and common marketing names.
PRESERVED_ALIASES: set[str] = {
    "kalama", "pineapple", "taro", "waipio", "lahaina", "kona", "msmnile",
    "lito", "sm6150", "cape", "crow", "sunny",
    "cloudripper", "whitechapel", "zuma", "zumapro",
    "dimensity 9000", "dimensity 9200", "dimensity 9300",
    "helio g90", "helio p90",
    "apple m1", "apple m2", "apple a17 pro", "apple a16 bionic", "apple a15 bionic",
    "exynos2200", "exynos990",
    "rk3588s", "rk3399pro",
    "kirin9000", "kirin990", "kirin980", "kirin970",
}


# ---------------------------------------------------------------------------
# DedupEngine
# ---------------------------------------------------------------------------

class DedupEngine:
    """Multi-strategy chip matcher and canonical identity generator.

    Attributes:
        alias_registry: Dict mapping normalised model keys to alternative
            name lists.  Defaults to :data:`CHIP_ALIASES`.
        logger: Module-level logger instance.
    """

    def __init__(self, alias_registry: dict[str, list[str]] | None = None) -> None:
        self.alias_registry = alias_registry or CHIP_ALIASES
        self.logger = logging.getLogger("soc_db.dedup")

    # ── public helpers ───────────────────────────────────────────────────

    def canonical_id(self, vendor: str, model: str, name: str = "") -> str:
        """Return a deterministic canonical ID for (vendor, model).

        If *model* is non-empty and contains alphanumeric characters, returns
        a UUID5 hex string.  Otherwise falls back to :func:`slug(name, model)`
        for backward compatibility.

        Args:
            vendor: Manufacturer name.
            model:  Model number.
            name:   Marketing name (used as fallback when model is empty).

        Returns:
            32-character hex UUID (no hyphens), or a slug if model is empty.
        """
        if model and bool(re.search(r"[a-zA-Z0-9]", model)):
            return chip_uuid(vendor, model)
        from soc_db.common import slug as _slug  # noqa: PLC0415

        return _slug(name, model)

    def match(
        self, chip: dict[str, Any], existing: dict[str, dict[str, Any]]
    ) -> tuple[str | None, str]:
        """Match a chip dict against existing records using all strategies.

        Strategies are tried in this order and return on first match:

        1. **exact_model** — case-insensitive model comparison.
        2. **alias** — normalised model lookup in alias registry.
        3. **regex** — ``extract_model()`` from ``common.py``.
        4. **wikidata_qid** — shared Wikidata QID.
        5. **fuzzy** — ``rapidfuzz.fuzz.token_sort_ratio >= 85``,
           vendor must match exactly.

        Args:
            chip:     The new chip record to match.
            existing: Mapping of existing chip IDs to their records.

        Returns:
            A ``(matched_id, strategy_name)`` tuple.  If no strategy
            produces a match, returns ``(None, "no_match")``.
        """
        if not existing:
            return None, "no_match"

        chip_model = (chip.get("model") or "").strip().upper()
        chip_name = (chip.get("name") or "").strip()
        chip_vendor = (chip.get("vendor") or "").strip()
        chip_wikidata = (chip.get("wikidata_id") or "").strip()

        # --- Strategy 1: exact_model ---
        if chip_model:
            for eid, ec in existing.items():
                ec_model = (ec.get("model") or "").strip().upper()
                if ec_model and ec_model == chip_model:
                    return eid, "exact_model"

        # local helper for remaining strategies
        def _iter_existing() -> list[tuple[str, dict[str, Any]]]:
            return sorted(existing.items(), key=lambda x: x[0])

        # --- Strategy 2: alias_registry ---
        if chip_model:
            normalized = self._normalize_model(chip_model)
            if normalized in self.alias_registry:
                aliases = [a.lower() for a in self.alias_registry[normalized]]
                for eid, ec in _iter_existing():
                    ec_name = (ec.get("name") or "").lower().strip()
                    ec_model = (ec.get("model") or "").lower().strip()
                    for alias in aliases:
                        if alias == ec_name or alias == ec_model or alias in ec_name or ec_name in alias:
                            return eid, "alias"

        # --- Strategy 3: vendor_model_regex ---
        from soc_db.common import extract_model as _extract_model  # noqa: PLC0415

        combined = f"{chip_name} {chip_model}".strip()
        extracted = _extract_model(combined)
        if extracted:
            for eid, ec in _iter_existing():
                ec_model = (ec.get("model") or "").strip().upper()
                if ec_model and ec_model == extracted:
                    return eid, "regex"

        # --- Strategy 4: wikidata_qid ---
        if chip_wikidata:
            for eid, ec in _iter_existing():
                ec_wd = (ec.get("wikidata_id") or "").strip()
                if ec_wd and ec_wd == chip_wikidata:
                    return eid, "wikidata_qid"

        # --- Strategy 5: fuzzy_name ---
        if chip_name and chip_vendor:
            try:
                from rapidfuzz import fuzz as _fuzz  # noqa: PLC0415
            except ImportError:
                self.logger.warning("rapidfuzz not available — skipping fuzzy strategy")
                return None, "no_match"

            best_id: str | None = None
            best_score = 0
            for eid, ec in _iter_existing():
                ec_name = (ec.get("name") or "").strip()
                ec_vendor = (ec.get("vendor") or "").strip()
                if not ec_name or ec_vendor.lower() != chip_vendor.lower():
                    continue
                score = _fuzz.token_sort_ratio(chip_name, ec_name)
                if score >= 85 and score > best_score:
                    best_score = score
                    best_id = eid

            if best_id is not None:
                return best_id, "fuzzy"

        # --- Fallback: name match (preserves old _match_existing behavior) ---
        if chip_name:
            chip_name_lower = chip_name.lower()
            for eid, ec in _iter_existing():
                ec_name = (ec.get("name") or "").lower().strip()
                if ec_name and ec_name == chip_name_lower:
                    return eid, "name"

        return None, "no_match"

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize_model(model: str) -> str:
        """Normalise a model string for alias lookup.

        Lowercases, strips whitespace, and removes non-alphanumeric
        characters except hyphens and spaces.
        """
        return re.sub(r"[^a-z0-9 \-]", "", model.lower().strip())

    # ── batch operations ─────────────────────────────────────────────────

    def batch_match(
        self, chips: list[dict[str, Any]], existing: dict[str, dict[str, Any]]
    ) -> dict[str, tuple[str | None, str]]:
        """Run :meth:`match` for every chip in *chips*.

        Returns:
            Dict mapping each chip's ``id`` to its ``(match_id, strategy)``.
        """
        return {c.get("id", ""): self.match(c, existing) for c in chips}

    def deduplicate(
        self, chips: list[dict[str, Any]], existing: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return chips that had no match, annotating the strategy used.

        Each returned chip dict gets a ``_dedup_strategy`` key.

        Returns:
            List of chip dicts that are either new (no match) or existing
            records that should be updated (strategy != ``"no_match"``).
        """
        result: list[dict[str, Any]] = []
        for c in chips:
            match_id, strategy = self.match(c, existing)
            c["_dedup_strategy"] = strategy
            if match_id is None:
                result.append(c)
            elif strategy != "no_match":
                result.append(c)
        return result
