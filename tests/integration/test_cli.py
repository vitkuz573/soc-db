import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "soc_db.cli", *args],
        capture_output=True,
        text=True,
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
