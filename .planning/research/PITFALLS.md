# Pitfalls Research: Multi-Source SoC Data Collection at Scale

**Domain:** Large-scale web scraping & data pipeline — 5000+ SoC records, multi-source deduplication
**Researched:** 2026-07-19
**Confidence:** HIGH (based on established scraping industry patterns, existing codebase analysis, and documented legal cases)

## Critical Pitfalls

### Pitfall 1: Naive Rate Limiting Causes Cascading Blocks

**What goes wrong:**
The existing `fetch()` in `common.py` has a hard-coded `time.sleep(1)` — one request per second with a single `USER_AGENT` and no proxy rotation. At 5000+ chips across multiple sources, this approach will trigger rate limits, IP blocks, and CAPTCHAs on every target. Worse: once one source blocks you, the scraper either fails entirely (halting collection) or continues hitting the blocked source (wasting requests and time).

**Why it happens:**
- Single IP, single User-Agent string (`SOC-DB/1.0`), no request jitter — trivially fingerprintable
- The current rate limiter (`rate_limit.py`) only protects the **API** from clients, NOT the scraper from target sites
- Developers think "add a sleep(1)" is sufficient — it's not at 5000+ chip scale across 20+ target pages
- Each source (Qualcomm, MediaTek, GSMArena, etc.) has DIFFERENT rate limit thresholds and detection patterns

**How to avoid:**
- **Per-source rate limiter** — NOT a global sleep. Use a separate rate limiter per target domain with configurable RPM (requests per minute) per source
- **Proxy rotation** — residential proxy pool for vendor sites, datacenter proxies for Wikipedia. Never use a single IP for bulk scraping
- **User-Agent rotation** — maintain a pool of realistic browser UAs, rotate per request
- **Exponential backoff** — on 429/503, back off with jitter: 1s → 2s → 4s → 8s → max 60s
- **Failure isolation** — one source block should NOT stop scraping other sources. Per-source error budgets
- **Respect `Retry-After` headers** — when present, ALWAYS obey them

**Warning signs:**
- Scraper starts getting sporadic 429 (Too Many Requests) responses
- Previously working scrapers return CAPTCHA pages
- Target sites start serving 10-30s delayed responses before blocking
- User-Agent "SOC-DB/1.0" appears in target server logs as a single heavy hitter

**Phase to address:** Phase 1 — Scraper Pipeline Overhaul. Must be built in before adding new sources.

---

### Pitfall 2: Schema Drift — Vendor Sites Change Layout Without Notice

**What goes wrong:**
The Wikipedia scraper (`scraper_wikipedia.py`) relies on `table.wikitable` CSS class selectors and specific column detection logic (`detect_columns`). When Wikipedia or a vendor site redesigns their tables, the scraper silently produces empty results, partial data, or wrong field mappings. This has already been flagged as a concern in `CONCERNS.md` ("Layout changes on Wikipedia could silently break scrapers"). At 5000+ chips, a silent 3-day scrape failure wastes compute and creates a stale data gap.

**Why it happens:**
- Scrapers use brittle CSS class selectors and positional column indices
- No validation that scraped output passes JSON Schema before writing
- `write_vendor_file()` silently skips failures — writes empty arrays, existing data is untouched, but NO ALERT is raised
- The only signal is "0 chips extracted" in a log line buried in CI output
- Multiple scrapers means multiple points of failure with no unified health check

**How to avoid:**
- **Schema drift detection** — maintain a checksum of expected HTML structure per source. Alert on mismatch
- **Minimum yield threshold** — if a scraper returns < 50% of expected chips for a source, flag for human review instead of writing
- **Visual regression testing** — snapshot known-good pages and diff parsed output, not just raw HTML
- **Graceful degradation** — if Wikipedia table layout changes, fall back to Wikidata SPARQL (already exists) rather than producing zero results
- **Weekly CI validation** — run all scrapers in CI, compare output counts against historical baselines, alert on >20% deviation

**Warning signs:**
- Scraper output count drops suddenly (e.g., Qualcomm went from 431 to 0)
- New fields appearing in parsed output with unexpected values
- `detect_columns()` starts matching different columns than intended
- Extraction time per page increases significantly (CSS selectors matching more elements)

**Phase to address:** Phase 1 (baseline detection) + Phase 2 (alerting). Add yield monitoring and schema validation before expanding to new sources.

---

### Pitfall 3: The Deduplication Nightmare — Same Chip, Different Names

**What goes wrong:**
The same hardware platform has dramatically different names across sources:
- Wikipedia: *"Snapdragon 8 Gen 2"*
- Qualcomm: *"SM8550-AB"*
- GSMArena: *"Snapdragon 8 Gen 2 Mobile Platform"*
- Linux DeviceTree: *"qcom,sm8550"*
- Geekbench: *"Qualcomm SM8550-AB Snapdragon 8 Gen 2"*

