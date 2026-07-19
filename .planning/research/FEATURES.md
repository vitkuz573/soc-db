# Feature Landscape

**Domain:** Large-scale SoC/CPU database — full market coverage (5000+ chips)
**Milestone:** v3.0 Full SoC Coverage
**Researched:** 2026-07-19
**Confidence:** HIGH (cross-verified from live source inspection)

---

## Executive Summary

soc-db v2.1 ships 1761 chips across 43 vendors, but average completeness ranges from 0.19 to 0.54. Many vendors have only 1–2 placeholder entries. The v3.0 milestone targets **5000+ SoCs** with **95-field depth (completeness ≥0.80)** — matching or exceeding the data depth of commercial aggregators like TechPowerUp (4398 CPUs), GSMArena (10000+ phones), NotebookCheck (thousands of benchmarked processors), and DeviceSpecifications. The research confirms that no single source provides all 95 fields; achieving full depth requires **merging across 6+ data source types** (vendor official, Wikipedia, benchmark sites, spec aggregators, Linux kernel, and community sources) with deduplication and cross-validation.

---

## Table Stakes

Features users expect from a large-scale chip database. Missing these = product feels incomplete for v3.0.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **`≥5000` SoC entries across all major vendors** | Commercial databases (TechPowerUp: 4398 CPUs, GSMArena: 10000+ phones with chipsets) set the expectation. Current 1761 is ~40% of target. | **High** | Must cover Qualcomm (800+), MediaTek (600+), Samsung Exynos (200+), Apple (80+), HiSilicon (100+), Unisoc (200+), Intel (500+), AMD (400+), plus IoT/embedded (Rockchip, Allwinner, Amlogic, etc.) |
| **95-field depth with completeness ≥0.80** | Existing databases hit 15–40 fields per chip. Users expect CPU cores, GPU, modem, NPU, memory, connectivity, benchmarks, etc. Current avg completeness is 0.19–0.54. | **High** | Requires multi-source merging. No single source provides all 95 fields. 65 fields are currently tracked for scoring; need to add ~30 more. |
| **Per-chip data source tracking** | Users need to know where each field value came from (vendor official vs Wikipedia vs benchmark site) to assess trust. | **Medium** | Existing `sources: dict[str, str]` field maps field→source. Needs expansion to track per-value granularity. |
| **Vendor-official data as highest-priority source** | Vendor specs (Qualcomm Developer Network, MediaTek product pages, Apple Tech Specs) are the most authoritative. Need dedicated scrapers. | **Medium** | Each vendor site is different. No standardized format. Requires per-vendor scraping logic with fallback to Wikipedia/aggregators. |
| **Deduplicated chip entries** | Same chip listed under different names/codenames across vendors and sources. Users expect one canonical entry with aliases. | **Medium** | Existing `aliases` field exists. Need matching/merging logic: same chip detected in Wikipedia + TechPowerUp + GSMArena → merge fields, mark sources. |
| **Cross-source validation** | If Wikipedia reports 3nm but vendor says 4nm, users need to know the discrepancy. | **Medium** | Existing enrichment pipeline can be extended with conflict detection scoring. |
| **Regular refresh of data from sources** | Chips are announced weekly. A static database goes stale. | **High** | Need automated pipeline that scrapes new chips from vendor sites + Wikipedia + benchmarks on schedule. Current weekly CI refresh is minimal. |
| **Search/filter by any chip attribute** | Users want "all 4nm chips with NPU > 40 TOPS" not just vendor name. | **Low** | FTS5 already exists. Need extended query capabilities for numeric range filters. |
| **Benchmark data integration** | Geekbench, AnTuTu scores are the #1 requested enrichment for chip comparison. NotebookCheck and browser.geekbench.com have thousands of benchmarked chips. | **Medium** | Existing `Benchmarks` model (antutu_v10, geekbench_5/6) is ready. Need scrapers for Geekbench Browser and AnTuTu ranking lists. NotebookCheck benchmark table is also scrapable. |
| **CLI with advanced filtering** | Power users want `soc-db list --process 4nm --npu-min 20 --vendor Qualcomm` | **Low** | CLI already extensible. Need to add more filter flags matching new fields. |
| **REST API with comparison endpoint** | `GET /v1/chips/{id}/compare?with=id2,id3` for side-by-side spec comparison | **Low** | API already has chips endpoint. Comparison is a new aggregation endpoint. |
| **Data quality dashboards** | Automated reports showing per-vendor completeness, field coverage, source freshness, conflict detection. | **Medium** | Scheduled CI job that generates quality metrics. Existing stats command can be extended. |

