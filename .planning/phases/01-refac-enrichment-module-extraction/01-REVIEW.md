---
phase: 01-refac-enrichment-module-extraction
reviewed: 2026-07-19T12:00:00Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - src/soc_db/enrich/__init__.py
  - src/soc_db/enrich/_vendor_data.py
  - src/soc_db/enrich/_helpers.py
  - src/soc_db/enrich/year.py
  - src/soc_db/enrich/gpu.py
  - src/soc_db/enrich/process.py
  - src/soc_db/enrich/memory.py
  - src/soc_db/enrich/modem.py
  - src/soc_db/enrich/npu.py
  - src/soc_db/enrich/connectivity.py
  - src/soc_db/enrich/storage.py
  - src/soc_db/enrich/aliases.py
  - src/soc_db/enrich/scoring.py
  - src/soc_db/enrich/cpu.py
  - src/soc_db/common.py
  - tests/snapshot/test_enrich_snapshot.py
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 1: Code Review Report — Enrichment Module Extraction

**Reviewed:** 2026-07-19T12:00:00Z
**Depth:** deep
**Files Reviewed:** 16
**Status:** issues_found

## Summary

This phase extracted per-domain enrichment logic from `common.py` into 14 modules under `src/soc_db/enrich/`, added a snapshot regression test, and preserved the existing enrichment pipeline as a re-export shim. The extraction is clean and the snapshot test provides an excellent regression safety net.

**Key concerns:**
1. `__all__` in `enrich/__init__.py` advertises `enrich_one` and `enrich_all` which are NOT importable from the package — `from soc_db.enrich import *` will raise `AttributeError`. This is a NEW bug introduced in this commit.
2. The Qualcomm WEAR year-inference formula (pattern 23 in `year.py`) computes a value that is immediately overwritten by `year = 2020` — a pre-existing bug that was carried over verbatim during extraction.
3. Pattern 16 (Intel x/zn prefix) in `year.py` lacks a `break` statement, allowing later patterns to override its year assignment — violating the documented priority chain.
4. Several `or` conditions in year-inference thresholds contain dead-code branches that make the logic misleading.
5. The snapshot test's first-run "capture mode" (`test_enrich_snapshot_matches()` when reference is missing) exits without any assertion — could silently hide errors during the initial capture.

Extraction fidelity is verified by the snapshot test (all 1746 chips match the pre-refactor reference). All pre-existing bugs listed below were carried over verbatim and represent shared risk with the original codebase rather than extraction defects.

---

## Critical Issues

### CR-01: `__all__` contains dangling names `enrich_one` and `enrich_all` that are NOT importable from the package

**File:** `src/soc_db/enrich/__init__.py:31-32`
**Introduced in this commit:** YES

**Issue:** Lines 31-32 of `__all__` include `"enrich_one"` and `"enrich_all"`, but these names are neither defined nor imported anywhere in `__init__.py`. They exist only in `soc_db.common`, which is not imported here.

This causes `from soc_db.enrich import *` to raise `AttributeError`:
```
AttributeError: module 'soc_db.enrich' has no attribute 'enrich_one'
```

Furthermore, `from soc_db.enrich import enrich_one` (explicit import) also fails with `ImportError` because the name simply isn't in the package namespace.

Cannot trivially add `from soc_db.common import enrich_one, enrich_all` to `__init__.py` because `common.py` itself imports from `soc_db.enrich.*` submodules, creating a circular import: `soc_db.enrich` → `soc_db.common` → `soc_db.enrich._helpers` → (via `__init__`) → `soc_db.common` again. This would raise `ImportError` because `enrich_one` isn't yet defined in `common.py` at the time of the cross-import.

**Fix:** Remove `"enrich_one"` and `"enrich_all"` from `__all__` in `__init__.py`. Users must import these from `soc_db.common` (the designated re-export shim), which already works correctly.

```python
# In src/soc_db/enrich/__init__.py, remove lines 31-32:
__all__ = [
    "VENDOR_KNOWLEDGE",
    "FIELD_GROUPS",
    "FIELD_WEIGHTS",
    "MEMORY_CLOCK_FROM_TYPE",
    "VENDOR_FILES",
    "_has",
    "clean",
    # "enrich_one",       # REMOVE — not importable from this package
    # "enrich_all",        # REMOVE — not importable from this package
    "infer_year",
    # ... rest of names that ARE available
]
```

