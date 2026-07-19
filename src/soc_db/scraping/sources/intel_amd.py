"""IntelAMDScraper — BaseScraper implementation for Intel and AMD processor specs.

Uses a comprehensive baseline data set of known Intel and AMD processors
(sourced from Intel ARK, AMD product pages, and Wikipedia) since the
official product listing pages are often unreliable for automated access.

Attempts live fetch first (via Intel ARK and AMD product pages) and falls
back to the baseline data if live scraping fails.

Extracts cores, threads, clock, boost, cache, TDP, memory, graphics,
socket, process node, and year.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from soc_db.common import extract_int, slug
from soc_db.scraping.base import BaseScraper, ChipScrapeResult
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# Intel ARK listing and AMD product pages
INTEL_ARK_URL = "https://ark.intel.com/content/www/us/en/ark.html"
AMD_PRODUCTS_URL = "https://www.amd.com/en/products/specifications"
INTEL_SPECS_URL = "https://www.intel.com/content/www/us/en/products/specs.html"
AMD_SPECS_URL = "https://www.amd.com/en/products/specifications/processors"

# ── Baseline Intel processor specs ──────────────────────────────────────
# Format: (name, vendor, model, cores, threads, clock_ghz, boost_ghz,
#           process_nm, tdp, l3_cache, gpu, year, memory_type)

INTEL_CHIPS: list[dict[str, Any]] = [
    # Core Ultra 200 series (Arrow Lake, 2024)
    {"name":"Intel Core Ultra 9 285K","vendor":"Intel","model":"285K","cores":24,"threads":24,"clock":3.7,"boost":5.7,"process_nm":3,"tdp":250,"l3_cache":"36 MB","gpu":"Intel Arc Graphics","year":2024,"socket":"LGA1851"},
    {"name":"Intel Core Ultra 7 265K","vendor":"Intel","model":"265K","cores":20,"threads":20,"clock":3.9,"boost":5.5,"process_nm":3,"tdp":250,"l3_cache":"30 MB","gpu":"Intel Arc Graphics","year":2024,"socket":"LGA1851"},
    {"name":"Intel Core Ultra 5 245K","vendor":"Intel","model":"245K","cores":14,"threads":14,"clock":4.2,"boost":5.2,"process_nm":3,"tdp":250,"l3_cache":"24 MB","gpu":"Intel Arc Graphics","year":2024,"socket":"LGA1851"},
    # Core 14th gen (Raptor Lake Refresh, 2023-2024)
    {"name":"Intel Core i9-14900K","vendor":"Intel","model":"i9-14900K","cores":24,"threads":32,"clock":3.2,"boost":6.0,"process_nm":7,"tdp":253,"l3_cache":"36 MB","gpu":"Intel UHD Graphics 770","year":2023,"socket":"LGA1700"},
    {"name":"Intel Core i7-14700K","vendor":"Intel","model":"i7-14700K","cores":20,"threads":28,"clock":3.4,"boost":5.6,"process_nm":7,"tdp":253,"l3_cache":"33 MB","gpu":"Intel UHD Graphics 770","year":2023,"socket":"LGA1700"},
    {"name":"Intel Core i5-14600K","vendor":"Intel","model":"i5-14600K","cores":14,"threads":20,"clock":3.5,"boost":5.3,"process_nm":7,"tdp":181,"l3_cache":"24 MB","gpu":"Intel UHD Graphics 770","year":2023,"socket":"LGA1700"},
    {"name":"Intel Core i5-14400","vendor":"Intel","model":"i5-14400","cores":10,"threads":16,"clock":2.5,"boost":4.7,"process_nm":7,"tdp":148,"l3_cache":"20 MB","gpu":"Intel UHD Graphics 730","year":2024,"socket":"LGA1700"},
    # Core 13th gen (Raptor Lake, 2022-2023)
    {"name":"Intel Core i9-13900K","vendor":"Intel","model":"i9-13900K","cores":24,"threads":32,"clock":3.0,"boost":5.8,"process_nm":7,"tdp":253,"l3_cache":"36 MB","gpu":"Intel UHD Graphics 770","year":2022,"socket":"LGA1700"},
    {"name":"Intel Core i7-13700K","vendor":"Intel","model":"i7-13700K","cores":16,"threads":24,"clock":3.4,"boost":5.4,"process_nm":7,"tdp":253,"l3_cache":"30 MB","gpu":"Intel UHD Graphics 770","year":2022,"socket":"LGA1700"},
    {"name":"Intel Core i5-13600K","vendor":"Intel","model":"i5-13600K","cores":14,"threads":20,"clock":3.5,"boost":5.1,"process_nm":7,"tdp":181,"l3_cache":"24 MB","gpu":"Intel UHD Graphics 770","year":2022,"socket":"LGA1700"},
    {"name":"Intel Core i5-13500","vendor":"Intel","model":"i5-13500","cores":14,"threads":20,"clock":2.5,"boost":4.8,"process_nm":7,"tdp":65,"l3_cache":"24 MB","gpu":"Intel UHD Graphics 770","year":2023,"socket":"LGA1700"},
    {"name":"Intel Core i3-13100","vendor":"Intel","model":"i3-13100","cores":4,"threads":8,"clock":3.4,"boost":4.5,"process_nm":7,"tdp":60,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 730","year":2023,"socket":"LGA1700"},
    # Core 12th gen (Alder Lake, 2021-2022)
    {"name":"Intel Core i9-12900K","vendor":"Intel","model":"i9-12900K","cores":16,"threads":24,"clock":3.2,"boost":5.2,"process_nm":10,"tdp":241,"l3_cache":"30 MB","gpu":"Intel UHD Graphics 770","year":2021,"socket":"LGA1700"},
    {"name":"Intel Core i7-12700K","vendor":"Intel","model":"i7-12700K","cores":12,"threads":20,"clock":3.6,"boost":5.0,"process_nm":10,"tdp":190,"l3_cache":"25 MB","gpu":"Intel UHD Graphics 770","year":2021,"socket":"LGA1700"},
    {"name":"Intel Core i5-12600K","vendor":"Intel","model":"i5-12600K","cores":10,"threads":16,"clock":3.7,"boost":4.9,"process_nm":10,"tdp":150,"l3_cache":"20 MB","gpu":"Intel UHD Graphics 770","year":2021,"socket":"LGA1700"},
    {"name":"Intel Core i5-12400","vendor":"Intel","model":"i5-12400","cores":6,"threads":12,"clock":2.5,"boost":4.4,"process_nm":10,"tdp":65,"l3_cache":"18 MB","gpu":"Intel UHD Graphics 730","year":2022,"socket":"LGA1700"},
    {"name":"Intel Core i3-12100","vendor":"Intel","model":"i3-12100","cores":4,"threads":8,"clock":3.3,"boost":4.3,"process_nm":10,"tdp":60,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 730","year":2022,"socket":"LGA1700"},
    # Core 11th gen (Rocket Lake, 2021)
    {"name":"Intel Core i9-11900K","vendor":"Intel","model":"i9-11900K","cores":8,"threads":16,"clock":3.5,"boost":5.3,"process_nm":14,"tdp":125,"l3_cache":"16 MB","gpu":"Intel UHD Graphics 750","year":2021,"socket":"LGA1200"},
    {"name":"Intel Core i7-11700K","vendor":"Intel","model":"i7-11700K","cores":8,"threads":16,"clock":3.6,"boost":5.0,"process_nm":14,"tdp":125,"l3_cache":"16 MB","gpu":"Intel UHD Graphics 750","year":2021,"socket":"LGA1200"},
    {"name":"Intel Core i5-11600K","vendor":"Intel","model":"i5-11600K","cores":6,"threads":12,"clock":3.9,"boost":4.9,"process_nm":14,"tdp":125,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 750","year":2021,"socket":"LGA1200"},
    # Core 10th gen (Comet Lake, 2020)
    {"name":"Intel Core i9-10900K","vendor":"Intel","model":"i9-10900K","cores":10,"threads":20,"clock":3.7,"boost":5.3,"process_nm":14,"tdp":125,"l3_cache":"20 MB","gpu":"Intel UHD Graphics 630","year":2020,"socket":"LGA1200"},
    {"name":"Intel Core i7-10700K","vendor":"Intel","model":"i7-10700K","cores":8,"threads":16,"clock":3.8,"boost":5.1,"process_nm":14,"tdp":125,"l3_cache":"16 MB","gpu":"Intel UHD Graphics 630","year":2020,"socket":"LGA1200"},
    {"name":"Intel Core i5-10600K","vendor":"Intel","model":"i5-10600K","cores":6,"threads":12,"clock":4.1,"boost":4.8,"process_nm":14,"tdp":125,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 630","year":2020,"socket":"LGA1200"},
    {"name":"Intel Core i3-10300","vendor":"Intel","model":"i3-10300","cores":4,"threads":8,"clock":3.7,"boost":4.4,"process_nm":14,"tdp":65,"l3_cache":"8 MB","gpu":"Intel UHD Graphics 630","year":2020,"socket":"LGA1200"},
    # Core 9th gen (Coffee Lake Refresh, 2019)
    {"name":"Intel Core i9-9900K","vendor":"Intel","model":"i9-9900K","cores":8,"threads":16,"clock":3.6,"boost":5.0,"process_nm":14,"tdp":95,"l3_cache":"16 MB","gpu":"Intel UHD Graphics 630","year":2018,"socket":"LGA1151"},
    {"name":"Intel Core i7-9700K","vendor":"Intel","model":"i7-9700K","cores":8,"threads":8,"clock":3.6,"boost":4.9,"process_nm":14,"tdp":95,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 630","year":2018,"socket":"LGA1151"},
    {"name":"Intel Core i5-9600K","vendor":"Intel","model":"i5-9600K","cores":6,"threads":6,"clock":3.7,"boost":4.6,"process_nm":14,"tdp":95,"l3_cache":"9 MB","gpu":"Intel UHD Graphics 630","year":2018,"socket":"LGA1151"},
    # Core 8th gen (Coffee Lake, 2017-2018)
    {"name":"Intel Core i7-8700K","vendor":"Intel","model":"i7-8700K","cores":6,"threads":12,"clock":3.7,"boost":4.7,"process_nm":14,"tdp":95,"l3_cache":"12 MB","gpu":"Intel UHD Graphics 630","year":2017,"socket":"LGA1151"},
    {"name":"Intel Core i5-8600K","vendor":"Intel","model":"i5-8600K","cores":6,"threads":6,"clock":3.6,"boost":4.3,"process_nm":14,"tdp":95,"l3_cache":"9 MB","gpu":"Intel UHD Graphics 630","year":2017,"socket":"LGA1151"},
    {"name":"Intel Core i3-8100","vendor":"Intel","model":"i3-8100","cores":4,"threads":4,"clock":3.6,"boost":0,"process_nm":14,"tdp":65,"l3_cache":"6 MB","gpu":"Intel UHD Graphics 630","year":2017,"socket":"LGA1151"},
    # Core 7th gen (Kaby Lake, 2017)
    {"name":"Intel Core i7-7700K","vendor":"Intel","model":"i7-7700K","cores":4,"threads":8,"clock":4.2,"boost":4.5,"process_nm":14,"tdp":91,"l3_cache":"8 MB","gpu":"Intel HD Graphics 630","year":2017,"socket":"LGA1151"},
    {"name":"Intel Core i5-7600K","vendor":"Intel","model":"i5-7600K","cores":4,"threads":4,"clock":3.8,"boost":4.2,"process_nm":14,"tdp":91,"l3_cache":"6 MB","gpu":"Intel HD Graphics 630","year":2017,"socket":"LGA1151"},
    # Core 6th gen (Skylake, 2015)
    {"name":"Intel Core i7-6700K","vendor":"Intel","model":"i7-6700K","cores":4,"threads":8,"clock":4.0,"boost":4.2,"process_nm":14,"tdp":91,"l3_cache":"8 MB","gpu":"Intel HD Graphics 530","year":2015,"socket":"LGA1151"},
    {"name":"Intel Core i5-6600K","vendor":"Intel","model":"i5-6600K","cores":4,"threads":4,"clock":3.5,"boost":3.9,"process_nm":14,"tdp":91,"l3_cache":"6 MB","gpu":"Intel HD Graphics 530","year":2015,"socket":"LGA1151"},
    # Mobile: Core HX (13th/14th gen mobile)
    {"name":"Intel Core i9-14900HX","vendor":"Intel","model":"i9-14900HX","cores":24,"threads":32,"clock":2.4,"boost":5.8,"process_nm":7,"tdp":157,"l3_cache":"36 MB","gpu":"Intel UHD Graphics","year":2024,"memory_type":"DDR5"},
    {"name":"Intel Core i7-14700HX","vendor":"Intel","model":"i7-14700HX","cores":20,"threads":28,"clock":2.1,"boost":5.5,"process_nm":7,"tdp":157,"l3_cache":"33 MB","gpu":"Intel UHD Graphics","year":2024,"memory_type":"DDR5"},
    {"name":"Intel Core i9-13980HX","vendor":"Intel","model":"i9-13980HX","cores":24,"threads":32,"clock":2.2,"boost":5.6,"process_nm":7,"tdp":157,"l3_cache":"36 MB","gpu":"Intel UHD Graphics","year":2023,"memory_type":"DDR5"},
    # Mobile: Core H/P/U series
    {"name":"Intel Core i7-13700H","vendor":"Intel","model":"i7-13700H","cores":14,"threads":20,"clock":3.7,"boost":5.0,"process_nm":7,"tdp":45,"l3_cache":"24 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i5-13500H","vendor":"Intel","model":"i5-13500H","cores":12,"threads":16,"clock":3.5,"boost":4.7,"process_nm":7,"tdp":45,"l3_cache":"18 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i7-1360P","vendor":"Intel","model":"i7-1360P","cores":12,"threads":16,"clock":2.8,"boost":5.0,"process_nm":7,"tdp":28,"l3_cache":"18 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i5-1340P","vendor":"Intel","model":"i5-1340P","cores":12,"threads":16,"clock":2.8,"boost":4.6,"process_nm":7,"tdp":28,"l3_cache":"12 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i7-1365U","vendor":"Intel","model":"i7-1365U","cores":10,"threads":12,"clock":2.8,"boost":5.2,"process_nm":7,"tdp":15,"l3_cache":"12 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i5-1335U","vendor":"Intel","model":"i5-1335U","cores":10,"threads":12,"clock":2.5,"boost":4.6,"process_nm":7,"tdp":15,"l3_cache":"12 MB","gpu":"Intel Iris Xe Graphics","year":2023,"memory_type":"DDR5"},
    # Mobile 12th gen
    {"name":"Intel Core i9-12900H","vendor":"Intel","model":"i9-12900H","cores":14,"threads":20,"clock":3.8,"boost":5.0,"process_nm":10,"tdp":45,"l3_cache":"24 MB","gpu":"Intel Iris Xe Graphics","year":2022,"memory_type":"DDR5"},
    {"name":"Intel Core i7-12700H","vendor":"Intel","model":"i7-12700H","cores":14,"threads":20,"clock":3.5,"boost":4.7,"process_nm":10,"tdp":45,"l3_cache":"24 MB","gpu":"Intel Iris Xe Graphics","year":2022,"memory_type":"DDR5"},
    {"name":"Intel Core i5-12500H","vendor":"Intel","model":"i5-12500H","cores":12,"threads":16,"clock":3.3,"boost":4.5,"process_nm":10,"tdp":45,"l3_cache":"18 MB","gpu":"Intel Iris Xe Graphics","year":2022,"memory_type":"DDR5"},
    {"name":"Intel Core i7-1260P","vendor":"Intel","model":"i7-1260P","cores":12,"threads":16,"clock":2.1,"boost":4.7,"process_nm":10,"tdp":28,"l3_cache":"18 MB","gpu":"Intel Iris Xe Graphics","year":2022,"memory_type":"DDR5"},
    {"name":"Intel Core i5-1240P","vendor":"Intel","model":"i5-1240P","cores":12,"threads":16,"clock":2.5,"boost":4.4,"process_nm":10,"tdp":28,"l3_cache":"12 MB","gpu":"Intel Iris Xe Graphics","year":2022,"memory_type":"DDR5"},
    # Xeon Scalable (4th gen, Sapphire Rapids, 2023)
    {"name":"Intel Xeon Platinum 8490H","vendor":"Intel","model":"8490H","cores":60,"threads":120,"clock":1.9,"boost":3.5,"process_nm":10,"tdp":350,"l3_cache":"112.5 MB","year":2023,"socket":"LGA4677"},
    {"name":"Intel Xeon Gold 6418H","vendor":"Intel","model":"6418H","cores":24,"threads":48,"clock":2.1,"boost":4.0,"process_nm":10,"tdp":185,"l3_cache":"60 MB","year":2023,"socket":"LGA4677"},
    {"name":"Intel Xeon Silver 4416+","vendor":"Intel","model":"4416+","cores":20,"threads":40,"clock":2.0,"boost":3.9,"process_nm":10,"tdp":165,"l3_cache":"37.5 MB","year":2023,"socket":"LGA4677"},
    # Xeon W (Workstation)
    {"name":"Intel Xeon w9-3495X","vendor":"Intel","model":"w9-3495X","cores":56,"threads":112,"clock":1.9,"boost":4.8,"process_nm":10,"tdp":420,"l3_cache":"105 MB","year":2023,"socket":"LGA4677"},
    {"name":"Intel Xeon w7-2495X","vendor":"Intel","model":"w7-2495X","cores":24,"threads":48,"clock":2.5,"boost":4.8,"process_nm":10,"tdp":225,"l3_cache":"45 MB","year":2023,"socket":"LGA4677"},
    # Xeon E-2400 (2023)
    {"name":"Intel Xeon E-2488","vendor":"Intel","model":"E-2488","cores":8,"threads":16,"clock":3.2,"boost":5.6,"process_nm":10,"tdp":95,"l3_cache":"24 MB","year":2023,"socket":"LGA1700"},
    # Intel Core HX 13th gen
    {"name":"Intel Core i9-13950HX","vendor":"Intel","model":"i9-13950HX","cores":24,"threads":32,"clock":2.2,"boost":5.5,"process_nm":7,"tdp":157,"l3_cache":"36 MB","gpu":"Intel UHD Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i7-13850HX","vendor":"Intel","model":"i7-13850HX","cores":20,"threads":28,"clock":2.4,"boost":5.3,"process_nm":7,"tdp":157,"l3_cache":"30 MB","gpu":"Intel UHD Graphics","year":2023,"memory_type":"DDR5"},
    {"name":"Intel Core i5-13600HX","vendor":"Intel","model":"i5-13600HX","cores":14,"threads":20,"clock":2.6,"boost":4.8,"process_nm":7,"tdp":157,"l3_cache":"24 MB","gpu":"Intel UHD Graphics","year":2023,"memory_type":"DDR5"},
]

# ── Baseline AMD processor specs ────────────────────────────────────────

AMD_CHIPS: list[dict[str, Any]] = [
    # Ryzen 9000 series (Granite Ridge, 2024)
    {"name":"AMD Ryzen 9 9950X","vendor":"AMD","model":"9950X","cores":16,"threads":32,"clock":4.3,"boost":5.7,"process_nm":4,"tdp":170,"l3_cache":"64 MB","gpu":"None","year":2024,"socket":"AM5"},
    {"name":"AMD Ryzen 9 9900X","vendor":"AMD","model":"9900X","cores":12,"threads":24,"clock":4.4,"boost":5.6,"process_nm":4,"tdp":120,"l3_cache":"64 MB","gpu":"None","year":2024,"socket":"AM5"},
    {"name":"AMD Ryzen 7 9700X","vendor":"AMD","model":"9700X","cores":8,"threads":16,"clock":3.8,"boost":5.5,"process_nm":4,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2024,"socket":"AM5"},
    {"name":"AMD Ryzen 5 9600X","vendor":"AMD","model":"9600X","cores":6,"threads":12,"clock":3.9,"boost":5.4,"process_nm":4,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2024,"socket":"AM5"},
    # Ryzen 7000 series (Raphael, 2022-2023)
    {"name":"AMD Ryzen 9 7950X","vendor":"AMD","model":"7950X","cores":16,"threads":32,"clock":4.5,"boost":5.7,"process_nm":5,"tdp":170,"l3_cache":"64 MB","gpu":"AMD Radeon Graphics","year":2022,"socket":"AM5"},
    {"name":"AMD Ryzen 9 7900X","vendor":"AMD","model":"7900X","cores":12,"threads":24,"clock":4.7,"boost":5.6,"process_nm":5,"tdp":170,"l3_cache":"64 MB","gpu":"AMD Radeon Graphics","year":2022,"socket":"AM5"},
    {"name":"AMD Ryzen 7 7800X3D","vendor":"AMD","model":"7800X3D","cores":8,"threads":16,"clock":4.2,"boost":5.0,"process_nm":5,"tdp":120,"l3_cache":"96 MB","gpu":"AMD Radeon Graphics","year":2023,"socket":"AM5"},
    {"name":"AMD Ryzen 7 7700X","vendor":"AMD","model":"7700X","cores":8,"threads":16,"clock":4.5,"boost":5.4,"process_nm":5,"tdp":105,"l3_cache":"32 MB","gpu":"AMD Radeon Graphics","year":2022,"socket":"AM5"},
    {"name":"AMD Ryzen 5 7600X","vendor":"AMD","model":"7600X","cores":6,"threads":12,"clock":4.7,"boost":5.3,"process_nm":5,"tdp":105,"l3_cache":"32 MB","gpu":"AMD Radeon Graphics","year":2022,"socket":"AM5"},
    {"name":"AMD Ryzen 5 7500F","vendor":"AMD","model":"7500F","cores":6,"threads":12,"clock":3.7,"boost":5.0,"process_nm":5,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2023,"socket":"AM5"},
    # Ryzen 7000 X3D series
    {"name":"AMD Ryzen 9 7950X3D","vendor":"AMD","model":"7950X3D","cores":16,"threads":32,"clock":4.2,"boost":5.7,"process_nm":5,"tdp":120,"l3_cache":"128 MB","gpu":"AMD Radeon Graphics","year":2023,"socket":"AM5"},
    {"name":"AMD Ryzen 9 7900X3D","vendor":"AMD","model":"7900X3D","cores":12,"threads":24,"clock":4.4,"boost":5.6,"process_nm":5,"tdp":120,"l3_cache":"128 MB","gpu":"AMD Radeon Graphics","year":2023,"socket":"AM5"},
    # Ryzen 5000 series (Vermeer, 2020-2022)
    {"name":"AMD Ryzen 9 5950X","vendor":"AMD","model":"5950X","cores":16,"threads":32,"clock":3.4,"boost":4.9,"process_nm":7,"tdp":105,"l3_cache":"64 MB","gpu":"None","year":2020,"socket":"AM4"},
    {"name":"AMD Ryzen 9 5900X","vendor":"AMD","model":"5900X","cores":12,"threads":24,"clock":3.7,"boost":4.8,"process_nm":7,"tdp":105,"l3_cache":"64 MB","gpu":"None","year":2020,"socket":"AM4"},
    {"name":"AMD Ryzen 7 5800X3D","vendor":"AMD","model":"5800X3D","cores":8,"threads":16,"clock":3.4,"boost":4.5,"process_nm":7,"tdp":105,"l3_cache":"96 MB","gpu":"None","year":2022,"socket":"AM4"},
    {"name":"AMD Ryzen 7 5800X","vendor":"AMD","model":"5800X","cores":8,"threads":16,"clock":3.8,"boost":4.7,"process_nm":7,"tdp":105,"l3_cache":"32 MB","gpu":"None","year":2020,"socket":"AM4"},
    {"name":"AMD Ryzen 5 5600X","vendor":"AMD","model":"5600X","cores":6,"threads":12,"clock":3.7,"boost":4.6,"process_nm":7,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2020,"socket":"AM4"},
    {"name":"AMD Ryzen 5 5500","vendor":"AMD","model":"5500","cores":6,"threads":12,"clock":3.6,"boost":4.2,"process_nm":7,"tdp":65,"l3_cache":"16 MB","gpu":"None","year":2022,"socket":"AM4"},
    {"name":"AMD Ryzen 3 5300G","vendor":"AMD","model":"5300G","cores":4,"threads":8,"clock":4.0,"boost":4.2,"process_nm":7,"tdp":65,"l3_cache":"8 MB","gpu":"AMD Radeon Graphics","year":2021,"socket":"AM4"},
    # Ryzen 5000G (Cezanne APU)
    {"name":"AMD Ryzen 7 5700G","vendor":"AMD","model":"5700G","cores":8,"threads":16,"clock":3.8,"boost":4.6,"process_nm":7,"tdp":65,"l3_cache":"16 MB","gpu":"AMD Radeon Graphics","year":2021,"socket":"AM4"},
    {"name":"AMD Ryzen 5 5600G","vendor":"AMD","model":"5600G","cores":6,"threads":12,"clock":3.9,"boost":4.4,"process_nm":7,"tdp":65,"l3_cache":"16 MB","gpu":"AMD Radeon Graphics","year":2021,"socket":"AM4"},
    # Ryzen 3000 series (Matisse, 2019)
    {"name":"AMD Ryzen 9 3950X","vendor":"AMD","model":"3950X","cores":16,"threads":32,"clock":3.5,"boost":4.7,"process_nm":7,"tdp":105,"l3_cache":"64 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 9 3900X","vendor":"AMD","model":"3900X","cores":12,"threads":24,"clock":3.8,"boost":4.6,"process_nm":7,"tdp":105,"l3_cache":"64 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 7 3800X","vendor":"AMD","model":"3800X","cores":8,"threads":16,"clock":3.9,"boost":4.5,"process_nm":7,"tdp":105,"l3_cache":"32 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 7 3700X","vendor":"AMD","model":"3700X","cores":8,"threads":16,"clock":3.6,"boost":4.4,"process_nm":7,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 5 3600X","vendor":"AMD","model":"3600X","cores":6,"threads":12,"clock":3.8,"boost":4.4,"process_nm":7,"tdp":95,"l3_cache":"32 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 5 3600","vendor":"AMD","model":"3600","cores":6,"threads":12,"clock":3.6,"boost":4.2,"process_nm":7,"tdp":65,"l3_cache":"32 MB","gpu":"None","year":2019,"socket":"AM4"},
    {"name":"AMD Ryzen 3 3300X","vendor":"AMD","model":"3300X","cores":4,"threads":8,"clock":3.8,"boost":4.3,"process_nm":7,"tdp":65,"l3_cache":"16 MB","gpu":"None","year":2020,"socket":"AM4"},
    # Ryzen 5000 mobile (Lucienne/Cezanne, 2021-2022)
    {"name":"AMD Ryzen 9 5980HX","vendor":"AMD","model":"5980HX","cores":8,"threads":16,"clock":3.3,"boost":4.8,"process_nm":7,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon Graphics","year":2021,"memory_type":"DDR4"},
    {"name":"AMD Ryzen 7 5800H","vendor":"AMD","model":"5800H","cores":8,"threads":16,"clock":3.2,"boost":4.4,"process_nm":7,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon Graphics","year":2021,"memory_type":"DDR4"},
    {"name":"AMD Ryzen 5 5600H","vendor":"AMD","model":"5600H","cores":6,"threads":12,"clock":3.3,"boost":4.2,"process_nm":7,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon Graphics","year":2021,"memory_type":"DDR4"},
    {"name":"AMD Ryzen 7 5700U","vendor":"AMD","model":"5700U","cores":8,"threads":16,"clock":1.8,"boost":4.3,"process_nm":7,"tdp":15,"l3_cache":"8 MB","gpu":"AMD Radeon Graphics","year":2021,"memory_type":"DDR4"},
    {"name":"AMD Ryzen 5 5500U","vendor":"AMD","model":"5500U","cores":6,"threads":12,"clock":2.1,"boost":4.0,"process_nm":7,"tdp":15,"l3_cache":"8 MB","gpu":"AMD Radeon Graphics","year":2021,"memory_type":"DDR4"},
    # Ryzen 6000 mobile (Rembrandt, 2022)
    {"name":"AMD Ryzen 9 6980HX","vendor":"AMD","model":"6980HX","cores":8,"threads":16,"clock":3.3,"boost":5.0,"process_nm":6,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon 680M","year":2022,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 7 6800H","vendor":"AMD","model":"6800H","cores":8,"threads":16,"clock":3.2,"boost":4.7,"process_nm":6,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon 680M","year":2022,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 5 6600H","vendor":"AMD","model":"6600H","cores":6,"threads":12,"clock":3.3,"boost":4.5,"process_nm":6,"tdp":45,"l3_cache":"16 MB","gpu":"AMD Radeon 660M","year":2022,"memory_type":"DDR5"},
    # Ryzen 7000 mobile (Phoenix/Dragon Range, 2023)
    {"name":"AMD Ryzen 9 7945HX","vendor":"AMD","model":"7945HX","cores":16,"threads":32,"clock":2.5,"boost":5.4,"process_nm":5,"tdp":55,"l3_cache":"64 MB","gpu":"None","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 9 7940HS","vendor":"AMD","model":"7940HS","cores":8,"threads":16,"clock":4.0,"boost":5.2,"process_nm":4,"tdp":35,"l3_cache":"16 MB","gpu":"AMD Radeon 780M","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 7 7840HS","vendor":"AMD","model":"7840HS","cores":8,"threads":16,"clock":3.8,"boost":5.1,"process_nm":4,"tdp":35,"l3_cache":"16 MB","gpu":"AMD Radeon 780M","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 7 7745HX","vendor":"AMD","model":"7745HX","cores":8,"threads":16,"clock":3.6,"boost":5.1,"process_nm":5,"tdp":55,"l3_cache":"32 MB","gpu":"None","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 5 7640HS","vendor":"AMD","model":"7640HS","cores":6,"threads":12,"clock":4.3,"boost":5.0,"process_nm":4,"tdp":35,"l3_cache":"16 MB","gpu":"AMD Radeon 760M","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 5 7545U","vendor":"AMD","model":"7545U","cores":6,"threads":12,"clock":3.2,"boost":4.9,"process_nm":4,"tdp":15,"l3_cache":"16 MB","gpu":"AMD Radeon 740M","year":2023,"memory_type":"DDR5"},
    # Ryzen 8000 mobile (Hawk Point, 2024)
    {"name":"AMD Ryzen 9 8945HS","vendor":"AMD","model":"8945HS","cores":8,"threads":16,"clock":4.0,"boost":5.2,"process_nm":4,"tdp":35,"l3_cache":"16 MB","gpu":"AMD Radeon 780M","year":2024,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 7 8845HS","vendor":"AMD","model":"8845HS","cores":8,"threads":16,"clock":3.8,"boost":5.1,"process_nm":4,"tdp":35,"l3_cache":"16 MB","gpu":"AMD Radeon 780M","year":2024,"memory_type":"DDR5"},
    # Threadripper (2023-2024)
    {"name":"AMD Ryzen Threadripper 7980X","vendor":"AMD","model":"7980X","cores":64,"threads":128,"clock":3.2,"boost":5.1,"process_nm":5,"tdp":350,"l3_cache":"320 MB","gpu":"None","year":2023,"socket":"sTR5"},
    {"name":"AMD Ryzen Threadripper 7970X","vendor":"AMD","model":"7970X","cores":32,"threads":64,"clock":4.0,"boost":5.3,"process_nm":5,"tdp":350,"l3_cache":"160 MB","gpu":"None","year":2023,"socket":"sTR5"},
    {"name":"AMD Ryzen Threadripper 7960X","vendor":"AMD","model":"7960X","cores":24,"threads":48,"clock":4.2,"boost":5.3,"process_nm":5,"tdp":350,"l3_cache":"160 MB","gpu":"None","year":2023,"socket":"sTR5"},
    # EPYC 9004 (Genoa/Bergamo, 2022-2023)
    {"name":"AMD EPYC 9654","vendor":"AMD","model":"9654","cores":96,"threads":192,"clock":2.4,"boost":3.7,"process_nm":5,"tdp":360,"l3_cache":"384 MB","gpu":"None","year":2022,"socket":"SP5"},
    {"name":"AMD EPYC 9554","vendor":"AMD","model":"9554","cores":64,"threads":128,"clock":3.1,"boost":3.75,"process_nm":5,"tdp":360,"l3_cache":"256 MB","gpu":"None","year":2022,"socket":"SP5"},
    {"name":"AMD EPYC 9454","vendor":"AMD","model":"9454","cores":48,"threads":96,"clock":2.75,"boost":3.8,"process_nm":5,"tdp":290,"l3_cache":"256 MB","gpu":"None","year":2022,"socket":"SP5"},
    {"name":"AMD EPYC 9334","vendor":"AMD","model":"9334","cores":32,"threads":64,"clock":2.7,"boost":3.9,"process_nm":5,"tdp":240,"l3_cache":"256 MB","gpu":"None","year":2022,"socket":"SP5"},
    {"name":"AMD EPYC 9224","vendor":"AMD","model":"9224","cores":24,"threads":48,"clock":2.5,"boost":3.7,"process_nm":5,"tdp":200,"l3_cache":"64 MB","gpu":"None","year":2022,"socket":"SP5"},
    # EPYC 8004 (Siena, 2023)
    {"name":"AMD EPYC 8534P","vendor":"AMD","model":"8534P","cores":64,"threads":128,"clock":2.3,"boost":3.1,"process_nm":5,"tdp":200,"l3_cache":"128 MB","gpu":"None","year":2023,"socket":"SP6"},
    {"name":"AMD EPYC 8324P","vendor":"AMD","model":"8324P","cores":32,"threads":64,"clock":2.65,"boost":3.0,"process_nm":5,"tdp":180,"l3_cache":"128 MB","gpu":"None","year":2023,"socket":"SP6"},
    # APU: Phoenix 7040 series
    {"name":"AMD Ryzen 7 7840U","vendor":"AMD","model":"7840U","cores":8,"threads":16,"clock":3.3,"boost":5.1,"process_nm":4,"tdp":28,"l3_cache":"16 MB","gpu":"AMD Radeon 780M","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 5 7640U","vendor":"AMD","model":"7640U","cores":6,"threads":12,"clock":3.5,"boost":4.9,"process_nm":4,"tdp":28,"l3_cache":"16 MB","gpu":"AMD Radeon 760M","year":2023,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 3 7440U","vendor":"AMD","model":"7440U","cores":4,"threads":8,"clock":3.0,"boost":4.7,"process_nm":4,"tdp":28,"l3_cache":"8 MB","gpu":"AMD Radeon 740M","year":2023,"memory_type":"DDR5"},
    # Strix Point / Ryzen AI 300 (2024)
    {"name":"AMD Ryzen AI 9 HX 370","vendor":"AMD","model":"HX 370","cores":12,"threads":24,"clock":3.3,"boost":5.1,"process_nm":4,"tdp":28,"l3_cache":"24 MB","gpu":"AMD Radeon 890M","year":2024,"memory_type":"DDR5"},
    {"name":"AMD Ryzen AI 9 365","vendor":"AMD","model":"365","cores":10,"threads":20,"clock":3.0,"boost":5.0,"process_nm":4,"tdp":28,"l3_cache":"24 MB","gpu":"AMD Radeon 880M","year":2024,"memory_type":"DDR5"},
    # Ryzen 7000 mobile (Mendocino, 2022)
    {"name":"AMD Ryzen 5 7520U","vendor":"AMD","model":"7520U","cores":4,"threads":8,"clock":2.8,"boost":4.3,"process_nm":6,"tdp":15,"l3_cache":"4 MB","gpu":"AMD Radeon 610M","year":2022,"memory_type":"DDR5"},
    {"name":"AMD Ryzen 3 7320U","vendor":"AMD","model":"7320U","cores":4,"threads":8,"clock":2.4,"boost":4.1,"process_nm":6,"tdp":15,"l3_cache":"4 MB","gpu":"AMD Radeon 610M","year":2022,"memory_type":"DDR5"},
]

# All baseline chips indexed by model for dedup
BASELINE_CHIPS: list[dict[str, Any]] = INTEL_CHIPS + AMD_CHIPS

# Vendor detection from processor name
INTEL_PREFIXES = ["intel", "core", "xeon", "pentium", "celeron", "atom", "xeon phi", "core ultra"]
AMD_PREFIXES = ["amd", "ryzen", "epyc", "threadripper", "athlon", "sempron", "fx-", "a-series"]


def detect_vendor(name: str) -> str:
    """Detect vendor (Intel or AMD) from CPU name string."""
    name_lower = name.lower().strip()
    for prefix in INTEL_PREFIXES:
        if name_lower.startswith(prefix):
            return "Intel"
    for prefix in AMD_PREFIXES:
        if name_lower.startswith(prefix):
            return "AMD"
    return "Unknown"


def parse_core_thread(text: str) -> tuple[int | None, int | None]:
    """Parse cores and threads from text like '8 / 16' or '8'."""
    parts = re.findall(r"\d+", text)
    if not parts:
        return None, None
    cores = int(parts[0])
    threads = int(parts[1]) if len(parts) > 1 else cores
    return cores, threads


def parse_clock(text: str) -> tuple[float | None, float | None]:
    """Parse base clock and boost clock from text like '3.4 GHz / 5.4 GHz'."""
    nums = re.findall(r"([\d.]+)\s*GHz", text, re.IGNORECASE)
    if not nums:
        return None, None
    base = float(nums[0])
    boost = float(nums[1]) if len(nums) > 1 else None
    return base, boost


def parse_tdp(text: str) -> int | None:
    """Parse TDP value from text like '65 W' or '15W'."""
    m = re.search(r"(\d+)\s*W", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def parse_cache_size(text: str) -> str | None:
    """Parse cache size from text like '30 MB' or '1 MB (per core)'."""
    m = re.search(r"(\d+)\s*(MB|KB|GB)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def parse_memory_max(text: str) -> str | None:
    """Parse memory max from text like '128 GB' or 'Up to 128 GB'."""
    m = re.search(r"(?:Up to\s+)?(\d+)\s*(GB|TB)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return None


def parse_process_node(text: str) -> int | None:
    """Parse process node from text like '7 nm' or 'Intel 7'."""
    m = re.search(r"(\d+)\s*nm", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"Intel\s+(\d+)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        mapping = {7: 10, 4: 7, 3: 5, 20: 14, 22: 14}
        return mapping.get(val)
    return None


# ── Scraper class ───────────────────────────────────────────────────────────


class IntelAMDScraper(BaseScraper):
    """Scraper for Intel and AMD processor specifications.

    Attempts live fetch from Intel ARK and AMD product pages first.
    Falls back to a comprehensive baseline dataset if live scraping fails.
    """

    SOURCE_ID = "intel_amd"
    VENDORS = ["Intel", "AMD"]
    PRIORITY = 30

    RATE_LIMIT_CONFIG: dict[str, float | int] = {
        "requests_per_sec": 1.0,
        "burst": 3,
        "backoff_factor": 2.0,
        "max_retries": 3,
        "min_wait": 0.5,
        "max_wait": 30.0,
        "jitter": True,
    }

    def __init__(
        self,
        robots_checker=None,
        rate_limiter=None,
    ) -> None:
        super().__init__(robots_checker, rate_limiter)
        self._http = HTTPSource(rate_limiter=self._rate_limiter, cache_ttl=86400)

    # ── fetch ───────────────────────────────────────────────────────────

    def fetch(self) -> dict[str, str]:
        """Fetch Intel and AMD product pages; return empty if unavailable.

        Uses baseline data as primary source since official product listing
        pages are unreliable for automated access.  Attempts a quick live
        fetch but does not block on slow responses.

        Returns:
            Dict mapping source label to HTML content (usually empty).
        """
        pages: dict[str, str] = {}

        # Quick live fetch attempt — short timeout, don't block
        import httpx as _httpx

        for label, url in [("intel", INTEL_SPECS_URL), ("amd", AMD_SPECS_URL)]:
            logger.info("[IntelAMDScraper] Quick fetch attempt for %s: %s", label, url)
            try:
                with _httpx.Client(
                    follow_redirects=True, timeout=10.0
                ) as client:
                    resp = client.get(
                        url,
                        headers={"User-Agent": self.user_agent},
                    )
                    if resp.status_code == 200 and len(resp.text) > 1000:
                        pages[label] = resp.text
                        logger.info("[IntelAMDScraper] Live fetch OK for %s", label)
            except Exception as exc:
                logger.debug("[IntelAMDScraper] Quick fetch failed for %s: %s", label, exc)

        logger.info("[IntelAMDScraper] Using baseline dataset as primary source")
        return pages

    # ── parse ───────────────────────────────────────────────────────────

    def parse(self, raw: dict[str, str]) -> list[ChipScrapeResult]:
        """Parse fetched HTML or return baseline data.

        If live HTML was fetched successfully, parses it.  Otherwise,
        returns the baseline dataset of known Intel/AMD processors.
        """
        results: list[ChipScrapeResult] = []
        seen_ids: set[str] = set()

        # Try parsing live HTML for each source
        for source_label, html in raw.items():
            soup = BeautifulSoup(html, "html.parser")
            chips_on_page = self._parse_page(soup, source_label)
            for chip in chips_on_page:
                chip_id = chip.get("id", "")
                if chip_id and chip_id not in seen_ids:
                    seen_ids.add(chip_id)
                    vendor = detect_vendor(chip.get("name", ""))
                    results.append(
                        ChipScrapeResult(
                            name=chip.get("name", ""),
                            vendor=vendor,
                            model=chip.get("model"),
                            fields=dict(chip),
                            source_id=self.SOURCE_ID,
                        )
                    )

        # Fallback to baseline data if live parsing yielded nothing
        if not results:
            logger.info("[IntelAMDScraper] Using baseline dataset (%d chips)", len(BASELINE_CHIPS))
            for chip in BASELINE_CHIPS:
                chip_id = slug(chip.get("name", ""), chip.get("model", ""))
                if chip_id and chip_id not in seen_ids:
                    seen_ids.add(chip_id)
                    chip_copy = dict(chip)
                    chip_copy["id"] = chip_id
                    chip_copy["source"] = self.SOURCE_ID
                    results.append(
                        ChipScrapeResult(
                            name=chip_copy.get("name", ""),
                            vendor=chip_copy.get("vendor", "Unknown"),
                            model=chip_copy.get("model"),
                            fields=chip_copy,
                            source_id=self.SOURCE_ID,
                        )
                    )

        logger.info(
            "[IntelAMDScraper] Produced %d chip(s)", len(results)
        )
        return results

    # ── internal helpers ─────────────────────────────────────────────────

    def _parse_page(self, soup: BeautifulSoup, source_label: str) -> list[dict[str, Any]]:
        """Parse a single page for processor chip data."""
        chips: list[dict[str, Any]] = []

        for table in soup.find_all("table"):
            chip = self._parse_spec_table(table, source_label)
            if chip:
                chips.append(chip)

        for article in soup.find_all(
            ["article", "div", "section", "li"],
            class_=re.compile(r"(product|processor|chip|card|item)", re.I),
        ):
            chip = self._parse_article(article, source_label)
            if chip:
                chips.append(chip)

        return chips

    def _parse_spec_table(self, table: Any, source_label: str) -> dict[str, Any] | None:
        """Parse a spec table for processor data."""
        rows = table.find_all("tr")
        chip: dict[str, Any] = {}
        name_found = False

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(" ", strip=True).lower()
            val = cells[1].get_text(" ", strip=True)

            if not key or not val or val in ("—", "-", "", "N/A"):
                continue

            if any(kw in key for kw in ("processor", "name", "product", "model")):
                name = val.strip()
                model = self._extract_model(name)
                chip["name"] = name
                chip["vendor"] = detect_vendor(name)
                chip["model"] = model or name
                chip["id"] = slug(name, model or "")
                name_found = True

            if not name_found:
                continue

            self._apply_spec_key(chip, key, val, source_label)

        if not name_found:
            return None

        return chip

    def _parse_article(self, article: Any, source_label: str) -> dict[str, Any] | None:
        """Parse a product article for processor data."""
        text = article.get_text(" ", strip=True)
        if not text:
            return None

        name = self._find_processor_name(text)
        if not name:
            return None

        model = self._extract_model(name)
        chip: dict[str, Any] = {
            "name": name,
            "vendor": detect_vendor(name),
            "model": model or name,
            "id": slug(name, model or ""),
        }

        ct_match = re.search(
            r"(?:cores?|threads?)\s*:?\s*(\d+)\s*/\s*(\d+)|(\d+)\s*/\s*(\d+)\s*(?:cores?|threads?)",
            text, re.IGNORECASE,
        )
        if ct_match:
            chip["cores"] = int(ct_match.group(1) or ct_match.group(3))
            chip["threads"] = int(ct_match.group(2) or ct_match.group(4))
        elif not ct_match:
            cores_match = re.search(r"(\d+)\s*(?:-core|cores?)", text, re.IGNORECASE)
            if cores_match:
                chip["cores"] = int(cores_match.group(1))

        base, boost = parse_clock(text)
        if base is not None:
            chip["clock"] = base
        if boost is not None:
            chip["boost"] = boost

        tdp = parse_tdp(text)
        if tdp is not None:
            chip["tdp"] = tdp

        proc_nm = parse_process_node(text)
        if proc_nm is not None:
            chip["process_nm"] = proc_nm

        l2 = re.search(r"L2\s*(?:cache\s+)?(\d+\s*(?:MB|KB))", text, re.IGNORECASE)
        if l2:
            chip["l2_cache"] = l2.group(1)
        l3 = re.search(r"L3\s*(?:cache\s+)?(\d+\s*(?:MB|KB))", text, re.IGNORECASE)
        if l3:
            chip["l3_cache"] = l3.group(1)

        mem_match = re.search(r"(DDR\d|LPDDR\d)", text, re.IGNORECASE)
        if mem_match:
            chip["memory_type"] = mem_match.group(1).upper()
        mem_max = parse_memory_max(text)
        if mem_max:
            chip["memory_max"] = mem_max

        gpu_match = re.search(
            r"(Intel\s+(UHD|Iris|Arc)\s+Graphics[\s\w]*|AMD\s+Radeon\s+(Graphics|HD)\s?[\w]*)",
            text, re.IGNORECASE,
        )
        if gpu_match:
            chip["gpu"] = gpu_match.group(0).strip()

        socket_match = re.search(r"(LGA\s*\d{3,}|Socket\s+\w+|AM\d|sTR\d|SP\d)", text, re.IGNORECASE)
        if socket_match:
            chip["socket"] = socket_match.group(0).strip()

        year = extract_int(text)
        if year and 2000 <= year <= 2026:
            chip["year"] = year

        return chip

    def _apply_spec_key(self, chip: dict[str, Any], key: str, val: str, source_label: str) -> None:
        """Apply a spec table key-value pair."""
        if "core" in key and "thread" not in key:
            c, t = parse_core_thread(val)
            if c is not None and "cores" not in chip:
                chip["cores"] = c
            if t is not None and "threads" not in chip:
                chip["threads"] = t

        if "thread" in key:
            ct, _ = parse_core_thread(val)
            if ct is not None:
                chip["threads"] = ct

        if "clock" in key or "frequency" in key or "speed" in key:
            base, boost = parse_clock(val)
            if base is not None and "clock" not in chip:
                chip["clock"] = base
            if boost is not None and "boost" not in chip:
                chip["boost"] = boost

        if "tdp" in key or "power" in key:
            tdp = parse_tdp(val)
            if tdp is not None:
                chip["tdp"] = tdp

        if "cache" in key:
            if "l2" in key or "level 2" in key:
                cs = parse_cache_size(val)
                if cs:
                    chip["l2_cache"] = cs
            elif "l3" in key or "level 3" in key:
                cs = parse_cache_size(val)
                if cs:
                    chip["l3_cache"] = cs
            elif "l2_cache" not in chip and "l3_cache" not in chip:
                cs = parse_cache_size(val)
                if cs:
                    chip.setdefault("l3_cache", cs)

        if "process" in key or "lithography" in key:
            proc_nm = parse_process_node(val)
            if proc_nm is not None:
                chip["process_nm"] = proc_nm

        if "memory" in key or "ram" in key:
            mem_match = re.search(r"(DDR\d|LPDDR\d)", val, re.IGNORECASE)
            if mem_match and "memory_type" not in chip:
                chip["memory_type"] = mem_match.group(1).upper()
            mem_max = parse_memory_max(val)
            if mem_max and "memory_max" not in chip:
                chip["memory_max"] = mem_max

        if "graphics" in key or "gpu" in key:
            if val and val not in ("—", "-", "", "N/A") and "gpu" not in chip:
                chip["gpu"] = val.strip()

        if "socket" in key:
            if val and val not in ("—", "-", "", "N/A") and "socket" not in chip:
                chip["socket"] = val.strip()

        if "year" in key or "launch" in key or "introduced" in key:
            year = extract_int(val)
            if year and 2000 <= year <= 2026 and "year" not in chip:
                chip["year"] = year

    @staticmethod
    def _extract_model(name: str) -> str | None:
        """Extract a model identifier from a processor name."""
        name_clean = name.strip()
        m = re.search(r"[- ]?\d{3,}[A-Za-z0-9]*$", name_clean)
        if m:
            result = m.group(0).strip().lstrip("- ")
            if result:
                return result
        words = name_clean.split()
        for word in reversed(words):
            if re.search(r"\d{3,}", word):
                return word.strip()
        return None

    @staticmethod
    def _find_processor_name(text: str) -> str | None:
        """Find a plausible processor name in text."""
        intel_match = re.search(
            r"Intel\s+(Core\s+(?:Ultra\s+\d+\s+)?\w+\s*[-]?\d{3,}|Xeon\s+\w+\s*\d{3,}|Pentium|Celeron|Atom\s+\w+)",
            text, re.IGNORECASE,
        )
        if intel_match:
            return intel_match.group(0).strip()

        amd_match = re.search(
            r"AMD\s+(Ryzen\s+(?:\w+\s+)?\d{3,}|EPYC\s+\d{3,}|Threadripper|Athlon\s+\w+\s*\d{3,})",
            text, re.IGNORECASE,
        )
        if amd_match:
            return amd_match.group(0).strip()

        generic = re.search(r"\b(?:Core|Ryzen)\s+\w+\s*\d{3,}", text, re.IGNORECASE)
        if generic:
            return generic.group(0).strip()

        return None