---

## Differentiators

Features that set soc-db apart from other chip databases. Not strictly expected, but provide unique value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Per-field source tracking with conflict scoring** | Every value knows where it came from. When sources disagree, a confidence score is computed. No other database does this. | **High** | Existing `sources` field needs extension. Conflict scoring can use: source freshness × source authority × number of agreeing sources. |
| **Unified chip categorization across mobile/desktop/server/embedded/IoT** | Most databases specialize (TechPowerUp = desktop/notebook CPUs, GSMArena = phone chipsets). soc-db spans all categories. | **Medium** | Current tags field already flexible. Need to add chip market category as a first-class enum. |
| **Automated vendor page generation** | `/v1/vendors/{vendor}` pages with chip comparison tables, completeness heatmaps, and trend charts. | **Medium** | Existing vendor endpoint provides raw counts. Extended vendor pages with aggregation. |
| **Chip lifecycle tracking** | Announced → Sampling → Production → End-of-life. Know which chips are current vs obsolete. | **Medium** | Existing `status` field exists with `"unknown"` default. Need to populate from vendor lifecycle sources. |
| **Benchmark trend analysis** | "How does Snapdragon 8 Gen series compare across generations?" | **Medium** | Aggregated benchmark data per chip series. Geekbench Browser has historical data. |
| **Linux Device Tree and BSP data** | Kernel upstream device trees encode compatible strings, clock rates, and power domains. Automated extraction provides deep hardware data. | **High** | Existing Linux DeviceTree scraper exists. Needs expansion to cover more SoC families. |
| **Open Data export** | Full database export in JSON, CSV, Parquet. Academic/research use. | **Low** | Existing `GET /v1/export/{fmt}` endpoint. Needs expansion for new fields. |
| **Community contribution pipeline** | Users submit corrections via PRs to JSON files, CI validates and merges. | **Medium** | Current data files in git enable this. Need clearer contribution docs and validation in CI. |

---

## Anti-Features

Features to explicitly NOT build in v3.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Full-text SoC description synthesis** | Writing Markdown descriptions for 5000+ chips is expensive and LLM-generated text can hallucinate. | Focus on structured field data. Keep `description` as optional wiki-sourced. |
| **Real-time chip announcement monitoring** | Tracking press releases from 40+ vendors requires a dedicated team. Too expensive for v3.0. | Weekly CI refresh from Wikipedia + benchmark sources. Monthly vendor site deep scrape. |
| **Device ↔ SoC cross-reference database** | Linking each chip to every phone/tablet/laptop that uses it is 50000+ relationships. | Deferred to v3.1. Current `devices: list[str]` per chip is sufficient for v3.0. |
| **Competitive analysis ("X is 15% faster than Y")** | Performance claims require careful benchmarking methodology. Auto-generated comparisons mislead. | Let users compare raw specs and benchmarks. Don't auto-draw performance conclusions. |
| **Chip photography / die shots** | Capturing and organizing die shots requires image hosting, moderation, and licensing review. | Link to TechPowerUp's existing die shot collection. Don't host our own. |
| **SoC power/efficiency curve modeling** | Power modeling requires per-workload data not available from public specs. | Focus on TDP/clock data from spec sheets. Power efficiency is a v4.0+ topic. |
| **Blocking vendor sites with aggressive scraping** | Some vendor sites block scrapers. Risk of IP ban. | Respect robots.txt, use polite delays (2-5s), cache aggressively, and document which sites require manual data entry. |

---

## Data Source Landscape

### Source Authority Hierarchy

