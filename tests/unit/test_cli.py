import subprocess
import sys


class TestCLI:
    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "soc_db", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()

    def test_list_command(self):
        result = subprocess.run(
            [sys.executable, "-m", "soc_db", "list", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