Current `_match_existing()` only does exact ID/model/name matching. It will create DUPLICATE entries for the same chip from different sources. The `write_vendor_file()` will try to merge by slug, but if the slugs differ (e.g., `snapdragon_8_gen_2` vs `sm8550`), they become separate records. At 5000+ chips with 4-5 sources each, the database could inflate to 20K+ "unique" chips.

**Why it happens:**
- No canonical chip identity — each source has its own naming convention
- Model numbers (SM8550) and marketing names (Snapdragon 8 Gen 2) are treated as separate fields, not as the same entity
- Current matching is exact-string only — no fuzzy matching, no alias resolution
- No alias table or registry that maps "SM8550" ↔ "Snapdragon 8 Gen 2" ↔ "qcom,sm8550"
- `slug()` function produces different IDs for different name variants

**How to avoid:**
- **Canonical identity system** — assign each chip a stable UUID at ingestion time, NOT a name-derived slug
- **Multi-strategy matching pipeline**:
  1. Exact model number (SM8550 = SM8550)
  2. Fuzzy name matching (Levenshtein/Damerau-Levenshtein on chip names, threshold >0.85)
  3. Known alias table (curated mapping of model→marketing name)
  4. Wikidata QID resolution (already exists for vendor knowledge — extend to chips)
  5. Hardware characteristics matching (same CPU cores + same GPU + same year = likely same chip)
- **Merge policy** — on conflict, prefer official vendor source > Wikipedia > third-party, not "last writer wins"
- **Dedup dashboard** — flag unresolvable matches for human review in the auto-PR workflow

**Warning signs:**
- Chip count grows faster than expected after adding new source
- Same chip appearing in search results twice with slightly different field values
- Completeness score drops because data is split across duplicate entries
- Vendor file shows suspiciously close "generation" gaps (two chips with same year, same CPU, different ID)

**Phase to address:** Phase 3 — Dedup Pipeline. This is the most complex phase. Do NOT add sources until identity resolution is designed.

---

### Pitfall 4: Data Provenance Loss — Undoable Merges

**What goes wrong:**
The current merge strategy in `write_vendor_file()` is destructive: when two sources disagree on a field, the **last scraped source silently overwrites** the previous value. There is no field-level provenance tracking. If the Qualcomm scraper extracts "5 nm" for a chip but the MediaTek scraper says "4 nm" for the same SoC, the last-run scraper wins — and there's no way to audit which source provided which value, or to detect conflicts.

**Why it happens:**
- Existing chip records are plain JSON with no `_source` or `_provenance` metadata
- `write_vendor_file()` assigns field by field with `if (k not in old or old[k] in (None, "", [], 0, 0.0)) and v not in (None, ...)` — first writer wins rather than best source wins
- No conflict detection — if both sources have a value, the first one written sticks silently
- When the enrichment pipeline runs (`enrich_all`), it further mutates fields without provenance

**How to avoid:**
- **Field-level provenance tracking** — extend data model to track per-field source:
  ```json
  {
    "id": "sm8550",
    "name": "Snapdragon 8 Gen 2",
    "process_node": "4 nm",
    "_provenance": {
      "process_node": { "source": "qualcomm_official", "scraped_at": "2026-07-19T10:00:00Z", "confidence": "HIGH" },
      "name": { "source": "wikipedia", "scraped_at": "2026-07-18T14:00:00Z", "confidence": "MEDIUM" }
    }
  }
  ```
- **Source priority tiers** — official vendor docs > manufacturer press releases > Wikipedia > third-party aggregators > inferred/enriched
- **Conflict reports** — generate a diff report when two sources disagree. Add to auto-PR so humans review
- **Immutable audit log** — track every field change with before/after/source/timestamp (append-only log or separate changelog file)
- **Migration strategy** — existing records need a one-time provenance backfill (mark all existing values as `_source: "legacy_v2"`)

**Warning signs:**
- Mystery fields with no clear origin ("where did this architecture value come from?")
- Rollback requests that can't be answered ("which source said 5 nm?")
- Inconsistent completeness scoring (one source fills fields, another overwrites them empty)
- Debugging enrichment bugs requires tracing through 3+ sources manually

**Phase to address:** Phase 2 — Data Model Extension. Provenance must be built into the schema before adding sources. Retrofitting is much harder.

---

### Pitfall 5: API Performance Regressions from Enrichment Pipeline

**What goes wrong:**
The existing API loads ALL chips into memory synchronously on cache miss (~300ms for 1761 chips). Enriching 5000+ chips involves running 14+ enrichment modules per chip (CPU, GPU, memory, modem, etc.). If `enrich_all()` is called during the API request path — or if data loading triggers full enrichment — the 300ms grows to several seconds. The API becomes unusable.

