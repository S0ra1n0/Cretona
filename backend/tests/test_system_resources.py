from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Add scripts directory to sys.path
scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
script_file = scripts_dir / "check-system-resources.py"

spec = importlib.util.spec_from_file_location("check_system_resources", script_file)
assert spec and spec.loader
diag = importlib.util.module_from_spec(spec)
sys.modules["check_system_resources"] = diag
spec.loader.exec_module(diag)


def test_inspect_system_returns_valid_hardware_report():
    report = diag.inspect_system()
    assert report.hardware.cpu_cores >= 1
    assert report.hardware.ram_total_gb > 0
    assert report.hardware.disk_free_gb >= 0
    assert report.recommended_tier in ("mock", "cloud", "local")


def test_tooling_status_detects_python():
    report = diag.inspect_system()
    assert report.tooling.python_version != ""
    assert isinstance(report.recommendations, list)
    assert isinstance(report.warnings, list)