---

### CR-02: Qualcomm WEAR year formula computed then immediately discarded (year always 2020)

**File:** `src/soc_db/enrich/year.py:433-434`
**Introduced in this commit:** NO (pre-existing, carried over verbatim)

**Issue:** Pattern 23 (Qualcomm WEAR) computes a year formula on line 433, then unconditionally overwrites it with `year = 2020` on line 434. The formula is dead code.

```python
# Line 433 — COMPUTED but never used:
year = 2016 + (wear - 2100) // 500 if wear >= 2100 else 2018 + (wear - 2500) // 500
# Line 434 — OVERWRITES the computed value unconditionally:
year = 2020
```

All Qualcomm WEAR chips will have their year inferred as 2020, regardless of the wear model number. This is a data correctness bug for any chip matching this pattern that should have had a different year.

The snapshot test does not catch this because the bug existed in the pre-refactor `common.py` and was carried over verbatim. The reference snapshot contains the same incorrect 2020 values.

**Fix:** Remove the dead formula on line 433. If the formula IS the intended logic, remove line 434. Determine the correct behavior from the original intent:

```python
# 23. Qualcomm WEAR
m = re.search(r"WEAR\s*(\d+)", f_text)
if m:
    wear = int(m.group(1))
    # If formula is correct:
    year = 2016 + (wear - 2100) // 500 if wear >= 2100 else 2018 + (wear - 2500) // 500
    # OR if year=2020 is correct:
    # year = 2020
    break
```

---

## Warnings

### WR-01: Pattern 16 (Intel x/zn prefix) missing `break` after year assignment — violates priority chain

**File:** `src/soc_db/enrich/year.py:363-368`
**Introduced in this commit:** NO (pre-existing)

**Issue:** Pattern 16 (Intel x/zn prefix) sets `year` to 2015 or 2014 but does NOT have a `break` statement. The loop continues to patterns 17–43, which can override the year if they also match. This violates the documented priority ordering which declares pattern 16 higher than patterns 17+.

```python
# Pattern 16 (lines 363-368):
m = re.search(r"\b[xzzn]\d+", f_text, re.IGNORECASE)
if m:
    if re.search(r"[xX]\d", f_text):
        year = 2015
    elif re.search(r"[Zz]\d{4}", f_text):
        year = 2014
# ← MISSING: break
```

The fallback `if year: break` at line 639 only fires after all 27 subsequent patterns have executed. If any later pattern ALSO matches the chip, it silently overrides pattern 16's year.

**Fix:** Add `break` after the `elif` block in pattern 16:

```python
m = re.search(r"\b[xzzn]\d+", f_text, re.IGNORECASE)
if m:
    if re.search(r"[xX]\d", f_text):
        year = 2015
    elif re.search(r"[Zz]\d{4}", f_text):
        year = 2014
    break  # ← Add this
```

---

### WR-02: Redundant dead-code `or` conditions in year-inference thresholds

**Files:**
- `src/soc_db/enrich/year.py:109,111,113,117,119,121-122,123,158,160,162,424,571`

**Introduced in this commit:** NO (pre-existing)

**Issue:** Multiple `elif` conditions use `A or B` where `A` logically implies `B`, making `B` dead code. This makes the code confusing and suggests the original developer may have intended separate thresholds with different year values.

Examples:
```python
# Line 109: d >= 9300 already implies d >= 9200
elif d >= 9300 or d >= 9200:
    year = 2024

# Line 117: d >= 8100 already implies d >= 8000
elif d >= 8100 or d >= 8000:
    year = 2022

# Line 158: kirin >= 950 already implies kirin >= 930
elif kirin >= 950 or kirin >= 930:
    year = 2015

# Line 424-425: sa >= 8195 already implies sa >= 8155
elif sa >= 8195 or sa >= 8155 or sa >= 6155:
    year = 2019

# Line 571: komp >= 1300 already implies komp >= 1200, komp >= 800
if komp >= 1300 or komp >= 1200 or komp >= 800:
    year = 2022
```