Additionally, the current `load_all()` in `cli.py` and `api/main.py` is duplicated sync code. The async path (`load_all_async`) exists but `get_chips()` still calls the sync version.

**Why it happens:**
- `enrich_all()` is called from `write_vendor_file()` (data write path), but NOT separated from the read path
- No separation between "scraped raw data" and "enriched/queryable data"
- All enrichment is eagerly computed on every write — no lazy enrichment for API queries
- The API cache has a TTL that triggers full reload + enrichment on expiry
- 5000 chips × 14 enrichment modules = 70,000 enrichment operations per load

**How to avoid:**
- **Separation of concerns** — keep "raw scraped data" (immutable, per-source) separate from "enriched views" (computed, merged, cached)
- **Pre-compute enrichment offline** — enrichment runs during data collection, not during API reads. The API serves pre-enriched data
- **Staged loading** — API loads only indexed fields (id, name, vendor, model, year) for search/list; full enrichment loaded on detail view
- **Incremental enrichment** — when adding a new source, only enrich the delta (new/modified chips), not all 5000
- **Async I/O** — fix the `get_chips()` → synchronous `load_all()` path. Use `asyncio.to_thread()` or migrate fully to `aiosqlite`

**Warning signs:**
- API response times degrade progressively as more chips are added
- Cache invalidation spikes CPU to 100%
- `/health` endpoint times out during enrichment cycles
- Search responses slow even for simple queries (should be O(1) with FTS5)

**Phase to address:** Phase 4 — Performance. Do this AFTER adding sources but BEFORE shipping to production. Profile first, optimize second.

---

### Pitfall 6: False Positives in Auto-PR Workflow

**What goes wrong:**
The data changes from scraping will trigger PRs against the `data/*.json` files. If every scrape difference opens a PR, the review queue floods with noise:
- Wikipedia bot edits a chip's description — minor wording change
- Number format changes ("4 nm" → "4nm" on a vendor site)
- Year field drifts because Wikipedia updates launch dates
- Schema version bumps cause diff noise in every field

Reviewers burn out, start auto-approving, and real data quality issues slip through.

**Why it happens:**
- No diff filtering — every byte change generates a PR
- No semantic diff — "4 nm" → "4nm" is a formatting change, not a data change
- No change classification — field A changing is usually noise, field B changing is usually signal
- No human-review budget — too many PRs means no one reviews carefully

**How to avoid:**
- **Semantic diff engine** — compare parsed values, not raw JSON. "4 nm" == "4nm" → skip
- **Change classification** — classify each change as:
  - **Noise** (whitespace, formatting, reordering) → auto-merge, no PR
  - **Information gain** (empty → value, old value updated with higher-confidence source) → auto-merge with changelog entry
  - **Conflict** (two sources disagree, or value changes from known to less-likely) → human-review PR
  - **Novel addition** (new chip, new field) → human-review PR with summary
- **Review batching** — group related changes into single PRs (e.g., "Qualcomm weekly update: +12 chips, 34 updates, 3 conflicts")
- **Confidence-based thresholds** — only flag changes where source confidence meets a minimum bar
- **Suppress known churn** — some chips get wikipedia edits daily. Identify high-churn chips and batch them weekly instead of per-edit

**Warning signs:**
- PRs piling up faster than they can be reviewed
- Reviewers start leaving "LGTM" on all PRs without reading
- Same chip appearing in PRs every week with trivial changes
- Rolled-back data changes (team reverts a PR that was wrong)

**Phase to address:** Phase 5 — Auto-PR Workflow. Do NOT automate PR creation without change classification. Start with manual review of auto-generated diffs first.

---

### Pitfall 7: Legal Exposure from Unauthorized Scraping

**What goes wrong:**
GSMArena, DeviceSpecifications, and vendor sites have terms of service that explicitly prohibit scraping. The project scrapes publicly available factual data (chip specifications), which is generally legal under *Feist v. Rural Telephone* (facts are not copyrightable). However:
- The Computer Fraud and Abuse Act (CFAA) can apply if scraping violates ToS after a cease-and-desist (*Craigslist v. 3Taps*)
- European database rights may protect curated chip databases
- Vendor sites (Qualcomm Developer Network) may restrict automated access in ToS
- The existing `USER_AGENT = "SOC-DB/1.0 (+https://github.com/...)"` explicitly identifies the scraper — good for transparency, bad if scraping is prohibited
- A C&D letter creates legal liability for continued scraping (*hiQ Labs v. LinkedIn*)

The project is open-source on GitHub. Aggressive scraping from a public repository is trivially traceable.

**Why it happens:**
- "It's public data" is not always a legal defense — method of access matters
- Terms of service can create contractual obligations (*Ryanair v. Billigfluege.de* — Irish court upheld click-wrap ToS)
- Database rights in EU/UK protect substantial investment in collection/curation
- The scraper identity is baked into the User-Agent — legal discovery is trivial if challenged
- No legal review was done before the v2.0 scrapers were built

