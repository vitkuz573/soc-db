import os
import subprocess
import sys


def _cli_env():
    """Return env with PYTHONPATH set so the package is importable."""
    env = dict(os.environ)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    env.setdefault("PYTHONPATH", src)
    return env


class TestCLI:
    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "soc_db", "--help"],
            capture_output=True,
            text=True,
            env=_cli_env(),
        )
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()

    def test_list_command(self):
        result = subprocess.run(
            [sys.executable, "-m", "soc_db", "list", "--help"],
            capture_output=True,
            text=True,
            env=_cli_env(),
        )
        assert result.returncode == 0