```
TIER 1 — Official vendor sources (authoritative, structured, but require crawling)
├── Qualcomm Developer Network (developer.qualcomm.com)
│   └── Snapdragon product pages: CPU, GPU, DSP, modem, NPU specs
├── MediaTek product pages (mediatek.com/products)
│   └── Dimensity/Helio/Kompanio/Pentonic chip detail pages
├── Apple Tech Specs (support.apple.com/specs)
│   └── M-series and A-series processor specifications
├── Samsung Semiconductor (semiconductor.samsung.com)
│   └── Exynos product pages
├── Intel ARK (ark.intel.com)
│   └── Full processor database, lifecycle status, pricing
└── AMD product pages (amd.com)
    └── Ryzen/EPYC/Instinct specifications

TIER 2 — Aggregator/reference sources (broad coverage, structured, community maintained)
├── TechPowerUp CPU Database (4398 CPUs)
│   └── CPU/mobile SoC spec pages — excellent for desktop/server/mobile coverage
├── GSMArena (phone database)
│   └── Chipset field in every phone page — good for mobile SoC→device mapping
├── DeviceSpecifications
│   └── Per-chip specs with CPU, GPU, RAM, display → SoC usage
├── NotebookCheck Benchmarks
│   └── 20+ benchmark scores per processor, TDP, L2/L3 cache, NPU TOPS
├── Wikipedia infobox tables
│   └── Lists of Qualcomm, MediaTek, Samsung, HiSilicon, Intel, AMD processors
├── Geekbench Browser (browser.geekbench.com)
│   └── Single/multi-core scores per chip, device-specific
├── AnTuTu Benchmark rankings
│   └── Mobile SoC performance rankings, GPU/sub-scores
└── Linux DeviceTree (kernel.org)
    └── Compatible strings, clocks, power domains — deep hardware data

TIER 3 — Community/derived sources (inconsistent coverage, needs vetting)
├── Wikidata SPARQL
│   └── Structured property data, but inconsistent population
├── Phoronix benchmark data
│   └── Linux-specific benchmarks
├── User-submitted data via PRs
│   └── Crowd-sourced chip additions with manual review
└── Datsheet PDFs from manufacturers
    └── Richest data but unstructured extraction needed
```

### Field Coverage by Source

| Field Group | Wikipedia | TechPowerUp | GSMArena | NotebookCheck | DeviceSpecs | Vendor Official | Geekbench | Linux DT |
|-------------|-----------|-------------|----------|---------------|-------------|-----------------|-----------|----------|
| Identity (name, vendor, model) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Cores/threads | ✅ | ✅ | ~ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Clock speeds | ✅ | ✅ | ~ | ✅ | ~ | ✅ | ❌ | ✅ |
| Process node | ✅ | ✅ | ~ | ✅ | ~ | ✅ | ❌ | ❌ |
| Cache | ✅ | ✅ | ❌ | ✅ | ❌ | ~ | ❌ | ✅ |
| TDP/power | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ |
| GPU model/clock | ✅ | ✅ | ~ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Memory support | ✅ | ✅ | ~ | ❌ | ~ | ✅ | ❌ | ✅ |
| NPU / AI TOPS | ~ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ |
| Modem/cellular | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Video codecs | ✅ | ~ | ❌ | ❌ | ~ | ✅ | ❌ | ❌ |
| Display/camera | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Connectivity | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ |
| Benchmarks | ❌ | ❌ | ~ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Lifecycle status | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Pricing | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |

Legend: ✅ = consistently available, ~ = partially available, ❌ = not available

### Notable Observations

1. **No single source covers all 95 fields.** The maximum per-source coverage is ~45-50 fields (vendor official + Wikipedia).
2. **TechPowerUp has the best desktop/server CPU coverage** (4398 entries) but lacks modem/cellular, display, camera, and connectivity fields that mobile SoCs need.
3. **GSMArena and DeviceSpecifications provide mobile-focused fields** (chipset→display, camera, connectivity, battery) but lack deep SoC detail (cache, NPU TOPS, process node).
4. **NotebookCheck has the most benchmark depth** (~20 different benchmarks) but their dataset is laptop/desktop focused, with limited mobile-only SoCs.
5. **Wikipedia infobox tables are the broadest starting point** for all vendors but fields are inconsistently populated across tables.
6. **Vendor official sites** have the richest per-chip detail but require per-vendor crawling and often bury specs in interactive elements (JS-rendered comparisons).
7. **Geekbench Browser lacks a public API** but pages have structured JSON-LD that can be scraped (approx 1 req/s rate limiting).
8. **AnTuTu rankings change frequently** and are not well-structured — scraping is fragile but provides the only mobile GPU performance data.

