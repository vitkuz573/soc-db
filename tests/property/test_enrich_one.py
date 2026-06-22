"""Property-based tests for enrich_one using Hypothesis."""

from hypothesis import given, settings
from hypothesis import strategies as st

from soc_db.common import VENDOR_KNOWLEDGE, enrich_one


@st.composite
def chip_dict(draw):
    chip = {
        "id": draw(st.text(min_size=1, max_size=20)),
        "name": draw(st.text(min_size=1, max_size=20)),
        "vendor": draw(st.sampled_from(list(VENDOR_KNOWLEDGE.keys()) + ["Unknown", ""])),
    }
    if draw(st.booleans()):
        chip["model"] = draw(st.text(min_size=0, max_size=20))
    if draw(st.booleans()):
        chip["year"] = draw(st.integers(min_value=2003, max_value=2026) | st.none())
    if draw(st.booleans()):
        chip["year_guess"] = draw(st.booleans())
    return chip


class TestEnrichOneProperties:
    @settings(max_examples=100)
    @given(chip_dict())
    def test_always_has_input_keys(self, chip):
        result = enrich_one(chip)
        for key in ("id", "name", "vendor"):
            assert key in result

    @settings(max_examples=100)
    @given(chip_dict())
    def test_preserves_valid_year(self, chip):
        result = enrich_one(chip)
        y = chip.get("year")
        if y is not None and 2003 <= y <= 2026:
            assert result.get("year") == y

    @settings(max_examples=100)
    @given(chip_dict())
    def test_architecture_from_vendor_knowledge(self, chip):
        result = enrich_one(chip)
        if chip.get("vendor") in VENDOR_KNOWLEDGE:
            assert "architecture" in result

    @settings(max_examples=100)
    @given(chip_dict())
    def test_memory_type_is_lpddr5_or_newer(self, chip):
        result = enrich_one(chip)
        yr = result.get("year")
        mem = result.get("memory_type")
        if yr is not None and yr >= 2021 and mem is not None:
            assert any(mem.startswith(p) for p in ("LPDDR5", "LPDDR6"))

    @settings(max_examples=100)
    @given(chip_dict())
    def test_no_exceptions(self, chip):
        enrich_one(chip)
