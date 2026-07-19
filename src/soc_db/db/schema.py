"""SQLite schema DDL for soc-db.

Provides create / drop / rebuild helpers for the ``chips`` table and
the ``chips_fts`` FTS5 virtual table.
"""

from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# DDL strings
# ---------------------------------------------------------------------------

CHIPS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS chips (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    vendor TEXT NOT NULL,
    model TEXT,
    aliases TEXT,
    codename TEXT,
    description TEXT,
    architecture TEXT,
    isa TEXT,
    cores INTEGER,
    threads INTEGER,
    cluster_config TEXT,
    clock_max INTEGER,
    clock_mid INTEGER,
    clock_min INTEGER,
    max_freq TEXT,
    process_nm INTEGER,
    process_name TEXT,
    process TEXT,
    cache TEXT,
    tdp REAL,
    gpu TEXT,
    gpu_clock INTEGER,
    gpu_api TEXT,
    gpu_tflops REAL,
    memory_type TEXT,
    memory_max INTEGER,
    memory_clock INTEGER,
    memory_bus INTEGER,
    memory_bandwidth INTEGER,
    storage_type TEXT,
    npu TEXT,
    ai_ops REAL,
    modem TEXT,
    modem_dl INTEGER,
    modem_ul INTEGER,
    cellular TEXT,
    video_decode TEXT,
    video_encode TEXT,
    display_max TEXT,
    camera_max TEXT,
    isps INTEGER,
    video_capture TEXT,
    wifi TEXT,
    bluetooth TEXT,
    connectivity TEXT,
    dsp TEXT,
    usb TEXT,
    navigation TEXT,
    charging TEXT,
    year INTEGER,
    announced TEXT,
    revision TEXT,
    status TEXT,
    completeness REAL,
    source TEXT,
    sources TEXT,
    updated TEXT,
    datasheet_url TEXT,
    wikipedia_url TEXT,
    wikidata_id TEXT,
    linux_dt_compatible TEXT,
    devices TEXT,
    alternative_names TEXT,
    parent TEXT,
    tags TEXT,
    rating TEXT,
    benchmarks TEXT,
    -- v3.0 fields (Phase 9 — Provenance & Schema)
    market_segment TEXT,
    charging_max_w INTEGER,
    wifi_version TEXT,
    modem_5g_mmwave INTEGER,
    video_decode_av1 INTEGER,
    video_encode_av1 INTEGER,
    ai_int8_tops REAL,
    ai_fp16_tflops REAL,
    pcie_version TEXT,
    usb_version TEXT,
    bluetooth_version TEXT,
    satellite_connectivity INTEGER,
    gnss TEXT,
    fingerprint TEXT,
    display_max_refresh INTEGER,
    display_resolution TEXT,
    camera_max_mp INTEGER,
    video_capture_max TEXT,
    isp_config TEXT,
    dsp_type TEXT,
    security TEXT,
    av1_decode INTEGER,
    arm_cores_total INTEGER,
    performance_cores INTEGER,
    efficiency_cores INTEGER,
    l2_cache TEXT,
    l3_cache TEXT,
    soc_id TEXT,
    package TEXT,
    die_size TEXT,
    provenance TEXT
)
"""

INDEXES_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_chips_vendor ON chips(vendor)",
    "CREATE INDEX IF NOT EXISTS idx_chips_year ON chips(year)",
    "CREATE INDEX IF NOT EXISTS idx_chips_architecture ON chips(architecture)",
    "CREATE INDEX IF NOT EXISTS idx_chips_gpu ON chips(gpu)",
]

FTS5_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chips_fts USING fts5(
    content='chips',
    content_rowid='rowid',
    name,
    vendor,
    model,
    codename,
    description,
    architecture,
    isa,
    cluster_config,
    gpu,
    memory_type,
    storage_type,
    npu,
    modem,
    cellular,
    wifi,
    bluetooth,
    usb,
    navigation,
    charging,
    revision,
    process_name,
    max_freq,
    tokenize='porter unicode61'
)
"""

FTS5_SELECT_COLS = (
    "name, vendor, model, codename, description, architecture, isa, "
    "cluster_config, gpu, memory_type, storage_type, npu, modem, "
    "cellular, wifi, bluetooth, usb, navigation, charging, revision, "
    "process_name, max_freq"
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def create_tables(conn: sqlite3.Connection) -> None:
    """Create the chips table, indexes, and FTS5 virtual table.

    All statements use ``IF NOT EXISTS`` so the function is idempotent.

    Args:
        conn: An open SQLite connection.
    """
    conn.execute(CHIPS_TABLE_DDL)
    for ddl in INDEXES_DDL:
        conn.execute(ddl)
    conn.execute(FTS5_DDL)
    conn.commit()


def create_fts_index(conn: sqlite3.Connection) -> None:
    """Alias for :func:`rebuild_fts`."""
    rebuild_fts(conn)


def drop_tables(conn: sqlite3.Connection) -> None:
    """Drop the chips and chips_fts tables.

    Args:
        conn: An open SQLite connection.
    """
    conn.execute("DROP TABLE IF EXISTS chips_fts")
    conn.execute("DROP TABLE IF EXISTS chips")
    conn.commit()


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild the FTS5 index from the chips table.

    Uses the FTS5 ``rebuild`` command which re-scans the content table
    (``chips``) and reconstructs the full-text index.  This is the
    correct approach for external content FTS5 tables.

    Args:
        conn: An open SQLite connection.
    """
    conn.execute("INSERT INTO chips_fts(chips_fts) VALUES('rebuild')")
    conn.commit()