---

## Target Vendor Coverage

### Phase 1 — Mobile SoC Vendors (core of v3.0)

| Vendor | Est. Chips | Current | Gap | Data Source Strategy |
|--------|-----------|---------|-----|---------------------|
| **Qualcomm** | 800+ | 431 | 369 | Snapdragon list on Wikipedia + TechPowerUp + QDN product pages (SM/WSC prefix series) for 2020-2026 models |
| **MediaTek** | 600+ | 292 | 308 | Wikipedia list + MediaTek product pages (Dimensity 9000+, Helio G series, Kompanio, Pentonic) |
| **Samsung Exynos** | 200+ | ~50 | 150 | Wikipedia Exynos page + Samsung Semiconductor site (Exynos 2400+, Auto, Wearable) |
| **Apple** | 80+ | 41 | 39 | Apple Tech Specs + Wikipedia (M3/M4/M5 series, A17/A18/A19, all S-series, W-series, H-series) |
| **HiSilicon** | 100+ | ~30 | 70 | Wikipedia Kirin + DeviceSpecifications (Kirin 9000s+, Ascend NPU) |
| **Unisoc** | 200+ | ~10 | 190 | Wikipedia Unisoc (Tiger, Shark, Tanggula series) + DeviceSpecifications |
| **Google Tensor** | 10+ | ~5 | 5 | Wikipedia Tensor + device teardowns (Tensor G4/G5/G6) |

### Phase 2 — Desktop/Server/Notebook CPU Vendors

| Vendor | Est. Chips | Current | Gap | Data Source Strategy |
|--------|-----------|---------|-----|---------------------|
| **Intel** | 1000+ | 289 (Atom only) | 700+ | ARK database + TechPowerUp (Core, Xeon, Pentium, Celeron, Core Ultra, Nova Lake) |
| **AMD** | 400+ | ~10 | 390 | AMD product pages + TechPowerUp (Ryzen 7000/8000/9000, EPYC, Threadripper, Ryzen AI) |

### Phase 3 — Embedded/IoT/Automotive SoC Vendors

| Vendor | Est. Chips | Current | Gap | Data Source Strategy |
|--------|-----------|---------|-----|---------------------|
| **Rockchip** | 100+ | ~20 | 80 | Wikipedia + Rockchip product pages (RK35xx, RV series) |
| **Allwinner** | 100+ | ~15 | 85 | Wikipedia + Linux-sunxi community |
| **Amlogic** | 80+ | ~10 | 70 | Wikipedia + LibreELEC/OARC community |
| **NXP i.MX** | 100+ | ~10 | 90 | NXP product pages + Linux DeviceTree |
| **TI OMAP/Sitara** | 80+ | ~10 | 70 | Wikipedia + TI product pages |
| **Nvidia Tegra/Orin** | 40+ | ~10 | 30 | Wikipedia + Nvidia dev pages + Jetson lineup |
| **Renesas R-Car** | 60+ | ~5 | 55 | Renesas product pages + automotive community |
| **Broadcom BCM** | 80+ | ~5 | 75 | Wikipedia + Raspberry Pi foundation + OpenWrt |
| **Marvell** | 40+ | ~2 | 38 | Wikipedia + Marvell product pages |
| **Microchip/SAMA5** | 60+ | ~3 | 57 | Microchip product pages + Linux AT91 |
| **STM STM32MP** | 40+ | ~5 | 35 | ST product pages + Linux ARM |
| **Realtek RTD** | 50+ | ~3 | 47 | TV box community + Linux media |
| **Ingenic** | 30+ | ~5 | 25 | Wikipedia + MIPS community |
| **Actions** | 30+ | ~3 | 27 | Wikipedia + low-end tablet community |

