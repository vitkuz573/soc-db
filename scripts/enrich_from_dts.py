#!/usr/bin/env python3
"""Enrich chips by parsing DTS content for architecture + core info.

Conservative strategy:
- Only use DTSI files (no board DTS)
- Extract the full cpus { } block with brace-depth tracking
- Detect architecture from CPU core compatibles
- Count unique CPU nodes for core count
"""

import json
import re
import sys
from collections import defaultdict
from common import fetch, DATA_DIR

# Core compatibles -> architecture mapping (most specific first)
CORE_ARCH = [
    ("cortex-a520", "ARMv9-A"),
    ("cortex-a510", "ARMv9-A"),
    ("cortex-a710", "ARMv9-A"),
    ("cortex-a715", "ARMv9-A"),
    ("cortex-a720", "ARMv9-A"),
    ("cortex-x4", "ARMv9-A"),
    ("cortex-x3", "ARMv9-A"),
    ("cortex-x2", "ARMv9-A"),
    ("cortex-x1c", "ARMv8.2-A"),
    ("cortex-x1", "ARMv8.2-A"),
    ("cortex-a78c", "ARMv8.2-A"),
    ("cortex-a78", "ARMv8.2-A"),
    ("cortex-a77", "ARMv8.2-A"),
    ("cortex-a76ae", "ARMv8.2-A"),
    ("cortex-a76", "ARMv8.2-A"),
    ("cortex-a75", "ARMv8.2-A"),
    ("cortex-a65ae", "ARMv8.2-A"),
    ("cortex-a65", "ARMv8.2-A"),
    ("cortex-a55", "ARMv8.2-A"),
    ("cortex-a73", "ARMv8-A"),
    ("cortex-a72", "ARMv8-A"),
    ("cortex-a57", "ARMv8-A"),
    ("cortex-a53", "ARMv8-A"),
    ("cortex-a35", "ARMv8-A"),
    ("cortex-a17", "ARMv7-A"),
    ("cortex-a15", "ARMv7-A"),
    ("cortex-a12", "ARMv7-A"),
    ("cortex-a9", "ARMv7-A"),
    ("cortex-a8", "ARMv7-A"),
    ("cortex-a7", "ARMv7-A"),
    ("cortex-a5", "ARMv7-A"),
    ("arm926", "ARMv5"),
    ("arm940", "ARMv5"),
    ("arm720", "ARMv4"),
]

VENDOR_DIR_MAP = {
    "qcom": "Qualcomm", "mediatek": "MediaTek", "exynos": "Samsung",
    "samsung": "Samsung", "hisilicon": "HiSilicon", "apple": "Apple",
    "rockchip": "Rockchip", "allwinner": "Allwinner", "sunxi": "Allwinner",
    "amlogic": "Amlogic", "meson": "Amlogic", "nvidia": "Nvidia", "tegra": "Nvidia",
    "ti": "TI OMAP", "omap": "TI OMAP", "intel": "Intel Atom", "ingenic": "Ingenic",
    "nxp": "NXP i.MX", "freescale": "NXP i.MX", "imx": "NXP i.MX", "sprd": "Unisoc",
    "realtek": "Realtek", "broadcom": "Broadcom", "brcm": "Broadcom",
    "marvell": "Marvell", "mvebu": "Marvell", "renesas": "Renesas", "rcar": "Renesas",
    "st": "STMicroelectronics", "stm32": "STMicroelectronics",
    "microchip": "Microchip", "atmel": "Microchip", "xilinx": "Xilinx", "zynq": "Xilinx",
    "actions": "Actions", "owl": "Actions",
    "airoha": "Airoha", "amazon": "Amazon", "altera": "Altera", "amd": "AMD",
    "apm": "APM", "aspeed": "ASPEED", "bitmain": "Bitmain", "cavium": "Cavium",
    "socionext": "Socionext", "sophgo": "Sophgo", "synaptics": "Synaptics",
    "tesla": "Tesla", "toshiba": "Toshiba", "nuvoton": "Nuvoton",
    "sigmastar": "SigmaStar", "vt8500": "VIA WonderMedia", "cirrus": "Cirrus Logic",
}


def get_dtsi_index():
    raw = fetch("https://api.github.com/repos/torvalds/linux/git/trees/master?recursive=1", ttl=3600)
    tree = json.loads(raw).get("tree", [])
    idx = defaultdict(list)
    for entry in tree:
        path = entry.get("path", "")
        fname = path.split("/")[-1]
        if not fname.endswith(".dtsi"):
            continue
        key = fname.replace(".dtsi", "").replace("-", "").replace("_", "").lower()
        parts = path.split("/")
        if len(parts) >= 5:
            idx[key].append(path)
    return idx


