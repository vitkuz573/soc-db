"""Unit tests for HTTPSource tiered HTTP fetcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from soc_db.scraping.rate_limit import PerSourceRateLimiter
from soc_db.scraping.source import HTTPSource


class TestHTTPSourceConstruction:
    def test_default_construction(self):
        source = HTTPSource()
        assert source._timeout == 30.0
        assert source._follow_redirects is True
        assert source._cache_ttl == 86400

    def test_with_rate_limiter(self):
        rl = PerSourceRateLimiter("test")
        source = HTTPSource(rate_limiter=rl)
        assert source._rate_limiter is rl


class TestHTTPSourceTier1:
    def test_fetch_httpx_called_first(self, monkeypatch):
        """On a normal fetch, httpx should be called."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        source = HTTPSource()

        monkeypatch.setattr(
            "soc_db.scraping.source.HTTPSource._fetch_httpx",
            lambda self, url, headers: "httpx response"
        )

        result = source.fetch("http://example.com")
        assert result == "httpx response"

    def test_fetch_httpx_403_escalates(self, monkeypatch):
        """On 403, httpx fails and curl-cffi (or Playwright) is tried next."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        source = HTTPSource()

        def fake_httpx_get(self_, url, **kw):
            raise ConnectionError(f"HTTP 403 for {url} (retryable — escalate)")

        monkeypatch.setattr("httpx.Client.get", fake_httpx_get, raising=False)

        # If curl-cffi is installed, it'll try that. We'll mock it too.
        try:
            import curl_cffi.requests  # noqa: F401

            class FakeCurlResponse:
                status_code = 200
                text = "curl response"

                def raise_for_status(self):
                    pass

            def fake_curl_get(self, url, **kw):
                return FakeCurlResponse()

            monkeypatch.setattr(
                "soc_db.scraping.source._HAS_CURL", True
            )
            monkeypatch.setattr(
                "curl_cffi.requests.Session.get", fake_curl_get, raising=False
            )

            result = source.fetch("http://example.com/403")
            assert result == "curl response"
        except ImportError:
            # No curl_cffi — Playwright should be attempted
            pass


class TestHTTPSourceTier2:
    def test_fetch_curl_called_on_403(self, monkeypatch):
        """On httpx 403, curl-cffi should be attempted."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        source = HTTPSource()

        def _raise_conn_error(self, url, headers):
            raise ConnectionError("HTTP 403 — escalate")

        monkeypatch.setattr(
            "soc_db.scraping.source.HTTPSource._fetch_httpx",
            _raise_conn_error
        )

        curl_calls = []

        class FakeCurlResponse:
            status_code = 200
            text = "curl response"

            def raise_for_status(self):
                pass

        def fake_curl_get(self, url, **kw):
            curl_calls.append(url)
            return FakeCurlResponse()

        monkeypatch.setattr("soc_db.scraping.source._HAS_CURL", True)
        monkeypatch.setattr(
            "curl_cffi.requests.Session.get", fake_curl_get, raising=False
        )

        result = source.fetch("http://example.com/403")
        assert result == "curl response"
        assert len(curl_calls) == 1

    def test_fetch_curl_missing_import_skips_tier(self, monkeypatch):
        """If curl-cffi not installed, skip tier 2 and go to tier 3."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        source = HTTPSource()

        def _raise_conn_error(self, url, headers):
            raise ConnectionError("HTTP 403 — escalate")

        monkeypatch.setattr(
            "soc_db.scraping.source.HTTPSource._fetch_httpx",
            _raise_conn_error
        )
        monkeypatch.setattr("soc_db.scraping.source._HAS_CURL", False)
        monkeypatch.setattr("soc_db.scraping.source._HAS_PLAYWRIGHT", False)

        with pytest.raises(RuntimeError, match="Playwright not installed"):
            source.fetch("http://example.com/403")


class TestHTTPSourceTier3:
    def test_fetch_playwright_missing_import_raises(self, monkeypatch):
        """If all tiers fail and Playwright unavailable, raise RuntimeError."""
        source = HTTPSource()

        def fake_httpx_get(self_, url, **kw):
            raise ConnectionError("httpx fail")

        monkeypatch.setattr("httpx.Client.get", fake_httpx_get, raising=False)
        monkeypatch.setattr("soc_db.scraping.source._HAS_CURL", False)
        monkeypatch.setattr("soc_db.scraping.source._HAS_PLAYWRIGHT", False)

        with pytest.raises(RuntimeError, match="Playwright not installed"):
            source.fetch("http://example.com/fail")


class TestHTTPSourceCache:
    def test_cache_miss(self, monkeypatch):
        """No cache → HTTP call made."""
        from pathlib import Path
        monkeypatch.setattr("soc_db.scraping.source.CACHE_DIR", Path("/tmp/nonexistent_cache"))
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)

        source = HTTPSource()

        class FakeResponse:
            status_code = 200
            text = "fresh content"

            def raise_for_status(self):
                pass

        mock_get = MagicMock(return_value=FakeResponse())
        monkeypatch.setattr("httpx.Client.get", mock_get, raising=False)

        result = source.fetch("http://example.com")
        assert result == "fresh content"


class TestHTTPSourceRateLimitIntegration:
    def test_rate_limiter_acquire_called(self, monkeypatch):
        """Rate limiter acquire() called before fetch."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        rl = MagicMock(spec=PerSourceRateLimiter)
        source = HTTPSource(rate_limiter=rl)

        monkeypatch.setattr(
            "soc_db.scraping.source.HTTPSource._fetch_httpx",
            lambda self, url, headers: "content"
        )

        source.fetch("http://example.com")
        rl.acquire.assert_called_once()

    def test_rate_limiter_success_called(self, monkeypatch):
        """record_success() called after successful fetch."""
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        rl = MagicMock(spec=PerSourceRateLimiter)
        source = HTTPSource(rate_limiter=rl)

        monkeypatch.setattr(
            "soc_db.scraping.source.HTTPSource._fetch_httpx",
            lambda self, url, headers: "content"
        )

        source.fetch("http://example.com")
        rl.record_success.assert_called_once()

    def test_rate_limiter_failure_called(self, monkeypatch):
        """record_failure() called after all tiers fail."""
        rl = MagicMock(spec=PerSourceRateLimiter)
        source = HTTPSource(rate_limiter=rl)

        def fake_httpx_get(self_, url, **kw):
            raise ConnectionError("fail")

        monkeypatch.setattr("httpx.Client.get", fake_httpx_get, raising=False)
        monkeypatch.setattr("soc_db.scraping.source._HAS_CURL", False)
        monkeypatch.setattr("soc_db.scraping.source._HAS_PLAYWRIGHT", False)

        with pytest.raises(RuntimeError):
            source.fetch("http://example.com/fail")

        rl.record_failure.assert_called_once()