### Phase 4 — RISC-V / Emerging Architectures

| Vendor | Est. Chips | Current | Gap | Data Source Strategy |
|--------|-----------|---------|-----|---------------------|
| **Sophgo** | 20+ | ~3 | 17 | Sophgo product pages + RISC-V community |
| **StarFive** | 10+ | 0 | 10 | StarFive product pages + RISC-V |
| **T-Head/XuanTie** | 20+ | 0 | 20 | T-Head product pages + RISC-V |
| **Espressif ESP** | 20+ | 0 | 20 | Espressif product pages (ESP32-P4, ESP32-C5/C6) |

### Estimated Total: 5000–5500 chips

---

## Detailed Field Schema (95 Fields)

### Current 65 scored fields (existing):
```
identity(7):      id, name, vendor, model, aliases, codename, description
core(10):         architecture, isa, cores, threads, cluster_config,
                  clock_max, clock_mid, clock_min, max_freq, cache
process(4):       process_nm, process_name, process, tdp
gpu(4):           gpu, gpu_clock, gpu_api, gpu_tflops
memory(6):        memory_type, memory_max, memory_clock, memory_bus,
                  memory_bandwidth, storage_type
ai(2):            npu, ai_ops
modem(4):         modem, modem_dl, modem_ul, cellular
media(6):         video_decode, video_encode, display_max, camera_max,
                  isps, video_capture
connectivity(5):  wifi, bluetooth, usb, navigation, charging
lifecycle(4):     year, announced, revision, status
provenance(7):    completeness, sources, updated, datasheet_url,
                  wikipedia_url, wikidata_id, linux_dt_compatible
metadata(6):      devices, alternative_names, parent, tags, rating, benchmarks
```

### Fields to add for v3.0 (30 new fields to reach ~95):

| New Field | Why | Source | Complexity |
|-----------|-----|--------|------------|
| `market_segment` | Distinguish mobile/server/embedded/IoT/auto | Inferred from vendor + chip line | Low |
| `chipset_model` | GSMArena chipset ID mapping | Wikipedia + GSMArena | Medium |
| `gpu_model_vendor` | Separate GPU vendor from model (Qualcomm Adreno, ARM Mali, Imagination) | Wikipedia + TechPowerUp | Low |
| `gpu_api_vulkan` | Vulkan/OpenGL ES version support | Vendor specs | Low |
| `gpu_fp16_tflops` | Half-precision GPU compute (important for AI) | Vendor specs + calculation | Low |
| `ai_hardware` | NPU DSP name + tensor accelerator specifics | Vendor specs | Medium |
| `ai_int8_tops` | INT8 NPU performance (industry standard for mobile) | NotebookCheck + vendor | Low |
| `ai_fp16_tops` | FP16 NPU performance | Vendor specs | Low |
| `modem_5g_mmwave` | mmWave 5G support flag | Vendor specs + Wikipedia | Low |
| `modem_5g_sub6` | Sub-6 GHz 5G support flag | Vendor specs + Wikipedia | Low |
| `modem_nr_ca` | 5G carrier aggregation support | Vendor specs | Low |
| `wifi_version` | Numeric WiFi version (4/5/6/7) for filtering | Inferred from wifi string | Low |
| `bluetooth_version` | Numeric BT version for filtering | Inferred from bluetooth string | Low |
| `usb_version` | Numeric USB version for filtering | Inferred from usb string | Low |
| `charging_watt_max` | Maximum charging power in Watts | Vendor specs + device specs | Medium |
| `charging_wireless` | Wireless charging support | Vendor specs + Wikipedia | Low |
| `display_max_refresh` | Max display refresh rate | Vendor specs | Low |
| `display_hdr` | HDR format support (HDR10+, Dolby Vision) | Vendor specs + Wikipedia | Low |
| `camera_max_mpx` | Max camera sensor MP for filtering | Inferred from camera_max | Low |
| `video_decode_h265` | HEVC decode capability | Vendor specs + Wikipedia | Low |
| `video_decode_av1` | AV1 decode capability | Vendor specs + Wikipedia | Low |
| `video_decode_vp9` | VP9 decode capability | Vendor specs + Wikipedia | Low |
| `security` | Security features (TrustZone, Secure Enclave, etc.) | Vendor specs | Medium |
| `pcie_version` | PCIe generation support | TechPowerUp + vendor | Low |
| `pcie_lanes` | PCIe lane count | TechPowerUp + vendor | Low |
| `satellite` | Satellite communication (iPhone 14+, Huawei, etc.) | Wikipedia + vendor | Low |
| `e_sim` | eSIM support (modem feature) | Wikipedia + vendor | Low |
| `gnss_types` | GPS/GLONASS/BeiDou/Galileo/QZSS | Wikipedia + vendor | Low |
| `soc_id` | Die/package markings, hardware ID string | Vendor hardware | Low |
| `benchmark_antutu_v9` | Older AnTuTu v9 scores for comparison | AnTuTu ranking lists | Low |

