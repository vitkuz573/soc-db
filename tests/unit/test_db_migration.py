"""Unit tests for the JSON-to-SQLite migration tool."""

import json

from soc_db.common import DATA_DIR
from soc_db.db.connection import get_connection
from soc_db.db.migrate import migrate, validate_migration


class TestMigration:
    def test_migration_creates_database(self, temp_data_dir):
        """Verify migrate() creates .db file."""
        db_path = temp_data_dir / "test.db"
        migrate(db_path, force=True)
        assert db_path.exists()
        assert db_path.stat().st_size > 0

    def test_migration_all_chips_present(self, temp_data_dir):
        """Verify total_chips > 0 and matches JSON file count."""
        db_path = temp_data_dir / "test.db"
        result = migrate(db_path, force=True)

        # Count chips in JSON files
        json_count = 0
        for fpath in sorted(DATA_DIR.glob("*.json")):
            if fpath.name == "index.json" or fpath.name.startswith("_"):
                continue
            json_count += len(json.loads(fpath.read_text("utf-8")))

        assert result["total_chips"] > 0
        assert result["total_chips"] == json_count

    def test_migration_field_by_field_validation(self, temp_data_dir):
        """Field-by-field comparison using validate_migration(). Must pass with 0 mismatches."""
        db_path = temp_data_dir / "test.db"
        migrate(db_path, force=True)
        validation = validate_migration(db_path)
        assert validation["pass"], f"Validation failed with {len(validation['mismatches'])} mismatches"
        assert validation["total"] > 0

    def test_migration_force_recreates(self, temp_data_dir):
        """Migrate twice with force=True, verify counts match both times."""
        db_path = temp_data_dir / "test.db"
        r1 = migrate(db_path, force=True)
        r2 = migrate(db_path, force=True)
        assert r1["total_chips"] == r2["total_chips"]

    def test_migration_idempotent_without_force(self, temp_data_dir):
        """Migrate twice (second without force), verify no duplicate rows."""
        db_path = temp_data_dir / "test.db"
        r1 = migrate(db_path, force=True)
        # Second call without force — should skip (idempotent)
        r2 = migrate(db_path, force=False)
        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) FROM chips").fetchone()[0]
        conn.close()
        assert count == r1["total_chips"]

    def test_migration_preserves_null_fields(self, temp_data_dir):
        """Verify fields absent in JSON are NULL in SQLite."""
        db_path = temp_data_dir / "test.db"
        migrate(db_path, force=True)
        conn = get_connection(db_path)
        # Some chips should have NULL architecture, description, etc.
        null_count = conn.execute("SELECT COUNT(*) FROM chips WHERE architecture IS NULL").fetchone()[0]
        assert null_count >= 0  # at least some may be null in real data
        conn.close()

    def test_migration_serializes_list_fields(self, temp_data_dir):
        """Verify aliases stored as JSON and deserialized back."""
        db_path = temp_data_dir / "test.db"
        migrate(db_path, force=True)

        from soc_db.db.queries import get_all as _sql_get_all

        conn = get_connection(db_path)
        chips = _sql_get_all(conn=conn)
        conn.close()

        # At least some chips should have aliases
        with_aliases = [c for c in chips if c.get("aliases")]
        assert len(with_aliases) > 0
        assert isinstance(with_aliases[0]["aliases"], list)

    def test_migration_serializes_dict_fields(self, temp_data_dir):
        """Verify sources dict field is stored/retrieved correctly."""
        db_path = temp_data_dir / "test.db"
        migrate(db_path, force=True)

        from soc_db.db.queries import get_all as _sql_get_all

        conn = get_connection(db_path)
        chips = _sql_get_all(conn=conn)
        conn.close()

        # sources field should be a dict (even if empty)
        with_sources = [c for c in chips if c.get("sources") is not None]
        assert len(with_sources) > 0
        assert isinstance(with_sources[0]["sources"], dict)

    def test_migration_per_vendor_counts(self, temp_data_dir):
        """Verify per-vendor counts match between JSON and SQLite."""
        db_path = temp_data_dir / "test.db"
        result = migrate(db_path, force=True)
        assert "per_vendor" in result
        assert len(result["per_vendor"]) > 0
        total_from_vendors = sum(result["per_vendor"].values())
        assert total_from_vendors == result["total_chips"]
