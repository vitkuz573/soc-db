"""Cell parsers for Wikipedia infobox extraction of enterprise SoC fields."""

import re


def parse_cpu(text: str) -> dict:
    """Parse CPU cell: cores, architecture, clock speeds."""
    result = {}
    if not text:
        return result

    # Architecture
    arch_map = {"ARMv9": "ARMv9-A", "ARMv8": "ARMv8.2-A", "ARMv7": "ARMv7-A"}
    for key, val in arch_map.items():
        if key in text:
            result["architecture"] = val
            break
    if not result.get("architecture"):
        for arch in ("Cortex", "Kryo", "Swift", "Hurricane", "Zephyr", "Mistral", "Lightning", "Thunder", "Avalanche", "Blizzard"):
            if re.search(rf'\b{arch}\b', text, re.IGNORECASE):
                result["architecture"] = "ARMv8.2-A"
                break

    CORE_NAMES = r'(?:Cortex|Kryo|Gold|Silver|A\d+|Avalanche|Blizzard|Lightning|Thunder|Everest|Sawtooth|Mistral|Zephyr|Hurricane|Monsoon|Icestorm|Firestorm|Vortex|Tempest|Typhoon|Cyclone)'

    # Core count: explicit total-core pattern > cluster sum > x-sum > first number
    cores = None
    m_total = re.search(r'(\d+)\s*(?:-core|cores?\b)', text, re.IGNORECASE)
    if m_total:
        cores = int(m_total.group(1))
    else:
        cluster_re = rf'(\d+)[xX*×]\s*(?:[\d.]+\s*(?:GHz|MHz)\s+)?{CORE_NAMES}'
        clusters = re.findall(cluster_re, text)
        if clusters:
            cores = sum(int(c) for c in clusters)
        else:
            x_vals = re.findall(r'(\d+)\s*[xX*×]', text)
            x_vals = [int(v) for v in x_vals if int(v) <= 8]
            if len(x_vals) >= 2:
                cores = sum(x_vals)
            else:
                m_num = re.search(r'\b(8|10|12|6|4|16|2)\b', text)
                if m_num:
                    cores = int(m_num.group(1))
    if cores and cores <= 256:
        result["cores"] = cores

    # Cluster config (e.g. 1+3+4)
    cluster_re = rf'(\d+)[xX*×]\s*(?:[\d.]+\s*(?:GHz|MHz)\s+)?{CORE_NAMES}'
    cm = re.findall(cluster_re, text)
    if len(cm) < 2:
        cm = re.findall(r'(\d+)[xX*×]', text)
        cm = [c for c in cm if int(c) <= 8]
    if len(cm) >= 2:
        result["cluster_config"] = "+".join(cm[:3])

    # Clock speeds
    speeds = re.findall(r'([\d.]+)\s*(?:GHz|MHz)', text, re.IGNORECASE)
    mhz_vals = []
    for s in speeds:
        val = float(s)
        if 'GHz' in text[text.find(s)-2:text.find(s)+len(s)+4] if s else False:
            mhz_vals.append(int(val * 1000))
        else:
            mhz_vals.append(int(val))
    if mhz_vals:
        mhz_vals = sorted(mhz_vals)
        result["clock_min"] = mhz_vals[0]
        result["clock_max"] = mhz_vals[-1]
        if len(mhz_vals) >= 3:
            result["clock_mid"] = mhz_vals[len(mhz_vals)//2]
        result["max_freq"] = f"{mhz_vals[-1]/1000:.2f} GHz" if mhz_vals[-1] >= 1000 else f"{mhz_vals[-1]} MHz"

    return result


def parse_gpu(text: str) -> dict:
    """Parse GPU cell: name, clock, APIs."""
    result = {}
    if not text:
        return result
    result["gpu"] = text.strip()[:120]
    # Clock
    m = re.search(r'(\d+)\s*MHz', text, re.IGNORECASE)
    if m:
        result["gpu_clock"] = int(m.group(1))
    # APIs
    apis = []
    for api in ["OpenGL ES", "Vulkan", "DirectX", "Metal", "OpenCL"]:
        if api.lower() in text.lower():
            apis.append(api)
    if apis:
        result["gpu_api"] = apis
    return result


def parse_process(text: str) -> dict:
    """Parse process node: nm value, name."""
    result = {}
    if not text:
        return result
    m = re.search(r'(\d+)\s*nm', text, re.IGNORECASE)
    if m:
        nm = int(m.group(1))
        result["process_nm"] = nm
        result["process_name"] = f"{nm}nm"
        result["process"] = f"{nm} nm"
    return result


def parse_memory(text: str) -> dict:
    """Parse memory cell: type, speed, max capacity."""
    result = {}
    if not text:
        return result
    # Memory type
    for mtype in ["LPDDR5", "LPDDR4X", "LPDDR4", "LPDDR3", "DDR5", "DDR4", "DDR3"]:
        if mtype in text.upper():
            result["memory_type"] = mtype
            break
    # Speed
    m = re.search(r'(\d+)\s*MHz', text, re.IGNORECASE)
    if m:
        result["memory_clock"] = int(m.group(1))
    # Max capacity
    m = re.search(r'(?:up to\s*)?(\d+)\s*GB', text, re.IGNORECASE)
    if m:
        result["memory_max"] = int(m.group(1))
    # Bus width
    m = re.search(r'(\d+)\s*-?bit', text, re.IGNORECASE)
    if m:
        result["memory_bus"] = int(m.group(1))
    return result


def parse_modem(text: str) -> dict:
    """Parse modem cell: name, DL/UL speeds."""
    result = {}
    if not text:
        return result
    parts = text.strip().split()
    result["modem"] = text.strip()[:80]
    # Download speed
    m = re.search(r'([\d.]+)\s*(?:Gbps|Mbps|Gb/s|Mb/s)\s*(?:download|DL|downlink)?', text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        result["modem_dl"] = int(val * 1000 if "G" in m.group(0).upper() else val)
    # Upload speed
    m = re.search(r'([\d.]+)\s*(?:Gbps|Mbps|Gb/s|Mb/s)\s*(?:upload|UL|uplink)', text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        result["modem_ul"] = int(val * 1000 if "G" in m.group(0).upper() else val)
    # If only one speed found, it's likely DL
    if not result.get("modem_dl"):
        m = re.search(r'down\s*([\d.]+)\s*Gbps', text, re.IGNORECASE)
        if m:
            result["modem_dl"] = int(float(m.group(1)) * 1000)
    return result


def parse_connectivity(text: str) -> dict:
    """Parse connectivity cell: WiFi, Bluetooth."""
    result = {}
    if not text:
        return result
    # WiFi
    m = re.search(r'Wi-?Fi\s*(\d+|[\d.]+)', text, re.IGNORECASE)
    if m:
        result["wifi"] = f"Wi-Fi {m.group(1)}"
    else:
        m = re.search(r'(802\.11\w*)', text, re.IGNORECASE)
        if m:
            result["wifi"] = m.group(1)
        elif re.search(r'\bWi-?Fi\b', text, re.IGNORECASE):
            result["wifi"] = "Wi-Fi"
    # Bluetooth
    m = re.search(r'Bluetooth\s*([\d.]+)', text, re.IGNORECASE)
    if m:
        result["bluetooth"] = m.group(1)
    # NFC
    if re.search(r'\bNFC\b', text):
        result.setdefault("connectivity", "NFC")
    return result


def parse_video(text: str) -> dict:
    """Parse video cell: decode/encode capabilities."""
    result = {}
    if not text:
        return result
    if re.search(r'(8K|4320p)', text, re.IGNORECASE):
        result["video_decode"] = text.strip()[:100]
    elif re.search(r'(4K|2160p)', text, re.IGNORECASE):
        result["video_decode"] = text.strip()[:100]
    else:
        result["video_decode"] = text.strip()[:100]
    return result


def parse_display(text: str) -> dict:
    """Parse display cell: max resolution/refresh."""
    result = {}
    if not text:
        return result
    m = re.search(r'(\d+)×(\d+)', text)
    if m:
        res = f"{m.group(1)}×{m.group(2)}"
        hz = re.search(r'(\d+)Hz', text)
        if hz:
            res += f" @ {hz.group(1)}Hz"
        result["display_max"] = res
    elif re.search(r'(4K|8K|WQHD|FHD)', text, re.IGNORECASE):
        result["display_max"] = text.strip()[:80]
    return result


def parse_camera(text: str) -> dict:
    """Parse camera cell: MP, ISPs."""
    result = {}
    if not text:
        return result
    m = re.search(r'(\d+)\s*MP', text, re.IGNORECASE)
    if m:
        result["camera_max"] = text.strip()[:80]
    m = re.search(r'(\d+)\s*(?:ISP|image signal processor)', text, re.IGNORECASE)
    if m:
        result["isps"] = int(m.group(1))
    return result


# Map column header keywords to (field_name, parser_function)
COLUMN_MAP = [
    (["model number", "model", "soc", "chipset", "chip name"], "model", None),
    (["product name", "brand", "marketing name"], "name", None),
    (["cpu", "cpu cores", "cpu config", "cpu cluster"], "cpu", parse_cpu),
    (["gpu", "graphics"], "gpu", parse_gpu),
    (["dsp"], "dsp", lambda t: {"dsp": t.strip()[:80]} if t else {}),
    (["npu", "ai", "ai accelerator", "machine learning"], "npu", lambda t: {"npu": t.strip()[:80]} if t else {}),
    (["memory", "memory support", "ram", "memory type"], "memory", parse_memory),
    (["process", "fabrication", "node", "process node", "technology", "fab"], "process", parse_process),
    (["modem", "cellular", "mobile radio"], "modem", parse_modem),
    (["connectivity", "wifi", "wi-fi", "bluetooth"], "connectivity", parse_connectivity),
    (["charging", "charge", "fast charge", "battery charging", "quick charge"], "charging", lambda t: {"charging": t.strip()[:80]} if t else {}),
    (["storage", "storage type"], "storage", lambda t: {"storage_type": t.strip()[:80]} if t else {}),
    (["video", "video codec", "video encode/decode", "video codecs", "video encoding/decoding"], "video", parse_video),
    (["display", "display support", "screen"], "display", parse_display),
    (["camera", "isp", "isps", "image signal", "camera specs"], "camera", parse_camera),
    (["location", "gnss", "navigation", "gps", "positioning"], "location", lambda t: {"navigation": t.strip()[:80]} if t else {}),
]


def _kw_match(text: str, keyword: str) -> bool:
    """Keyword matching: whole-word for short keywords, substring for long ones."""
    if len(keyword) <= 3:
        return bool(re.search(rf'\b{re.escape(keyword)}\b', text, re.IGNORECASE))
    return keyword.lower() in text.lower()


def detect_columns(header_row) -> list[tuple[str, callable]]:
    """Detect column field names from header row cells."""
    columns = []
    for cell in header_row:
        text = cell.get_text(" ", strip=True).lower().strip()
        matched = False
        for keywords, field_name, parser in COLUMN_MAP:
            if any(_kw_match(text, kw) for kw in keywords):
                columns.append((field_name, parser))
                matched = True
                break
        if not matched:
            columns.append((None, None))
    return columns


def parse_cell(text: str, field_name: str, parser) -> dict:
    """Parse a cell into structured fields using the appropriate parser."""
    if not text or text in ("—", "-", "?", "", "N/A", "n/a"):
        return {}
    if parser:
        return parser(text)
    if field_name:
        return {field_name: text.strip()[:120]}
    return {}