### Target completeness model:

```python
# New field groups for v3.0 (adding ~5 new groups)
NEW_FIELD_GROUPS = {
    "new_media":    ["video_decode_h265", "video_decode_av1", "video_decode_vp9",
                     "display_max_refresh", "display_hdr", "camera_max_mpx"],
    "new_modem":    ["modem_5g_mmwave", "modem_5g_sub6", "modem_nr_ca"],
    "new_ai":       ["ai_hardware", "ai_int8_tops", "ai_fp16_tops"],
    "new_gpu":      ["gpu_model_vendor", "gpu_fp16_tflops", "gpu_api_vulkan"],
    "new_connect":  ["wifi_version", "bluetooth_version", "usb_version",
                     "charging_watt_max", "charging_wireless", "satellite",
                     "e_sim", "gnss_types"],
    "new_segment":  ["market_segment", "pcie_version", "pcie_lanes", "security"],
    "new_chip":     ["chipset_model", "soc_id"],
    "benchmarks":   ["benchmark_antutu_v9"],
}
```

---

## Feature Dependencies

```
Existing v2.1 infrastructure (SQLite, FTS5, async API, enrich pipeline, Wikidata)
          │
          ├── Phase 3.1: Scraper expansion (new source modules)
          │     │
          │     ├── Wikipedia: Extend to all vendors, fill gaps ─── independent
          │     ├── TechPowerUp spide: CPU database scrape ─── needs rate limiting
          │     ├── GSMArena/DeviceSpecs scrape ─── needs careful robots.txt handling
          │     ├── Vendor official sites ─── per-vendor logic, needs JS rendering (Playwright/Selenium)
          │     ├── NotebookCheck benchmark scrape ─── needs HTML table parsing
          │     └── Geekbench Browser scrape ─── needs JSON-LD extraction
          │
          ├── Phase 3.2: Data merging and dedup
          │     │
          │     ├── Multi-source merge pipeline ─── depends on all scrapers existing
          │     ├── Conflict detection and scoring ─── depends on merge pipeline
          │     └── Source authority weighting ─── depends on source metadata
          │
          ├── Phase 3.3: Schema expansion (30 new fields)
          │     │
          │     ├── New model fields ─── independent, but needs migration
          │     ├── New enrich modules for new fields ─── depends on new sources
          │     └── Extended completeness scoring ─── depends on new fields
          │
          ├── Phase 3.4: Quality dashboards and reports
          │     │
          │     ├── Data quality CI job ─── depends on data existing
          │     └── Per-vendor coverage reports ─── depends on quality metrics
          │
          ├── Phase 3.5: Comparison and statistics API
          │     │
          │     ├── Chip comparison endpoint ─── depends on full data
          │     └── Statistics dashboard ─── depends on comparison
          │
          └── Phase 3.6: Web UI updates
                │
                └── Handle 5000+ chips efficiently ─── depends on data volume
```

### Critical Dependency Chain

```
Scrapers exist → Data merged → Schema expanded → Quality dashboards (partially independent)
                                                       → Comparison API → Web UI
```

---

## MVP Recommendation (Phase Ordering)