def extract_block(text, start):
    """Extract a { ... } block starting at start, handling brace nesting."""
    depth = 0
    started = False
    s = start
    for i in range(start, len(text)):
        ch = text[i]
        if ch == '{':
            if not started:
                started = True
                s = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if started and depth == 0:
                return text[s+1:i]
    return None


def _detect_arch(compat: str) -> str | None:
    cl = compat.lower()
    best = (None, -1)
    for core_name, arch in CORE_ARCH:
        if core_name in cl and len(core_name) > best[1]:
            best = (arch, len(core_name))
    return best[0]


def parse_cpu_info(content: str, dtsi_path: str = "") -> dict:
    result = {}

    m = re.search(r"cpus\s*\{", content)
    if not m:
        return result
    cpus_body = extract_block(content, m.start())
    if not cpus_body:
        return result

    cpu_addrs = set()
    arch_set = set()

    for m2 in re.finditer(r"cpu@([0-9a-f]+)\s*\{", cpus_body):
        addr = m2.group(1)
        cpu_addrs.add(addr)
        cpu_body = extract_block(cpus_body, m2.start())
        if cpu_body:
            compat_m = re.search(r'compatible\s*=\s*"([^"]+)"', cpu_body)
            if compat_m:
                arch = _detect_arch(compat_m.group(1))
                if arch:
                    arch_set.add(arch)

    if cpu_addrs:
        result["cores"] = len(cpu_addrs)

    if arch_set:
        for arch in ["ARMv9-A", "ARMv8.2-A", "ARMv8-A", "ARMv7-A", "ARMv5", "ARMv4"]:
            if arch in arch_set:
                result["architecture"] = arch
                break
    elif dtsi_path.startswith("arch/arm64/"):
        result["architecture"] = "ARMv8-A"

    return result


def main():
    print("=== DTS Content Architecture Enrichment ===")
    print("  Building DTSI index...", end=" ", flush=True)
    idx = get_dtsi_index()
    print(f"{len(idx)} entries\n")

    total_enriched = 0
    total_fetched = 0

    for fpath in sorted(DATA_DIR.glob("*.json")):
        if fpath.name in ("index.json", "chip-schema.json", "other.json"):
            continue
        data = json.loads(fpath.read_text())
        updated = 0
        for chip in data:
            if chip.get("architecture") and chip.get("cores"):
                continue
            vendor = chip.get("vendor", "")
            model = chip.get("model", chip.get("id", ""))
            if not model:
                continue

            model_clean = model.lower().replace("-", "").replace("_", "")
            target_dirs = [vd for vd, vn in VENDOR_DIR_MAP.items()
                          if vn.lower() == vendor.lower()]
            if not target_dirs:
                continue

            best_score = -1
            best_path = None
            for key, paths in idx.items():
                if model_clean != key and not key.startswith(model_clean) and not model_clean.startswith(key):
                    continue
                for path in paths:
                    vdir = path.split("/")[4]
                    if vdir not in target_dirs:
                        continue
                    fname = path.split("/")[-1]
                    score = 0
                    if key == model_clean:
                        score += 5
                    if "-base" in fname.replace(model_clean, ""):
                        score += 3
                    if fname.startswith(model_clean.split("-")[0] + "-"):
                        score += 1
                    if score > best_score:
                        best_score = score
                        best_path = path

            if not best_path:
                continue

            url = f"https://raw.githubusercontent.com/torvalds/linux/master/{best_path}"
            try:
                content = fetch(url, ttl=86400)
            except Exception:
                continue
            if not content or len(content) < 200:
                continue
            total_fetched += 1

            info = parse_cpu_info(content, best_path)
            if info:
                changed = False
                for k, v in info.items():
                    if k not in chip or not chip[k]:
                        chip[k] = v
                        changed = True
                if changed:
                    updated += 1
                    total_enriched += 1
                    src = best_path.split("/")[-1]
                    print(f"  {fpath.name}: {model:20s} <- {src:25s} {info}", flush=True)

        if updated > 0:
            output = sorted(data, key=lambda x: (x.get("year", 9999), x.get("name", "")))
            fpath.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")

    print(f"\n  Total: {total_enriched} chips enriched ({total_fetched} DTSI files fetched)")


if __name__ == "__main__":
    main()