**How to avoid:**
- **Legal audit** — for each target source, review ToS, scraping policy, and robots.txt. Document the legal basis for scraping
- **Prefer official APIs** — Qualcomm Developer Network, MediaTek Developer Portal may have official data feeds. These are legally safer AND more reliable
- **robots.txt compliance** — respect Crawl-delay directives. Cache robots.txt per source with TTL and re-check periodically
- **Rate limiting as legal defense** — scraping at human-like rates (< 1 req/sec) demonstrates good faith. "200-300 requests per minute" was cited in *QVC v. Resultly* as excessive
- **Cease-and-desist response plan** — pre-define what happens if a source sends a C&D: which data to stop scraping, how to archive existing data, alternative sourcing strategy
- **Separate scraper identity** — use a different User-Agent for problematic targets (or use residential proxies). The `SOC-DB/1.0` identity is legally clean but operationally fragile
- **Prefer data sources with permissive terms** — Wikipedia (CC-BY-SA), Wikidata (CC0), Linux DeviceTree (GPL), vendor press releases are legally safer

**Warning signs:**
- Target site updates its robots.txt with `Disallow: /` for known scraper paths
- Target site shows CAPTCHA for every request (precursor to legal action)
- Legal team inquiry (internal or external)
- Terms of Service update adding explicit "no scraping" clause
- Rate of 503/403 errors increases significantly (technical enforcement precedes legal)

**Phase to address:** Phase 0 — Legal Review. Do BEFORE any new scraper implementation. Create a source compliance matrix.

---

### Pitfall 8: Vendor Site Anti-Bot Systems Blocking the Scraper

**What goes wrong:**
Modern vendor sites (Qualcomm, MediaTek, Apple Tech Specs) use Cloudflare, DataDome, Akamai, or other WAF/bot detection systems. The current BeautifulSoup-based scraper with `urllib.request` will be immediately blocked — it can't execute JavaScript, doesn't maintain a browser fingerprint, and has no TLS fingerprint randomization (JA3 signature). The scraper gets a Cloudflare challenge page instead of chip data, and the operator doesn't notice for weeks.

**Why it happens:**
- Existing scrapers use `urllib.request.urlopen()` — no JS execution, no browser automation
- `BeautifulSoup` parses static HTML only — cannot handle React/Angular frontends common on modern vendor sites
- No TLS fingerprint management — Python's `urllib` has a distinctive JA3 signature that WAFs recognize instantly
- The `fetch()` function has no error classification — it returns the Cloudflare challenge page as valid HTML, which then fails to parse any chips
- Existing scrapers were designed for Wikipedia (no anti-bot). Vendor sites are a completely different class of target

**How to avoid:**
- **Scraper capability tiers:**
  - Tier 1 (Wikipedia, Linux DeviceTree): `urllib` + BeautifulSoup — no anti-bot, static HTML
  - Tier 2 (TechPowerUp, NotebookCheck): `httpx` with fingerprint randomization + rotating User-Agents
  - Tier 3 (GSMArena, DeviceSpecifications): Playwright/Selenium headless browser + proxy rotation
  - Tier 4 (Qualcomm, Apple): Official API if available; manual/contractual data access if not
- **Anti-bot detection middleware** — create an abstraction layer that detects challenge pages (Cloudflare, CAPTCHA) before the response reaches the parser
- **TLS fingerprinting** — consider using `curl_cffi` instead of `urllib` for TLS-level impersonation of real browsers
- **Headless browser fallback** — if Tier 2 gets blocked, escalate to Tier 3 automatically
- **Manual override** — for critical sources that remain blocked, document a "manual data entry" workflow as last resort

**Warning signs:**
- `parse_standard_table()` returns 0 chips but the page content is HTML (check the actual response)
- Response body contains "Checking your browser," "Just a moment," or "Attention required"
- HTTP status 403, 503, or 200 but with a challenge page
- Response time is suspiciously fast (<100ms for what should be a heavy page)

**Phase to address:** Phase 1 — Scraper Infrastructure. Build the capability tiers before targeting vendor sites.

---

### Pitfall 9: Stale Data Inconsistency — Weekly Refresh Causes Churn

**What goes wrong:**
The scraper pipeline is designed to run on a weekly schedule (from CI). When it re-scrapes all sources:
1. Wikipedia infobox data changes slightly (bot edits, formatting fixes) → 10% of fields "change"
2. Vendor sites may be unreachable → 30% of chips fail to refresh
3. Some sources update slowly → mixed data from different weeks

The result: weekly PRs with hundreds of churn changes, data that's partially fresh and partially stale, and no way to know which sources contributed to the current state.

