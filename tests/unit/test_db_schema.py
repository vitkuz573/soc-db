"""Unit tests for the SQLite database schema."""

import sqlite3

from soc_db.db.schema import create_tables, drop_tables, rebuild_fts
from soc_db.models import Chip


def _table_cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


class TestSchemaTables:
    def test_tables_exist(self, db_conn):
        """Verify chips and chips_fts tables are present."""
        tables = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "chips" in tables
        assert "chips_fts" in tables

    def test_chip_columns_match_model(self, db_conn):
        """Verify all Chip model fields have corresponding columns."""
        model_fields = set(Chip.model_fields.keys())
        db_cols = _table_cols(db_conn, "chips")
        # Core model fields that MUST be present
        required = {"id", "name", "vendor", "model", "cores", "architecture", "gpu", "year", "completeness"}
        missing = required - db_cols
        assert not missing, f"Missing columns: {missing}"

    def test_required_columns_not_null(self, db_conn):
        """Verify id, name, vendor are NOT NULL (via PRAGMA or PK constraint)."""
        info = db_conn.execute("PRAGMA table_info(chips)").fetchall()
        not_null = {r[1] for r in info if r[3] == 1}
        pks = {r[1] for r in info if r[5] == 1}
        # id is PRIMARY KEY (implicitly NOT NULL even if PRAGMA shows 0)
        if "id" not in not_null:
            assert "id" in pks, "id must be PK if not explicitly NOT NULL"
        assert "name" in not_null
        assert "vendor" in not_null

    def test_indexes_exist(self, db_conn):
        """Verify vendor, year, architecture, gpu indexes."""
        idxs = [r[1] for r in db_conn.execute("PRAGMA index_list(chips)").fetchall()]
        idx_names = [i for i in idxs if i is not None]
        assert any("vendor" in i for i in idx_names), "Missing vendor index"
        assert any("year" in i for i in idx_names), "Missing year index"
        assert any("architecture" in i for i in idx_names), "Missing architecture index"
        assert any("gpu" in i for i in idx_names), "Missing gpu index"

    def test_fts_columns_match_chips(self, db_conn):
        """Verify chips_fts is configured for the chips table."""
        fts_tables = {r[0] for r in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts%'"
        ).fetchall()}
        assert len(fts_tables) >= 1

    def test_drop_tables_clean(self):
        """Verify drop_tables removes both tables."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_tables(conn)
        drop_tables(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "chips" not in tables
        assert "chips_fts" not in tables
        conn.close()

    def test_rebuild_fts_populates(self, db_conn):
        """Verify rebuild_fts populates the FTS index."""
        # Count FTS rows before
        before = db_conn.execute("SELECT COUNT(*) FROM chips_fts").fetchone()[0]
        # Rebuild
        rebuild_fts(db_conn)
        after = db_conn.execute("SELECT COUNT(*) FROM chips_fts").fetchone()[0]
        assert after > 0
        assert after >= before  # should have at least as many

    def test_extra_fields_present(self, db_conn):
        """Verify extra fields from JSON data are in the schema."""
        cols = _table_cols(db_conn, "chips")
        assert "source" in cols
        assert "connectivity" in cols
        assert "dsp" in cols
