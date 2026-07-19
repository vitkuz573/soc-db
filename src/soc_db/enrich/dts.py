"""DTS-based enrichment: extract CPU core count and architecture from Linux
Device Tree Source files.

Uses the Linux kernel's GitHub API to find DTSI definitions for known SoC
models, parses ``cpus { }`` blocks, detects architecture from CPU core
compatibles, and returns enriched chip data.

This module exposes ``enrich_from_dts(chip)`` for the enrichment pipeline.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from soc_db.common import fetch, guard_path
from soc_db.scraping.source import HTTPSource

logger = logging.getLogger(__name__)

# Core compatibles -> architecture mapping (most specific first)
CORE_ARCH: list[tuple[str, str]] = [
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

# Kernel vendor directory -> our vendor name
VENDOR_DIR_MAP: dict[str, str] = {
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

# Generic family names that should never get DTS enrichment
SKIP_FAMILIES: set[str] = {
    "EXYNOS", "EXYNOS4", "EXYNOS5", "EXYNOS54",
    "AMLOGIC", "MESON", "MESONI",
    "SUN50", "SUNXI",
    "RENESAS", "RZ", "RZG2", "RZG2L", "RZG2LC", "RZG2UL",
    "RZG3E", "RZG3L", "RZG3S", "RZT2H",
    "ROCKCHIP", "QCOM",
    "FSL", "IMX8",
    "NUVOTON", "MARVELL", "BROADCOM",
    "SIGMASTAR", "CIRRUS LOGIC",
    "APPLE", "S800", "S800X",
    "AMD", "ELBA",
    "NVIDIA",
    "REALTEK", "XILINX", "ALTERA",
}

_http_source = HTTPSource()


# ── DTSI index building ──────────────────────────────────────────────


def get_dtsi_index() -> dict[str, list[str]]:
    """Fetch and index all DTSI files from the Linux kernel tree.

    Returns:
        Dict mapping normalised filenames (no extension, no hyphens/underscores)
        to lists of full paths in the tree.
    """
    github_url = "https://api.github.com/repos/torvalds/linux/git/trees/master?recursive=1"
    raw = fetch(github_url, ttl=3600)
    tree = json.loads(raw).get("tree", [])
    idx: dict[str, list[str]] = defaultdict(list)
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


# ── DTS content parsing ──────────────────────────────────────────────


def extract_block(text: str, start: int) -> str | None:
    """Extract a ``{`` ... ``}`` block starting at *start*, handling brace nesting.

    Args:
        text: The full source text.
        start: Character position to begin scanning.

    Returns:
        The block content (without braces), or ``None`` if unbalanced.
    """
    depth = 0
    started = False
    s = start
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            if not started:
                started = True
                s = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return text[s + 1 : i]
    return None


def _detect_arch(compat: str) -> str | None:
    """Detect ARM architecture from a CPU core compatible string."""
    cl = compat.lower()
    best: tuple[str | None, int] = (None, -1)
    for core_name, arch in CORE_ARCH:
        if core_name in cl and len(core_name) > best[1]:
            best = (arch, len(core_name))
    return best[0]


def _resolve_include(inc_path: str, cur_dir: str) -> str | None:
    """Resolve a ``#include`` path relative to *cur_dir*.

    Args:
        inc_path: The path from the ``#include`` directive.
        cur_dir: Directory of the including file.

    Returns:
        The resolved absolute path within the kernel tree, or ``None``.
    """
    p = inc_path
    if p.startswith("./"):
        p = p[2:]
    parts = cur_dir.rstrip("/").split("/")
    for seg in p.split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg and seg != ".":
            parts.append(seg)
    result = "/".join(parts)
    if result.endswith(".dtsi") or result.endswith(".dts"):
        return result
    return result + ".dtsi"


def _parse_cpus_from_content(content: str, dtsi_path: str) -> dict[str, Any]:
    """Extract CPU info from DTS content.

    Args:
        content: The DTS source text.
        dtsi_path: Path of the DTSI file (for architecture fallback).

    Returns:
        Dict with ``cores`` and/or ``architecture`` keys, or empty.
    """
    result: dict[str, Any] = {}
    m = re.search(r"cpus\s*\{", content)
    if not m:
        return result
    cpus_body = extract_block(content, m.start())
    if not cpus_body:
        return result

    cpu_addrs: set[str] = set()
    arch_set: set[str] = set()

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
                result["_arch_source"] = "compatible"
                break
    elif dtsi_path.startswith("arch/arm64/"):
        result["architecture"] = "ARMv8-A"
        result["_arch_source"] = "fallback"

    return result


def parse_cpu_info(content: str, dtsi_path: str = "", _depth: int = 0) -> dict[str, Any]:
    """Extract CPU info, optionally following ``#include`` chains (max depth 2).

    Args:
        content: The DTS source text.
        dtsi_path: Path of the DTSI file.
        _depth: Internal recursion depth tracker.

    Returns:
        Dict with ``cores`` and/or ``architecture`` keys, or empty.
    """
    if _depth > 2:
        return {}

    result = _parse_cpus_from_content(content, dtsi_path)

    # If no CPU nodes found, try following #include directives
    if not result.get("cores"):
        cur_dir = "/".join(dtsi_path.split("/")[:-1])
        for m in re.finditer(r'#include\s+"([^"]+)"', content):
            resolved = _resolve_include(m.group(1), cur_dir)
            if not resolved:
                continue
            if not (resolved.endswith(".dtsi") or resolved.endswith(".dts")):
                continue
            url = f"https://raw.githubusercontent.com/torvalds/linux/master/{resolved}"
            try:
                inc_content = fetch(url, ttl=86400)
            except Exception:
                continue
            if not inc_content or len(inc_content) < 200:
                continue
            result = parse_cpu_info(inc_content, resolved, _depth + 1)
            if result.get("cores"):
                break

    return result


# ── public entry point ───────────────────────────────────────────────


def enrich_from_dts(chip: dict[str, Any], dtsi_index: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Enrich a single chip dict with CPU info from Linux DTS files.

    Looks up the chip's model number in the DTSI index, fetches the
    corresponding DTSI content from the Linux kernel tree, and extracts
    CPU core count and architecture.

    Args:
        chip: The chip record to enrich (modified in place).
        dtsi_index: Pre-built DTSI index. If ``None``, builds one.

    Returns:
        The enriched chip dict (same object as the input).
    """
    model = chip.get("model", chip.get("id", "")).strip().upper()
    if not model or model in SKIP_FAMILIES:
        return chip

    # Skip if already enriched and not being force-overwritten
    if chip.get("architecture") and chip.get("cores"):
        return chip

    vendor = chip.get("vendor", "")
    if not vendor:
        return chip

    idx = dtsi_index if dtsi_index is not None else get_dtsi_index()

    model_clean = model.lower().replace("-", "").replace("_", "")
    target_dirs = [vd for vd, vn in VENDOR_DIR_MAP.items() if vn.lower() == vendor.lower()]
    if not target_dirs:
        return chip

    candidates: list[tuple[float, str, str]] = []
    for key, paths in idx.items():
        if model_clean != key and not key.startswith(model_clean) and not model_clean.startswith(key):
            continue
        for path in paths:
            vdir = path.split("/")[4]
            if vdir not in target_dirs:
                continue
            fname = path.split("/")[-1]
            score = 0.0
            if key == model_clean:
                score += 5
            elif model_clean.startswith(key):
                score += len(key) / 100.0
            if "-base" in fname.replace(model_clean, ""):
                score += 3
            if fname.startswith(model_clean.split("-")[0] + "-"):
                score += 1
            candidates.append((score, key, path))

    if not candidates:
        return chip

    candidates.sort(key=lambda x: (-x[0], -len(x[1])))

    # Collect sibling paths for fallback
    base_prefix = candidates[0][1]
    sibling_paths: list[str] = []
    for key, paths in idx.items():
        if key.startswith(base_prefix) and key != base_prefix:
            for path in paths:
                vdir = path.split("/")[4]
                if vdir in target_dirs:
                    sibling_paths.append(path)

    info: dict[str, Any] = {}
    used_path = ""
    for _score, _key, path in candidates:
        url = f"https://raw.githubusercontent.com/torvalds/linux/master/{path}"
        try:
            content = fetch(url, ttl=86400)
        except Exception:
            continue
        if not content or len(content) < 200:
            continue
        info = parse_cpu_info(content, path)
        if info.get("cores"):
            used_path = path
            break

    if not info.get("cores") and sibling_paths:
        for path in sibling_paths:
            url = f"https://raw.githubusercontent.com/torvalds/linux/master/{path}"
            try:
                content = fetch(url, ttl=86400)
            except Exception:
                continue
            if not content or len(content) < 200:
                continue
            info = parse_cpu_info(content, path)
            if info.get("cores"):
                used_path = path
                break

    if info:
        changed = False
        for k, v in info.items():
            if k.startswith("_"):
                continue
            existing = chip.get(k)
            if k == "architecture":
                src = info.get("_arch_source", "")
                if src == "compatible":
                    if not existing or v != existing:
                        chip[k] = v
                        changed = True
                elif not existing:
                    chip[k] = v
                    changed = True
            elif not existing:
                chip[k] = v
                changed = True
        if changed and used_path:
            logger.debug("enrich_from_dts: %s <- %s (%s)", model, used_path.split("/")[-1], info)

    return chip