### Phase 1: Scraper Expansion — TechPowerUp + NotebookCheck + Geekbench
**Why first:** These three sources cover the widest chip range with the most structured data. TechPowerUp alone adds 2000+ chips. NotebookCheck adds 20+ benchmarks per chip. Scrapability: HTML tables (not JS), well-structured URLs, permissive robots.txt.

**Delivers:** +2000 chips from TechPowerUp, benchmarks from NotebookCheck and Geekbench. Raises total to ~4000 chips.

### Phase 2: Schema Expansion (30 new fields) + Field Migration
**Why second:** Need the schema ready before the big data influx. The enrichment pipeline needs new domain modules for the new fields.

**Delivers:** Complete 95-field schema. Migration path for existing 1761 chips. All 30 new fields populated for new chips.

### Phase 3: Vendor Official Site Scrapers (Qualcomm, MediaTek, Apple, Samsung)
**Why third:** These are the hardest to build (JS rendering, per-vendor logic, rate limiting). Do them after the technical foundation is solid and the data pipeline is proven.

**Delivers:** Official data for 1500+ chips from the 4 biggest vendors. Fills gaps in process node, NPU TOPS, charging, and connectivity that aggregators don't provide.

### Phase 4: GSMArena + DeviceSpecifications Phone-Centric Scrapers
**Why fourth:** Phone-oriented fields (camera, display, battery). Important for mobile SoC completeness but lower priority than the core chip spec data.

**Delivers:** Mobile-oriented fields (camera, display, battery, charging) for 2000+ chips. Device → SoC mapping.

### Phase 5: Data Merging, Dedup & Cross-Validation
**Why fifth:** Requires all scrapers to exist. Merging logic is complex and must handle 6+ sources per chip.

**Delivers:** Single-canonical chip entries with merged fields, source tracking, and conflict scoring.

### Phase 6: Quality Dashboards + Comparison API
**Why sixth:** Depends on clean, merged data. Quality metrics are meaningless before merging.

**Delivers:** Per-vendor completeness reports, conflict heatmaps, `GET /v1/chips/{id}/compare` endpoint.

### Phase 7: Web UI Upgrade + Extended CLI
**Why last:** UI enhancement depends on fully populated data and stable schema. CLI filter flags depend on final field list.

**Delivers:** Typeahead search, chip comparison tables, filterable chip lists, CLI upgrades.

### Deferred to v3.1+:
- Device ↔ SoC cross-reference database (50000+ relationships)
- Real-time announcement monitoring
- Developer portal / API key management
- Bulk chip import/export API
- Hardware database as a service (marketplace)

---

## Data Quality Metrics

### Proposed quality dimensions for v3.0:

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Chip count** | ≥5000 | Total entries in database |
| **Completeness** | ≥0.80 | Weighted field fill ratio (existing scoring) |
| **Field coverage** | ≥0.90 | Percentage of 95 fields populated across database |
| **Source diversity** | ≥3.0 | Average number of sources per chip |
| **Conflict rate** | <0.05 | Percentage of chips with field conflicts (sources disagree) |
| **Freshness** | <90 days | Days since last data update for 90% of chips |
| **Vendor coverage** | ≥40 | Number of distinct vendors with ≥10 chips each |
| **Benchmark coverage** | ≥0.60 | Percentage of chips with ≥1 benchmark score |

---

## Sources

### Inspected live (HIGH confidence):
- **TechPowerUp CPU Database** `(techpowerup.com/cpu-specs/)` — 4398 CPUs, 30+ fields per entry, structured URL patterns, REST API available for licensing.
- **NotebookCheck Mobile Processor Benchmark List** `(notebookcheck.net/Mobile-Processors-Benchmark-List.2436.0.html)` — 1000+ processors, 20+ benchmarks, speculative CPU/GPU parameters, AI NPU TOPS column.
- **DeviceSpecifications** `(devicespecifications.com/en/processor-list)` — Phone+SoC database, fields include SoC model, CPU config, GPU, RAM type/speed.
- **GSMArena** `(gsmarena.com)` — 10000+ phones, each with chipset field, camera/display/battery/connectivity specs. No dedicated SoC page — chipset info embedded in phone page.
- **soc-db v2.1 codebase** — 65-field scoring model, Chip Pydantic model with 95 named fields, existing enrichment pipeline.

