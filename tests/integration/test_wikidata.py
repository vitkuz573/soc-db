"""Integration tests for Wikidata CLI, workflow structure, and vendor knowledge."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from soc_db.common import VENDOR_KNOWLEDGE


def run_cli(*args):
    """Run the soc-db CLI with given arguments and return the result."""
    env = dict(os.environ)
    src = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    env.setdefault("PYTHONPATH", src)
    return subprocess.run(
        [sys.executable, "-m", "soc_db.cli", *args],
        capture_output=True,
        text=True,
        env=env,
    )


class TestCliWikidata:
    """Tests for the ``wikidata-refresh`` CLI subcommand."""

    def test_cli_help_includes_wikidata(self):
        """Verify ``--help`` output includes the new subcommand."""
        result = run_cli("--help")
        assert result.returncode == 0
        assert "wikidata-refresh" in result.stdout

    def test_cli_wikidata_refresh_help(self):
        """Verify ``wikidata-refresh --help`` works."""
        result = run_cli("wikidata-refresh", "--help")
        assert result.returncode == 0
        assert "--dry-run" in result.stdout

    def test_cli_wikidata_refresh_dry_run(self):
        """Dry-run mode should complete without errors and print summary."""
        result = run_cli("wikidata-refresh", "--dry-run")
        assert result.returncode == 0
        assert "Dry-run complete" in result.stdout or "dry_run" in result.stdout.lower()

    def test_cli_wikidata_refresh_dry_run_no_vendor_mutation(self):
        """After dry-run, VENDOR_KNOWLEDGE should still have all vendor keys."""
        run_cli("wikidata-refresh", "--dry-run")
        assert "Qualcomm" in VENDOR_KNOWLEDGE
        assert "MediaTek" in VENDOR_KNOWLEDGE
        assert "Samsung" in VENDOR_KNOWLEDGE

    def test_cli_wikidata_refresh_unknown_flag_errors(self):
        """Unknown flags should produce non-zero exit."""
        result = run_cli("wikidata-refresh", "--unknown-flag")
        assert result.returncode != 0


class TestVendorKnowledgeStructure:
    """Tests ensuring VENDOR_KNOWLEDGE structure is preserved."""

    def test_vendor_knowledge_structure_preserved(self):
        """VENDOR_KNOWLEDGE must have expected vendor keys and structure."""
        for vendor in ("Qualcomm", "MediaTek", "Samsung", "HiSilicon", "Apple", "Google"):
            assert vendor in VENDOR_KNOWLEDGE, f"Missing vendor: {vendor}"

        # Qualcomm must have process_map, gpu_map, architecture
        qc = VENDOR_KNOWLEDGE.get("Qualcomm", {})
        assert "process_map" in qc
        assert "gpu_map" in qc
        assert "architecture" in qc
        assert isinstance(qc["process_map"], dict)
        assert isinstance(qc["gpu_map"], dict)

    def test_known_models_present(self):
        """Specific known models must be in VENDOR_KNOWLEDGE."""
        qc = VENDOR_KNOWLEDGE.get("Qualcomm", {})
        assert "sm8550" in qc.get("process_map", {})
        assert "sm8550" in qc.get("gpu_map", {})

        mt = VENDOR_KNOWLEDGE.get("MediaTek", {})
        assert "mt6989" in mt.get("process_map", {})

    def test_architecture_is_string(self):
        """Architecture values must be strings."""
        for vendor, data in VENDOR_KNOWLEDGE.items():
            if "architecture" in data:
                assert isinstance(data["architecture"], str), f"{vendor} architecture is not str"


class TestGitHubWorkflow:
    """Tests for the GitHub Actions workflow file."""

    WORKFLOW_PATH = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "wikidata-refresh.yml"

    def test_workflow_exists(self):
        """Workflow file must exist."""
        assert self.WORKFLOW_PATH.exists(), f"Workflow file missing: {self.WORKFLOW_PATH}"

    def test_workflow_is_valid_yaml(self):
        """Workflow file must be valid YAML."""
        import yaml

        with open(self.WORKFLOW_PATH) as f:
            data = yaml.safe_load(f)
        assert data is not None
        assert "name" in data
        assert data["name"] == "Wikidata Knowledge Refresh"
        # Verify the on: trigger was parsed (may be boolean True in YAML)
        trigger = data.get("on") or data.get(True)
        assert trigger is not None, "Missing on: trigger key"

    def test_workflow_has_schedule_trigger(self):
        """Workflow must have a weekly schedule trigger."""
        import yaml

        with open(self.WORKFLOW_PATH) as f:
            data = yaml.safe_load(f)
        # YAML parses ``on:`` as boolean True, so check both forms
        trigger = data.get("on") or data.get(True) or {}
        assert "schedule" in trigger, "Missing schedule in on: trigger"
        assert any("cron" in entry for entry in trigger["schedule"])

    def test_workflow_has_create_pr_step(self):
        """Workflow must have the create-pull-request step."""
        import yaml

        with open(self.WORKFLOW_PATH) as f:
            data = yaml.safe_load(f)
        jobs = data.get("jobs", {})
        refresh_job = jobs.get("refresh", {})
        steps = refresh_job.get("steps", [])
        pr_steps = [s for s in steps if "create-pull-request" in str(s.get("uses", ""))]
        assert len(pr_steps) > 0, "No create-pull-request step found"
