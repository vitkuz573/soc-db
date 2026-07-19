"""Unit tests for robots.txt caching and compliance checking."""

from unittest.mock import MagicMock, patch

import pytest

from soc_db.robots import RobotsChecker


class TestRobotsChecker:
    def test_can_fetch_allows_when_no_robots(self):
        """Fail-open: if robots.txt unreachable, allow by default."""
        checker = RobotsChecker(ttl=3600)
        result = checker.can_fetch("http://127.0.0.1:1/test", "test-agent")
        assert result is True

    def test_can_fetch_empty_domain(self):
        checker = RobotsChecker()
        assert checker.can_fetch("data:text/plain,hi", "test") is True

    def test_clear_cache(self):
        checker = RobotsChecker(ttl=1)
        # Force a failed fetch entry
        checker.can_fetch("http://127.0.0.1:1/x", "test")
        assert len(checker._parsers) > 0
        checker.clear_cache()
        assert len(checker._parsers) == 0

    def test_can_fetch_uses_cached_parser(self):
        """Same domain should reuse cached parser (exercise cache hit path)."""
        checker = RobotsChecker(ttl=3600)
        # First call populates cache (will fail but that's fine)
        checker.can_fetch("http://127.0.0.1:2/a", "test")
        before = len(checker._parsers)
        checker.can_fetch("http://127.0.0.1:2/b", "test")
        # No new parser added for the same domain
        assert len(checker._parsers) == before

    def test_fetch_raises_on_disallowed_path(self, monkeypatch):
        """If robots.txt disallows a path, fetch raises PermissionError."""
        from soc_db import common as cm

        # Replace the robots checker with one that says False for everything
        class DenyAll:
            def can_fetch(self, url, ua):
                return False

        monkeypatch.setattr(cm, "_robots_checker", DenyAll())
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        with pytest.raises(PermissionError, match="robots.txt disallows"):
            cm.fetch("http://example.com/forbidden")

    def test_fetch_with_custom_user_agent(self, monkeypatch):
        """fetch() passes custom user_agent to the request and robots check."""
        from soc_db import common as cm

        class AllowAll:
            def can_fetch(self, url, ua):
                assert ua == "Custom-UA/1.0"
                return True

        monkeypatch.setattr(cm, "_robots_checker", AllowAll())
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        mock_urlopen_calls = []

        def mock_urlopen(req, **kw):
            mock_urlopen_calls.append(req.get_header("User-agent"))
            from io import BytesIO

            resp = MagicMock()
            resp.read.return_value = b"ok"
            resp.__enter__.return_value = resp
            resp.__exit__ = lambda *a: None
            return resp

        monkeypatch.setattr(cm, "urlopen", mock_urlopen)
        cm.fetch("http://example.com/custom", user_agent="Custom-UA/1.0")
        assert any("Custom-UA/1.0" in h for h in mock_urlopen_calls), str(
            mock_urlopen_calls
        )

    def test_fetch_default_user_agent(self, monkeypatch):
        """fetch() uses the module USER_AGENT when no custom UA is passed."""
        from soc_db import common as cm

        class AllowAll:
            def can_fetch(self, url, ua):
                assert ua == cm.USER_AGENT
                return True

        monkeypatch.setattr(cm, "_robots_checker", AllowAll())
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        mock_urlopen_calls = []

        def mock_urlopen(req, **kw):
            mock_urlopen_calls.append(req.get_header("User-agent"))
            from io import BytesIO

            resp = MagicMock()
            resp.read.return_value = b"ok"
            resp.__enter__.return_value = resp
            resp.__exit__ = lambda *a: None
            return resp

        monkeypatch.setattr(cm, "urlopen", mock_urlopen)
        cm.fetch("http://example.com/default")
        assert any(cm.USER_AGENT in str(h) for h in mock_urlopen_calls), str(
            mock_urlopen_calls
        )