### Derived from web research (MEDIUM confidence):
- **Qualcomm Developer Network** — Documented product page structure from secondary sources. Actual page structure may differ when crawled.
- **MediaTek product pages** — Product listing structure described in press/review analysis. Actual HTML structure unverified.
- **Apple Tech Specs** — Known to list processor details for current products. Historical data may require archival sources.
- **Geekbench Browser** — Known to block automated access (403 response verified). JSON-LD in page source is documented but may change.

### Industry knowledge (MEDIUM-HIGH confidence):
- Existing soc-db commodity knowledge from v1.0–v2.1 development (1761 chips across 43 vendors, known gaps).
- Wikipedia infobox scraping patterns from existing scraper_wikipedia.py (511 lines, 14 vendors).

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **TechPowerUp blocks scraping** | Lose 2000+ chips | Use their licensing program (they offer REST API + MCP access). Fall back to Wikipedia. |
| **Vendor sites require JS rendering** | Can't scrape with simple HTTP | Use Playwright/Selenium for dynamic pages. Prioritize static HTML sources. |
| **Geekbench rate limiting (403)** | Benchmarks unavailable | Cache aggressively, <1 req/s, use JSON-LD extraction from cached pages. |
| **Schema bloat (95+ fields)** | API responses too large | Support field selection: `?fields=name,cpu,gpu,benchmarks` |
| **Data conflicts between sources** | Users see contradictory values | Conflict scoring → expose all values in `sources` dict with confidence | | **WikiData SPARQL changes** | Dynamic enrichment breaks | Version-pin property P-IDs, validate results before writing (already in PITFALLS.md). |

---

## Appendix: Scraper Priority Matrix

| Source | Chip Count | Field Depth | Scrape Difficulty | Per-field Freshness | Priority |
|--------|-----------|-------------|-------------------|-------------------|----------|
| TechPowerUp | 4398 | 30+ | Low (HTML, static) | Monthly | **P0** |
| Wikipedia | 3000+ | 25+ | Low (HTML tables) | Continuous | **P0** |
| NotebookCheck | 1000+ | 20 benchmarks | Low (HTML table) | Continuous | **P0** |
| Qualcomm official | 400+ | 50+ | Medium (JS) | Quarterly | **P1** |
| MediaTek official | 300+ | 50+ | Medium (JS) | Quarterly | **P1** |
| Geekbench Browser | 2000+ | 3 benchmarks | Medium (403 risk) | Continuous | **P1** |
| Intel ARK | 1500+ | 40+ | Medium (dynamic) | Quarterly | **P1** |
| AMD official | 400+ | 40+ | Low | Quarterly | **P1** |
| GSMArena | 10000+ | 15 (mobile) | Medium (no SoC page) | Continuous | **P2** |
| DeviceSpecs | 5000+ | 10 (mobile) | Medium (per-phone) | Continuous | **P2** |
| Apple Tech Specs | 80+ | 30+ | Low | Quarterly | **P2** |
| Samsung Semi | 200+ | 40+ | Medium (JS) | Quarterly | **P2** |
| AnTuTu rankings | 500+ | 3 benchmarks | Medium (fragile) | Continuous | **P2** |
| Linux DeviceTree | 2000+ | 10+ | Medium (git repo) | Monthly | **P3** |
| Wikidata SPARQL | 2000+ | 15 | Low (API) | Monthly | **P3** |
| HiSilicon official | 100+ | 30+ | Hard (blocked) | Quarterly | **P3** |
| Community PRs | — | — | Low | Continuous | **P3** |

### Notes on priority:
- **P0** = Must have for v3.0 launch. Build these first.
- **P1** = High value, should be in v3.0 but can come after P0.
- **P2** = Nice to have for v3.0. Fill gaps after P0/P1.
- **P3** = Good to have for v3.0 but not blocking. Can defer to v3.1.

---

*Researched: 2026-07-19*
*Ready for roadmap: yes*
