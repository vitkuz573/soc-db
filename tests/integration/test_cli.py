import os
import subprocess
import sys


def run_cli(*args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    env.setdefault("PYTHONPATH", src)
    return subprocess.run(
        [sys.executable, "-m", "soc_db.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_list_output():
    result = run_cli("list")
    assert result.returncode == 0
    assert "Vendor" in result.stdout
    assert "Qualcomm" in result.stdout or "MediaTek" in result.stdout or "Samsung" in result.stdout


def test_stats_output():
    result = run_cli("stats")
    assert result.returncode == 0
    assert "total_chips" in result.stdout
    assert "total_vendors" in result.stdout
    assert "avg_completeness" in result.stdout


def test_show_chip():
    result = run_cli("show", "sm8550_ac")
    assert result.returncode == 0
    assert "Qualcomm" in result.stdout


def test_query_vendor():
    result = run_cli("query", "--vendor", "Qualcomm")
    assert result.returncode == 0
    assert "Qualcomm" in result.stdout
    assert "chips matched" in result.stdout
    assert "snapdragon" in result.stdout.lower() or "SM" in result.stdout


# ===========================================================================
# CLI filter tests (Phase 14 — UIPLUS-03)
# ===========================================================================


def test_query_completeness_min():
    """--completeness-min filters chips by minimum completeness score."""
    result = run_cli("query", "--completeness-min", "0.5", "--json")
    assert result.returncode == 0
    import json
    chips = json.loads(result.stdout)
    assert len(chips) > 0
    for c in chips:
        assert c.get("completeness", 0) >= 0.5


def test_query_completeness_legacy_alias():
    """--completeness (legacy name) still works."""
    result = run_cli("query", "--completeness", "0.5", "--json")
    assert result.returncode == 0
    import json
    chips = json.loads(result.stdout)
    assert len(chips) > 0
    for c in chips:
        assert c.get("completeness", 0) >= 0.5


def test_query_source_filter():
    """--source filters chips by provenance source name (JSON mode)."""
    env = dict(os.environ)
    env["SOC_DB_USE_JSON"] = "true"
    result = run_cli("query", "--source", "legacy_v2", "--limit", "5", "--json", extra_env=env)
    assert result.returncode == 0
    import json
    chips = json.loads(result.stdout)
    assert len(chips) > 0
    for c in chips:
        prov = c.get("provenance", {})
        sources = set(prov.values())
        assert "legacy_v2" in sources


def test_query_fields_projection():
    """--fields restricts output to specified columns."""
    result = run_cli("query", "--fields", "id,name,vendor", "--limit", "3", "--json")
    assert result.returncode == 0
    import json
    chips = json.loads(result.stdout)
    assert len(chips) > 0
    for c in chips:
        assert set(c.keys()) == {"id", "name", "vendor"}


def test_query_fields_csv():
    """--fields works with --csv output."""
    result = run_cli("query", "--fields", "id,name,vendor", "--limit", "3", "--csv")
    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) >= 2  # header + at least one row
    header = lines[0]
    assert header == "id,name,vendor"


def test_quality_report_cli():
    """soc-db quality-report outputs quality data."""
    result = run_cli("quality-report")
    assert result.returncode == 0
    assert "Quality Report" in result.stdout or "Total chips" in result.stdout or "total_chips" in result.stdout


def test_quality_report_json():
    """soc-db quality-report --json outputs JSON."""
    result = run_cli("quality-report", "--json")
    assert result.returncode == 0
    import json
    report = json.loads(result.stdout)
    assert "summary" in report
    assert "vendors" in report