**Why it happens:**
- Current `fetch()` has a 24h cache TTL for individual pages, but the pipeline has no "data freshness" concept
- No staleness budget ("this chip was last confirmed by source X N days ago")
- No source staleness metadata — after merge, it's impossible to tell which fields were refreshed and which are from the previous run
- The merge strategy (`write_vendor_file`) doesn't record `scraped_at` or `source` timestamps
- Weekly refresh is too aggressive for stable sources (Wikipedia) and too infrequent for dynamic sources (vendor sites)

**How to avoid:**
- **Source freshness metadata** — track per-source `last_successful_scrape` timestamp per chip category
- **Staleness budget per source**:
  - Wikipedia: refresh monthly (stable data)
  - Vendor sites: refresh weekly (new releases)
  - New chip announcements: on-demand (triggered by RSS/webhook)
- **Incremental refresh** — only scrape sources whose staleness budget is exceeded, not all sources every time
- **Timestamp-aware merge** — when merging, prefer the value from the source with the most recent `scraped_at` if confidence is equal
- **Staleness dashboard** — show "days since last confirmed" per vendor. Alert when exceeds 2× the staleness budget

**Warning signs:**
- Weekly PR shows changes to chips that haven't been announced (Wikipedia formatting edits)
- A chip's `year` field keeps changing by ±1 year across weeks
- Newly released chips take weeks to appear because weekly schedule misses them
- Data from some vendors appears "stale" (no updates for months) but there's no alert

**Phase to address:** Phase 2 — Data Model (freshness metadata) + Phase 5 — Scheduling. Staleness tracking must be in the data model before scheduling decisions can be made.

---

### Pitfall 10: Slug Collisions and ID Instability

**What goes wrong:**
The `slug()` function in `common.py` generates chip IDs from name+model. This creates two failure modes:
1. **Collision** — "Snapdragon 8 Gen 2" and "Snapdragon 8 Gen 2 Mobile Platform" can produce the same slug, overwriting each other
2. **Instability** — if a chip name changes slightly (e.g., Wikipedia adds a footnote), the slug changes. The "old" chip is treated as deleted, the "new" one as added — even though it's the same chip

The `write_vendor_file()` has logic to update IDs when names change, but this is fragile and can orphan references in the database.

**Why it happens:**
- ID is derived from display name, not from a stable identifier (model number, QID, UUID)
- The slug generation has 6-part truncation — "Snapdragon 8 Gen 2" = `snapdragon_8_gen_2` but "Snapdragon 8 Gen 2 Mobile Platform" could also truncate to the same
- `KNOWN_PREFIXES` and skip-lists create arbitrary rules for what's a "chip name" — these are fragile and already have gaps
- No UUID or hash-based persistent identifier

**How to avoid:**
- **Stable canonical ID** — use a hash of the model number (e.g., SHA256 of "SM8550") or a sequential UUID. NOT derived from name
- **Model-first identification** — organize chips by model number (SM8550) with marketing name as an attribute, not the other way around
- **Migration mapping** — create a `chip_id_map.json` that maps old slugs → new UUIDs for backward compatibility
- **Alias registry** — maintain a registry of all known names/designators for a chip, keyed by canonical ID:
  ```json
  {
    "canonical_id": "a1b2c3d4",
    "model": "SM8550",
    "aliases": ["Snapdragon 8 Gen 2", "Snapdragon 8 Gen 2 Mobile Platform", "qcom,sm8550"],
    "qid": "Q115615277"
  }
  ```

**Warning signs:**
- Vendor file audit shows chips appearing/disappearing between runs
- `write_vendor_file()` log shows many "removed" entries
- GitHub diff shows chips renamed (old name → new name in same file)
- Data integrity checks show orphan references (enrichment modules referencing non-existent chips)

**Phase to address:** Phase 3 — Dedup Pipeline. ID stability is a prerequisite for deduplication.

---

### Pitfall 11: Enrichment Module Performance at 5000× Scale

**What goes wrong:**
The enrichment modules (`infer_cpu`, `infer_gpu`, `infer_memory`, etc.) are domain-specific inference functions called for each chip. At 1761 chips this is fast. At 5000+ chips with 14+ modules:
- Each module iterates over all chips
- Some modules call external services (Wikidata SPARQL — the weekly vendor knowledge refresh)
- The year inference module (`infer_year`) is a 700-line function with ~40 if/elif regex blocks per chip
- There's no caching of per-module results

The weekly CI job that runs enrichment goes from 30 seconds to 5+ minutes, and the API enrichment during loading causes visible latency.

**Why it happens:**
- Pre-mature optimization wasn't needed at 1761 chips — now it's a bottleneck
- No module-level result caching — running `infer_cpu` on all chips twice is 2× the work
- The monolithic `infer_year()` function is O(n × patterns) — at 5000 chips × 40 patterns = 200,000 regex operations
- Wikidata SPARQL queries are called for every chip that's missing vendor knowledge — no batch querying