**Fix:** Simplify conditions to use only the broader threshold, or document why two ranges with the same year appear separate (e.g., if the intent is to document known model numbers):

```python
# Example fix for line 109:
elif d >= 9200:
    year = 2024
```

---

### WR-03: Snapdragon X24 modem incorrectly labeled as "5G"

**File:** `src/soc_db/enrich/modem.py:48`
**Introduced in this commit:** NO (pre-existing)

**Issue:** The Qualcomm X24 modem (matching `sm_num >= 8000`) is labeled as "Snapdragon X24 5G", but the Snapdragon X24 is a 4G LTE Category 20 modem (up to 2 Gbps downlink, but 4G-only, no 5G). It was introduced in the Snapdragon 850/8cx platform for PCs.

```python
modem_map = {8750: "X80", 8650: "X75", 8550: "X70", 8450: "X65", 8350: "X60", 8250: "X55", 8150: "X50", 8000: "X24"}
...
chip["modem"] = f"Snapdragon {modem_name} 5G"
```

This produces incorrect modem branding for SM/SDM8000-series chips (e.g., Snapdragon 850 = SDM850 with X24 would get "Snapdragon X24 5G" instead of "Snapdragon X24 LTE").

**Fix:** Either use different modem name templates for 4G vs 5G modems, or special-case the X24:

```python
if sm_num >= 8150:
    chip["modem"] = f"Snapdragon {modem_name} 5G"
elif sm_num >= 8000:
    chip["modem"] = f"Snapdragon {modem_name} LTE"
```

---

### WR-04: Snapshot test first-run capture mode has no assertions — silent failure risk

**File:** `tests/snapshot/test_enrich_snapshot.py:33-42`
**Introduced in this commit:** YES (new test file)

**Issue:** When the reference file does not exist, `test_enrich_snapshot_matches()` writes the reference and returns without any assertions. If the enrichment pipeline crashes during capture (uncaught exception), pytest would catch it. But if the pipeline silently produces wrong output (e.g., all chips get year=None), the test passes, the broken reference is committed, and all subsequent runs compare against a corrupted baseline.

```python
if not REFERENCE_FILE.exists():
    # First run — write reference file and pass
    enriched = [enrich_one(c) for c in chips]
    enriched.sort(key=lambda c: (c.get("vendor", ""), c.get("id", "")))
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_FILE.write_text(...)
    return  # ← No assertion!
```

**Fix:** Add basic sanity checks before writing the reference:

```python
if not REFERENCE_FILE.exists():
    enriched = [enrich_one(c) for c in chips]
    enriched.sort(key=lambda c: (c.get("vendor", ""), c.get("id", "")))
    # Sanity checks
    assert len(enriched) > 1000, f"Too few chips: {len(enriched)}"
    assert all(c.get("vendor") for c in enriched), "Some chips missing vendor"
    assert all(c.get("year") for c in enriched), "Some chips missing year"
    PHASE_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_FILE.write_text(...)
    return
```

---

### WR-05: Hardcoded "updated" date in scoring module

**File:** `src/soc_db/enrich/scoring.py:35`
**Introduced in this commit:** NO (pre-existing)

**Issue:** `compute_completeness()` unconditionally sets `chip["updated"] = "2026-06-21"`. This means:
1. All enriched chips show the same "last updated" date
2. The date is hardcoded and will become increasingly stale
3. Re-enriching existing chips (via `write_vendor_file()`) resets their `updated` field even if nothing changed

```python
chip["updated"] = "2026-06-21"
```

