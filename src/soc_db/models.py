from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, RootModel


class Cache(BaseModel):
    l1: str | None = None
    l2: str | None = None
    l3: str | None = None


class Rating(BaseModel):
    performance: float | None = Field(None, ge=0, le=100)
    efficiency: float | None = Field(None, ge=0, le=100)
    gpu_score: float | None = Field(None, ge=0, le=100)
    ai_score: float | None = Field(None, ge=0, le=100)
    modem_score: float | None = Field(None, ge=0, le=100)


class Benchmarks(BaseModel):
    antutu_v10: int | None = None
    geekbench_6_single: int | None = None
    geekbench_6_multi: int | None = None
    geekbench_5_single: int | None = None
    geekbench_5_multi: int | None = None


class Chip(BaseModel):
    id: str = Field(description="Unique identifier (lowercase, underscore-separated)", pattern=r"^[a-z0-9_]+$")
    name: str = Field(description="Marketing name")
    vendor: str = Field(description="Manufacturer name")
    model: str | None = Field(None, description="Exact model number")
    aliases: list[str] | None = Field(None, description="Alternative names / aliases")
    codename: str | None = Field(None, description="Internal platform codename")
    description: str | None = Field(None, description="Short description")
    architecture: str | None = Field(None, description="ISA architecture")
    isa: str | None = Field(None, description="Instruction set architecture details")
    cores: int | None = Field(None, ge=1, le=256, description="Total core count")
    threads: int | None = Field(None, ge=1, description="Number of threads")
    cluster_config: str | None = Field(None, description="Core cluster layout")
    clock_max: int | None = Field(None, description="Maximum clock speed in MHz")
    clock_mid: int | None = Field(None, description="Mid-cluster clock speed in MHz")
    clock_min: int | None = Field(None, description="Minimum clock speed in MHz")
    max_freq: str | None = Field(None, description="Maximum frequency display string")
    process_nm: int | None = Field(None, description="Fabrication process node in nm")
    process_name: str | None = Field(None, description="Process node marketing name")
    process: str | None = Field(None, description="Fabrication process node string (legacy)")
    cache: Cache | None = Field(None, description="Cache hierarchy")
    tdp: float | None = Field(None, description="Thermal Design Power in Watts")
    gpu: str | None = Field(None, description="GPU model name")
    gpu_clock: int | None = Field(None, description="GPU clock speed in MHz")
    gpu_api: list[str] | None = Field(None, description="Supported GPU APIs")
    gpu_tflops: float | None = Field(None, description="GPU compute in TFLOPS")
    memory_type: str | None = Field(None, description="RAM type")
    memory_max: int | None = Field(None, description="Maximum RAM in GB")
    memory_clock: int | None = Field(None, description="Memory clock speed in MHz")
    memory_bus: int | None = Field(None, description="Memory bus width in bits")
    memory_bandwidth: int | None = Field(None, description="Memory bandwidth in GB/s")
    storage_type: str | None = Field(None, description="Storage interface")
    npu: str | None = Field(None, description="NPU / AI accelerator name")
    ai_ops: float | None = Field(None, description="AI performance in TOPS")
    modem: str | None = Field(None, description="Modem model name")
    modem_dl: int | None = Field(None, description="Modem max download in Mbps")
    modem_ul: int | None = Field(None, description="Modem max upload in Mbps")
    cellular: str | None = Field(None, description="Cellular generation and bands")
    video_decode: str | None = Field(None, description="Video decode capabilities")
    video_encode: str | None = Field(None, description="Video encode capabilities")
    display_max: str | None = Field(None, description="Maximum display resolution")
    camera_max: str | None = Field(None, description="Maximum camera resolution")
    isps: int | None = Field(None, description="Number of Image Signal Processors")
    video_capture: str | None = Field(None, description="Video capture capabilities")
    wifi: str | None = Field(None, description="WiFi standard")
    bluetooth: str | None = Field(None, description="Bluetooth version")
    usb: str | None = Field(None, description="USB version/support")
    navigation: str | None = Field(None, description="Navigation satellite systems")
    charging: str | None = Field(None, description="Charging technology")
    year: int | None = Field(None, ge=2007, le=2030, description="Release year")
    announced: date | None = Field(None, description="Announcement date")
    revision: str | None = Field(None, description="Revision or stepping")
    status: str | None = Field("unknown", description="Lifecycle status")
    completeness: float | None = Field(None, ge=0, le=1, description="Data completeness score")
    sources: dict[str, str] | None = Field(None, description="Per-field data source tracking")
    updated: date | None = Field(None, description="Last update date")
    datasheet_url: str | None = Field(None, description="Link to manufacturer datasheet")
    wikipedia_url: str | None = Field(None, description="Link to Wikipedia article")
    wikidata_id: str | None = Field(None, description="Wikidata item ID")
    linux_dt_compatible: str | None = Field(None, description="Linux Device Tree compatible string")
    devices: list[str] | None = Field(None, description="Known devices using this chip")
    alternative_names: list[str] | None = Field(None, description="Alternative names (legacy)")
    parent: str | None = Field(None, description="Parent chip ID for variants")
    tags: list[str] | None = Field(None, description="Arbitrary tags for categorization")
    rating: Rating | None = Field(None, description="Normalized performance ratings")
    benchmarks: Benchmarks | None = Field(None, description="Benchmark scores")

    # ── New v3.0 fields (Phase 9 — Provenance & Schema) ──────────────────
    market_segment: str | None = Field(None, description="Target market segment (mobile/desktop/server/iot/automotive)")
    charging_max_w: int | None = Field(None, description="Maximum charging power in Watts")
    wifi_version: str | None = Field(None, description="Wi-Fi version string (e.g. Wi-Fi 7, Wi-Fi 6E)")
    modem_5g_mmwave: bool | None = Field(None, description="Supports 5G mmWave")
    video_decode_av1: bool | None = Field(None, description="Hardware AV1 video decode support")
    video_encode_av1: bool | None = Field(None, description="Hardware AV1 video encode support")
    ai_int8_tops: float | None = Field(None, description="AI INT8 performance in TOPS")
    ai_fp16_tflops: float | None = Field(None, description="AI FP16 performance in TFLOPS")
    pcie_version: str | None = Field(None, description="PCI Express version (e.g. PCIe 4.0, PCIe 5.0)")
    usb_version: str | None = Field(None, description="USB version (e.g. USB 3.2 Gen 2, USB4)")
    bluetooth_version: str | None = Field(None, description="Bluetooth version (e.g. 5.4, 5.3)")
    satellite_connectivity: bool | None = Field(None, description="Supports satellite connectivity")
    gnss: str | None = Field(None, description="Supported GNSS systems (GPS, GLONASS, BeiDou, Galileo)")
    fingerprint: str | None = Field(None, description="Biometric fingerprint support")
    display_max_refresh: int | None = Field(None, description="Maximum display refresh rate in Hz")
    display_resolution: str | None = Field(None, description="Maximum display resolution string")
    camera_max_mp: int | None = Field(None, description="Maximum camera sensor resolution in MP")
    video_capture_max: str | None = Field(None, description="Maximum video capture capability (e.g. 8K30, 4K120)")
    isp_config: str | None = Field(None, description="ISP configuration (e.g. triple ISP)")
    dsp_type: str | None = Field(None, description="DSP type (e.g. Hexagon)")
    security: str | None = Field(None, description="Security subsystem (e.g. Titan M, Knox, Secure Enclave)")
    av1_decode: bool | None = Field(None, description="Hardware AV1 decode (alias for video_decode_av1)")
    arm_cores_total: int | None = Field(None, description="Total ARM core count (big.LITTLE)")
    performance_cores: int | None = Field(None, description="Number of performance cores")
    efficiency_cores: int | None = Field(None, description="Number of efficiency cores")
    l2_cache: str | None = Field(None, description="L2 cache configuration")
    l3_cache: str | None = Field(None, description="L3 cache configuration")
    soc_id: str | None = Field(None, description="Vendor-specific SoC part number")
    package: str | None = Field(None, description="Package type (e.g. FCCSP)")
    die_size: str | None = Field(None, description="Die size in mm²")
    provenance: dict[str, str] | None = Field(None, description="Per-field provenance tracking: {field_name: source_id}")

    model_config = {"extra": "ignore"}


class ChipListResponse(BaseModel):
    total: int
    offset: int
    limit: int
    data: list[Chip]


class VendorInfo(BaseModel):
    count: int
    avg_completeness: float


class VendorResponse(RootModel[dict[str, VendorInfo]]):
    pass


class StatsResponse(BaseModel):
    total_chips: int
    total_vendors: int
    year_min: int | None = None
    year_max: int | None = None
    avg_completeness: float
    fields_present: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    uptime: float
    chips_cached: int | None = None
    version: str | None = None
    redis_connected: bool = False


class MetricsResponse(BaseModel):
    uptime_seconds: float
    total_requests: int
    requests_per_second: float
    chips_cached: int
    active_rate_limit_clients: int


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
