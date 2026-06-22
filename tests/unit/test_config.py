from pathlib import Path

from soc_db.config import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.log_level == "WARNING"
        assert s.log_format == "json"
        assert s.api_host == "0.0.0.0"
        assert s.api_port == 8000
        assert s.api_rate_limit == 100
        assert s.api_rate_limit_window == 60
        assert s.cache_ttl == 300
        assert s.api_cors_origins == ["*"]

    def test_data_dir_default(self):
        s = Settings()
        assert "data" in str(s.data_dir)
        assert isinstance(s.data_dir, Path)

    def test_schema_file_default(self):
        s = Settings()
        assert "schema" in str(s.schema_file)
        assert "chip-schema.json" in str(s.schema_file)

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SOC_DB_LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("SOC_DB_API_PORT", "9000")
        monkeypatch.setenv("SOC_DB_API_RATE_LIMIT", "200")
        monkeypatch.setenv("SOC_DB_API_CORS_ORIGINS", '["http://example.com"]')
        s = Settings()
        assert s.log_level == "DEBUG"
        assert s.api_port == 9000
        assert s.api_rate_limit == 200
        assert s.api_cors_origins == ["http://example.com"]

    def test_env_file_not_required(self):
        s = Settings(_env_file=None)
        assert s.api_port == 8000

    def test_cache_ttl_custom(self, monkeypatch):
        monkeypatch.setenv("SOC_DB_CACHE_TTL", "600")
        s = Settings()
        assert s.cache_ttl == 600

    def test_singleton_available(self):
        from soc_db.config import settings

        assert isinstance(settings, Settings)