**Fix:** Either make this dynamic (today's date) or preserve the existing `updated` date if already set:

```python
if not chip.get("updated"):
    from datetime import date
    chip["updated"] = date.today().isoformat()
```

---

### WR-06: Duplicate Wi-Fi 7 year threshold — dead entry

**File:** `src/soc_db/enrich/connectivity.py:27-28`
**Introduced in this commit:** NO (pre-existing)

**Issue:** The Wi-Fi year table has two entries mapping to "Wi-Fi 7":
```python
(2025, "Wi-Fi 7"),  # line 27 — ALWAYS shadowed by line 28
(2023, "Wi-Fi 7"),  # line 28 — wins for all years >= 2023
```

The `(2025, "Wi-Fi 7")` entry is unreachable because `(2023, "Wi-Fi 7")` matches first for any year >= 2023. This may confuse future maintainers who update the table.

**Fix:** Keep only one entry, or add an "8" placeholder for the future:
```python
(2023, "Wi-Fi 7"),
```

---

## Info

### IN-01: `enrich_one()` compiles regex inside the function body on every call

**File:** `src/soc_db/common.py:339`
**Introduced in this commit:** NO (pre-existing)

**Issue:** The `ann` regex is compiled fresh every time `enrich_one()` is called (once per chip, ~1746 times). It's a simple pattern, so the performance impact is negligible, but it's good practice to hoist to module level:

```python
# Move to module level:
_CLEANUP_RE = re.compile(r"\s*\(now\s+[^)]*?\)")

def enrich_one(chip):
    for k in ("name", "model"):
        if chip.get(k):
            cleaned = _CLEANUP_RE.sub("", chip[k]).strip()
            ...
```

---

### IN-02: Nvidia GPU defaults to generic string "Nvidia GPU"

**File:** `src/soc_db/enrich/gpu.py:48`
**Introduced in this commit:** NO (pre-existing)

**Issue:** Vendor default for Nvidia chips sets `chip["gpu"] = "Nvidia GPU"` which is not informative. Nvidia SoCs like Tegra X1 used Maxwell architecture GPU, later models used newer architectures.

```python
"Nvidia": "Nvidia GPU",
```

---

### IN-03: `npu.py` uses `chip["year"]` direct access instead of local `yr` variable

**File:** `src/soc_db/enrich/npu.py:37`
**Introduced in this commit:** NO (pre-existing)

**Issue:** Most of the function uses the local `yr` variable, but one branch accesses `chip["year"]` directly. This is inconsistent and risks a `KeyError` if `year` happened to not be set (though the guard at line 30 prevents this in practice):

```python
if vendor == "Apple" and chip["year"] >= 2017:  # Uses chip["year"] instead of yr
```

---

### IN-04: `gpu.py:47` — Rockchip default line exceeds 160-char limit

**File:** `src/soc_db/enrich/gpu.py:47`
**Introduced in this commit:** NO (pre-existing)

**Issue:** The Rockchip vendor default line is very long (exceeds the project's 160-character ruff line length):

```python
"Rockchip": "Mali-400 MP" if yr < 2014 else "Mali-T760 MP4" if yr < 2017 else "Mali-G52 MP2",
```

Consider splitting for readability:

```python
"Rockchip": (
    "Mali-400 MP" if yr < 2014
    else "Mali-T760 MP4" if yr < 2017
    else "Mali-G52 MP2"
),
```

---

### IN-05: `_helpers.py` `_has()` considers `0` and `0.0` as empty

**File:** `src/soc_db/enrich/_helpers.py:27`
**Introduced in this commit:** NO (pre-existing)

**Issue:** `_has()` returns `False` for numeric zero values, treating them as "not present". This is intentional for fields like `cores` or `process_nm` where 0 is invalid, but could be surprising for legitimate zero values in the future (e.g., TDP of 0W for ultra-low-power designs). The logic is inherited from the original code, but the assumption should be documented.

---

## Structural Findings (fallow)

No structural pre-pass was provided for this review. All findings above are from direct code review.

---

## Import / Module Boundary Audit

- **Circular imports:** None. The import graph is a DAG:
  `common.py` → `soc_db.enrich.*` (all submodules)
  `soc_db.enrich.*` → `soc_db.enrich._vendor_data`, `soc_db.enrich._helpers` (internal only)
  No module in `enrich/` imports from `common.py`.
- **Missing re-exports:** `__init__.py` advertises `enrich_one`/`enrich_all` in `__all__` but does not import them (see CR-01).
- **Backward compatibility:** All pre-existing `from soc_db.common import ...` paths are preserved via re-exports.
- **`TYPE_CHECKING` guards:** Not needed — no type-only cross-imports between enrich modules and `common.py`.

---

_Reviewed: 2026-07-19T12:00:00Z_
_Reviewer: gsd-code-reviewer (deep)_
_Depth: deep_