**How to avoid:**
- **Batch enrichment** — process chips in batches, not individually. Vectorize where possible
- **Module result caching** — cache enrichment output per chip by module. Re-enrich only when input fields change
- **Lazy enrichment** — enrich on first read, not on write. Store raw scraper data, enrich when queried
- **Profiling** — run `cProfile` on the enrichment pipeline at full scale before optimization. Don't guess where the bottleneck is
- **SPARQL batching** — combine Wikidata QID lookups into batch queries instead of N individual queries
- **Module parallelism** — enrichment modules are independent (CPU doesn't depend on GPU). Run them in parallel with `concurrent.futures`

**Warning signs:**
- Weekly CI pipeline times out or approaches time limits
- `enrich_all()` shows up in profiling as the hottest path
- CPU usage spikes during API cache refresh
- SPARQL queries start returning 429 (rate limited) — individual queries hit per-second limits

**Phase to address:** Phase 4 — Performance Optimization. Profile first; the actual bottlenecks may differ from expectations.

---

### Pitfall 12: GitHub Pages Integrity Broken by Data Changes

**What goes wrong:**
The web UI is generated from `docs/` directory and deployed to GitHub Pages. If a scraper or data pipeline script accidentally modifies, deletes, or overwrites files in `docs/` (index.html, 404.html, swagger.html), the GitHub Pages deployment breaks. This is flagged as a CRITICAL CONSTRAINT in PROJECT.md, but there's nothing in the current code preventing it.

**Why it happens:**
- `write_vendor_file()` writes to `DATA_DIR` which is `data/` — adjacent to `docs/` in the repo root
- A stray path manipulation could write to `docs/`
- The CI pipeline that runs scrapers also deploys Pages — a scraper crash could corrupt the deployment step
- No write guard or path validation for `docs/`
- A PR that modifies both `data/` and `docs/` could accidentally include data changes in the Pages deploy commit

**How to avoid:**
- **Filesystem boundary guard** — add a write-time check that rejects any file write to `docs/`:
  ```python
  if str(path).startswith(str(REPO_ROOT / "docs")):
      raise PermissionError("CRITICAL: Attempted write to docs/")
  ```
- **Dedicated CI steps** — separate "scrape + update data" from "deploy pages". If data step fails, pages step still runs with existing data
- **Pre-commit check** — add a pre-commit hook that rejects changes to `docs/` from data pipeline scripts
- **GitHub branch protection** — if possible, protect the `gh-pages` source branch separately from the data source branch
- **Immutable docs/** — treat `docs/` as a build artifact, not source. Generate it in CI from data, not during scraping

**Warning signs:**
- GitHub Actions workflow fails with "Pages deployment failed"
- `docs/` shows unexpected diffs in PRs that only modify data
- Local `git status` shows changes in `docs/` after running a scraper

**Phase to address:** Phase 0 — Safety Guards. Add this BEFORE any new scraping code reaches production.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Derive chip ID from name (current `slug()`) | Simple, no ID schema needed | Collisions, ID instability, data duplication | ONLY at <1000 chips; MUST replace before 5000 |
| Last-writer-wins merge (current `write_vendor_file`) | Simple implementation | Data provenance loss, undebuggable conflicts | NEVER for multi-source; only acceptable for single-source |
| Synchronous file I/O in API (current `load_all()`) | Simple implementation | Blocks event loop, degrades under load | ONLY for single-user / dev; MUST fix for production API |
| No per-field source tracking | Keeps data model simple | Can't audit, roll back, or resolve source conflicts | NEVER for multi-source pipeline |
| Global `time.sleep(1)` rate limiting | Simple, prevents immediate bans | Ineffective at scale, false sense of security | NEVER — must be per-source with jitter |
| Hardcoded chip knowledge maps (VENDOR_KNOWLEDGE) | Fast, no external dependency | Stale data on new releases, code change required | ONLY for stable/slow-moving vendors; replace with Wikidata SPARQL for fast-moving ones |
| No minimum yield threshold on scrapers | Silent on failure | Data gaps go unnoticed for weeks | NEVER — scraper should alert on low yield |
| `scripts/` directory with duplicate logic | Quick prototyping | Confusion about authoritative code, skipped by CI checks | ONLY as scratch; MUST migrate to `src/soc_db/` before v3.0 |
| Single target URL per vendor (WIKI_PAGES dict) | Simple, works for Wikipedia | Blocks multiple-page scraping (common for large vendors) | ONLY for single-page sources; MUST support multi-page for Qualcomm/MediaTek |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **Wikipedia** | Assume infobox format is stable | Use schema-drift detection; fall back to Wikidata SPARQL on layout change |
| **Qualcomm Developer Network** | Treat as simple HTML scraping | Likely requires API key or headless browser (Cloudflare protection). First check for official API/dataset |
| **MediaTek / Dimensity** | Expect structured HTML tables | MediaTek site is JS-heavy SPA. Requires headless browser or API |
| **Apple Tech Specs** | Use same scraper pattern as Wikipedia | Apple site uses different structure per product line. Consider official press releases instead |
| **GSMArena / DeviceSpecifications** | Scrape without checking ToS | Both likely prohibit scraping. Use ethically — rate limit heavily, cache aggressively, respect robots.txt |
| **Linux DeviceTree** | Assume all chips have DTS entries | Many mobile SoCs not yet upstreamed. Use as supplement, not primary source |
| **Geekbench Browser** | Bulk query without API | Has rate limits. Use official API if available, or batch queries with polite intervals |
| **Wikidata SPARQL** | Individual queries per chip | Use batch SPARQL queries with VALUES clause. Already partially done for vendor knowledge |
| **NotebookCheck** | Expect stable URL patterns | URLs contain non-semantic IDs. Use their search function. Check if scraping is permitted |
| **GitHub Actions CI** | Let scraper workflow write to gh-pages branch | Separate data-gen workflow from deploy workflow. Never let scraper write to `docs/` |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Eager enrichment on every write | API latency spikes, CI timeouts | Pre-compute enriched views; store raw data separately | >2000 chips currently borderline; definite at 5000 |
| Synchronous per-chip Wikidata SPARQL | 30+ minute CI runs, rate limits hit | Batch SPARQL queries; cache results with 24h TTL | >500 chips (already hitting this) |
| Regex-heavy enrichment per chip (infer_year) | CPU-bound enrichment, slow CI | Profile and pre-compile regex; consider data-driven approach | Already a concern at 1761 chips (700-line function) |
| Loading all chips into memory on API startup | Cache miss latency, memory pressure | Staged loading (summary fields first, full detail on demand) | >5000 chips makes memory pressure significant |
| Single-page scraping for multi-page vendors | Misses chips from continuation pages, incomplete data | Pagination-aware scrapers that follow "next page" links | At v3.0 scale, Qualcomm listing spans multiple pages |
| No incremental refresh in CI | Re-scrapes everything weekly, waste of quota | Track last-modified per source; only scrape changed/expired entries | >3 sources makes full refresh impractical |
| `urllib.request.urlopen()` for all scrapes | Cannot handle JS SPAs, blocked by WAFs | Capability-tiers abstraction (Tier 1-4); use Playwright/httpx for JS sites | First vendor site with Cloudflare |
| Per-chip file I/O in write path | Slow merge for 5000+ chips | Batch writes; use database transactions instead of individual file writes | ~3000 chips when JSON file grows large |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing API keys for vendor portals in source code | Credential leak via public GitHub | Use environment variables or GitHub Secrets. Never commit secrets. Pre-commit hook already checks for private keys |
| Hardcoded cache in `/tmp/soc-db-cache/` | World-readable cached data may be sensitive | Use user-private cache directory (`~/.cache/soc-db/` or `$SOC_DB_CACHE_DIR`) |
| User-Agent includes GitHub URL | Enables trivial blocking via UA fingerprint | Use per-source User-Agent rotation. Keep `SOC-DB/1.0` only for Wikipedia/cooperative sources |
| No certificates/API key rotation | Compromised key grants permanent access | Add key expiry; support key rotation via environment |
| Scraper error responses passed directly to parsers | Parsers receive Cloudflare/error pages as "valid data" | Error classification middleware; validate response is the expected page before parsing |
| `urlopen(req, timeout=30) # nosec` | SSRF if URL becomes user-controllable | URLs are hardcoded now but verify if any scraping endpoint accepts user input |
| GitHub Actions secrets leaked via fork PRs | Unauthorized scraping runs from forks | Restrict secret access to non-forked PRs; use `pull_request_target` with caution |

---

## "Looks Done But Isn't" Checklist

- [ ] **Deduplication:** Dedup by name-only appears to work but silently duplicates chips with different naming conventions. Verify: search for "Snapdragon 8 Gen 2" shows exactly one result with all aliases attached.
- [ ] **Rate limiting:** Adding `time.sleep(1)` appears to solve rate limiting but fails at 5000+ chips across multiple sources. Verify: run a test scraping 5 sources simultaneously; check for 429s.
- [ ] **Data provenance:** Chip records look complete but there's no way to answer "where did this value come from?". Verify: pick a random chip field and trace it to its source.
- [ ] **Scraper resilience:** Scraper appears to work but only tested against current page layout. Verify: take a snapshot of a source page, modify the column order, and confirm the scraper detects/crashes gracefully rather than producing wrong data.
- [ ] **API performance:** API returns data fast for 1761 chips but will degrade at 5000+. Verify: benchmark with 5000 synthetic chip records; measure p50/p95/p99 response times.
- [ ] **Auto-PR workflow:** Auto-opening PRs for data changes appears efficient but will flood reviewers. Verify: simulate one week of scraping; count how many PRs would be generated.
- [ ] **Legal compliance:** Scraper runs without errors, but there's no documented legal basis for each target. Verify: for each source, document the ToS, robots.txt, scraping policy, and legal risk assessment.
- [ ] **Freshness tracking:** Chips are updated regularly but there's no staleness alert. Verify: stop a source's scraper for 2 weeks; confirm the dashboard shows an alert for stale data.
- [ ] **ID stability:** Chips have stable-looking IDs, but they change if the source renames the chip. Verify: change a chip name in a Wikipedia redirect; confirm the database doesn't create a duplicate.
- [ ] **Multi-page scraping:** Scraper extracts 20 chips but the Wikipedia page has 50 across 3 pages. Verify: check for "next page" links or continuation tables in the page HTML.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| IP banned from target source | MEDIUM | Switch to pool of residential proxies; reduce rate; wait 24h before retrying |
| Duplicate chips merged incorrectly | HIGH | Restore from git history; implement proper dedup before re-attempting merge |
| Schema drift breaks scraper | MEDIUM | Manually inspect new page layout; update CSS selectors; add schema-drift test |
| API performance regression | LOW to MEDIUM | Profile, identify bottleneck (likely enrichment), add caching or lazy eval |
| Legal C&D from source | HIGH | Stop scraping that source immediately; archive existing data; document compliance |
| Data corruption from merge bug | HIGH | Rollback from git; replay scrape from known-good commit with fix |
| GitHub Pages corrupted by data script | CRITICAL | Restore `docs/` from git; add filesystem guard; verify deploy |
| Outdated chip data from failed scrape | LOW | Re-run failing scrape; if source is permanently changed, update scraper |
| Slug collision causes data loss | MEDIUM | Restore from git; implement UUID-based IDs; rebuild collision-free |
| Enrichment produces wrong inference | MEDIUM | Fix enrichment module; re-run enrichment on all affected chips; snapshot-test before/after |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Naive rate limiting → blocks | Phase 1 — Scraper Overhaul | Test: 5 simultaneous source scrapes → 0 429s |
| Schema drift → silent failure | Phase 1 (detection) + Phase 2 (alerting) | Test: modify HTML mock → alert fires, pipeline halts |
| Dedup nightmare → duplicates | Phase 3 — Dedup Pipeline | Test: same chip from 4 sources → 1 entry with 4 aliases |
| Data provenance loss → undebuggable | Phase 2 — Data Model Extension | Test: field-level `_source` tracked for every mutation |
| API perf regression → slow response | Phase 4 — Performance | Test: 5000 chips, p95 API response < 200ms |
| Auto-PR false positives → review burnout | Phase 5 — Auto-PR | Test: simulated scrape with 100 changes → < 5 human-review PRs |
| Legal exposure → cease-and-desist | Phase 0 — Legal Review | Gate: source compliance matrix signed off |
| Anti-bot systems blocking scrapers | Phase 1 — Scraper Tiers | Test: scrape Qualcomm dev site → actual chip data, not challenge page |
| Stale data inconsistency → churn | Phase 2 (schema) + Phase 5 (scheduling) | Test: source not scraped for 2× budget → staleness alert |
| Slug collisions → data loss | Phase 3 — Dedup Pipeline | Test: similar chip names → different canonical IDs |
| Enrichment performance → slow CI | Phase 4 — Performance Optimization | Test: full enrich of 5000 chips < 60s |
| GitHub Pages broken → site down | Phase 0 — Safety Guards | Gate: write guard in place; CI separation confirmed |

---

## Sources

- Wikipedia "Web scraping — Legal issues" (cases: *hiQ Labs v. LinkedIn*, *Craigslist v. 3Taps*, *eBay v. Bidder's Edge*, *Ryanair v. Billigfluege.de*, *QVC v. Resultly*)
- ScraperAPI "Best Practices for Web Scraping in 2026" (proxy rotation, headless browsers, TLS fingerprinting)
- Zyte "Web Scraping Best Practices" (IP rotation, request headers, session persistence, honeypot detection)
- Existing codebase analysis: `scraper_wikipedia.py`, `scraper_apple.py`, `common.py` (`fetch`, `write_vendor_file`, `_match_existing`, `slug`), `rate_limit.py`
- Project docs: `PROJECT.md` (v3.0 requirements, constraints), `CONCERNS.md` (technical debt, known issues)
- *Feist Publications v. Rural Telephone Service* (U.S. Supreme Court — facts not copyrightable)
- *Van Buren v. United States* (2021 U.S. Supreme Court — narrowing CFAA scope for authorized access)

---
*Pitfalls research for: soc-db v3.0 Full SoC Coverage — Multi-Source Data Collection Pipeline*
*Researched: 2026-07-19*
