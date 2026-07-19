# Scraping Compliance Matrix

**⚠ NOT LEGAL ADVICE:** This document records publicly available terms of service,
robots.txt directives, and scraping policies for informational purposes.
It does not constitute legal advice. Consult legal counsel for compliance guidance.

---

## Current Sources

| Source | URL | ToS Link | robots.txt Status | Data Scraped | Legal Basis | Risk | Scraper UA |
|--------|-----|----------|-------------------|--------------|-------------|------|------------|
| Wikipedia | en.wikipedia.org | [Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use) | `Disallow: /wiki/` (but `/w/api.php` is permitted) | Chip spec tables and infoboxes via API | CC-BY-SA license (explicitly permits reuse with attribution) | **Low** | `SOC-DB-Wikipedia/1.0` |
| Wikidata | wikidata.org | [CC0 Dedication](https://creativecommons.org/publicdomain/zero/1.0/) | `Disallow: /wiki/Special:` / `Allow: /wiki/Special:EntityData` | SPARQL queries for entity data | CC0 public domain dedication | **Low** | `SOC-DB-Wikidata/1.0` (via SPARQLWrapper) |
| Apple Tech Specs | apple.com | [ToS Section 4(i)](https://www.apple.com/legal/internet-services/terms/site.html) — prohibits scraping | `Disallow: /shop/` | Chip specs from press releases and tech spec pages | Press releases / publicly available specs (factual data not copyrightable) | **Medium** (no C&D received) | `SOC-DB-Apple/1.0 (+https://github.com/vitkuz573/soc-db)` |
| Linux DeviceTree | git.kernel.org (or github.com/Devicetree-Org) | GPL-2.0 license | N/A (git repository, no robots.txt) | SoC compatible strings, CPU cores | GPL-licensed code | **Low** | `SOC-DB-DeviceTree/1.0 (+https://github.com/vitkuz573/soc-db)` |

---

## Planned Sources (Future Phases)

| Source | URL | ToS Link | robots.txt Status | Data Scraped | Legal Basis | Risk | Scraper UA |
|--------|-----|----------|-------------------|--------------|-------------|------|------------|
| TechPowerUp | techpowerup.com | [ToS Section 6](https://www.techpowerup.com/terms/) — prohibits automated data collection | `Crawl-delay: 5` / `Disallow: /gpu-specs/` (archived pages) / `Allow: /specs/` | GPU/SoC spec tables | Fair use of factual specification data | **Medium** | `SOC-DB-TPU/1.0 (+https://github.com/vitkuz573/soc-db)` |
| NotebookCheck | notebookcheck.net | [ToS](https://www.notebookcheck.net/Imprint.245.0.html) — restricts commercial use | `Disallow: /` (broad disallow) | Benchmark scores | Fair use of factual benchmarks | **High** (broad robots.txt disallow) | `SOC-DB-NBC/1.0 (+https://github.com/vitkuz573/soc-db)` |
| Geekbench Browser | browser.geekbench.com | No explicit scraping prohibition; [API available](https://browser.geekbench.com/developer) | `Crawl-delay: 10` | Benchmark scores | Public benchmark database / API terms | **Low** (use official API where possible) | `SOC-DB-GB/1.0 (+https://github.com/vitkuz573/soc-db)` |
| Qualcomm Developer Network | qualcomm.com | Developer ToS requires [registration](https://developer.qualcomm.com/) | robots.txt not restrictive | Official chip spec pages | Developer ToS (review before scraping) | **Medium** (prefer official API/dataset) | `SOC-DB-Qualcomm/1.0 (+https://github.com/vitkuz573/soc-db)` |
| MediaTek | mediatek.com | [ToS](https://www.mediatek.com/terms-conditions) — prohibits automated access | robots.txt not tested | Dimensity/Helio product pages | Fair use of factual specs | **Medium** | `SOC-DB-MediaTek/1.0 (+https://github.com/vitkuz573/soc-db)` |
| Intel ARK | ark.intel.com | Product spec database (public datasheets) | `Allow: /content/` `Disallow: /search/` | Product specifications | Public product database | **Low-Medium** | `SOC-DB-Intel/1.0 (+https://github.com/vitkuz573/soc-db)` |
| AMD | amd.com | [ToS Section 5](https://www.amd.com/en/corporate/terms) — prohibits scraping | `Crawl-delay: 10` | Product spec pages | Fair use of factual specs | **Medium** | `SOC-DB-AMD/1.0 (+https://github.com/vitkuz573/soc-db)` |

---

## robots.txt Compliance Policy

- Before every scrape, the source's `robots.txt` is checked via the `RobotsChecker` module (see [src/soc_db/robots.py](../src/soc_db/robots.py))
- Disallowed paths are **never scraped**
- `Crawl-delay` directives are honored as minimum interval between requests
- `robots.txt` is cached per domain with a 24-hour TTL
- If `robots.txt` is unreachable, the fetch is **allowed by default** (fail-open for resilience)

---

## Source-Specific Notes

- **GSMArena / DeviceSpecifications:** NOT yet reviewed — legal review deferred to **Phase 14**. Do not scrape these sources until legal status is documented.
- **Wikipedia API** (`/w/api.php`) is preferred over scraping HTML directly — the API is explicitly permitted and provides structured data with proper attribution.
- **Linux DeviceTree** data is obtained from git tags, not live web scraping; the repository is openly licensed under GPL-2.0.
- **Apple Tech Specs:** Apple's ToS Section 4(i) prohibits scraping, but the data collected (clock speeds, core counts, GPU configurations) consists of factual specifications published in press releases. No cease-and-desist has been received. If a C&D is received, follow the C&D Response Plan below.
- **Geekbench Browser:** An official API is available for benchmark data. Prefer using the API over HTML scraping. The API has its own terms that must be reviewed before use.
- **Qualcomm Developer Network:** Qualcomm provides official documentation and software packages. Contact Qualcomm for structured access to chip specification data if scraping is not practical.

---

## C&D Response Plan

Upon receipt of a cease-and-desist communication from any data source:

1. **Halt immediately** — stop all scraping activity against the source domain within 1 hour of receipt
2. **Block the source** — add the source domain to the scraper configuration's blocklist (per-source disable without code changes)
3. **Preserve data** — archive all data obtained from that source in a separate branch. Do NOT delete — legal preservation hold applies
4. **Notify maintainers** — file a GitHub issue with the `[LEGAL]` tag describing the communication received and actions taken
5. **Evaluate alternatives** — identify and document alternative data sources to replace the blocked source
6. **Never resume** — do not resume scraping the source after a C&D without explicit written approval from legal counsel

---

## Jurisdictional Notes

### United States

- **Feist v. Rural (1991):** Facts are not copyrightable. Only the creative expression of facts can be protected. Pure factual data (clock speeds, core counts, process nodes) is not subject to copyright.
- **hiQ v. LinkedIn (2019, 9th Cir.):** Scraping publicly accessible data does not violate the CFAA (Computer Fraud and Abuse Act). This ruling applies to data that is not behind authentication.
- **Van Buren v. United States (2021):** The Supreme Court narrowed the CFAA's scope — "exceeds authorized access" does not cover using a system in a way that violates use restrictions (ToS violations are not CFAA violations).
- **State laws:** Some states (e.g., California) have computer trespass statutes that may apply differently. Consult counsel for specific state-law analysis.

### European Union

- **Database Directive (96/9/EC):** The EU's *sui generis* database right may protect databases where there has been substantial investment in obtaining, verifying, or presenting data. This applies even to factual databases. Scraping substantial portions of a database may infringe.
- **GDPR:** If any scraped data includes personal data (e.g., reviewer names, contact information), GDPR applies. Do not scrape personal data. Stick to hardware specification data only.
- **Text and Data Mining Exception (Art. 3-4 DSM Directive 2019/790):** Allows TDM for research and innovation purposes, but rightsholders can opt out via machine-readable means (robots.txt).

### United Kingdom

- Database rights similar to EU *sui generis* rights apply post-Brexit under the Copyright and Rights in Databases Regulations 1997.
- The UK has implemented the DSM Directive's TDM exception with modifications.

### General

- **Terms of Service:** ToS can create contractual obligations. Breach of ToS may give rise to a breach of contract claim, but this varies by jurisdiction. In the US, ToS violations alone are generally not CFAA violations (post-*Van Buren*).
- **Rate limiting:** Even where scraping is legally permitted, aggressive rate limiting may trigger technical blocks. Respect `Crawl-delay` directives and implement polite scraping intervals.
- **International:** If your scraper operates from a different jurisdiction than the target site, both sets of laws may apply. The above is a summary — consult legal counsel for your specific situation.

---

## Future Review Queue

| Source | Phase | Status | Notes |
|--------|-------|--------|-------|
| GSMArena | Phase 14 | Not yet reviewed | Requires ToS and robots.txt analysis |
| DeviceSpecifications | Phase 14 | Not yet reviewed | Requires ToS and robots.txt analysis |

---

*Document generated: 2026-07-19*
*Next review: When a new data source is added or when legal terms change for an existing source.*
