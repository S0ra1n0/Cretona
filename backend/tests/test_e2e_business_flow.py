from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Add scripts directory to sys.path
scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
script_file = scripts_dir / "test-e2e-business-flow.py"

spec = importlib.util.spec_from_file_location("test_e2e_business_flow_script", script_file)
assert spec and spec.loader
e2e_mod = importlib.util.module_from_spec(spec)
sys.modules["test_e2e_business_flow_script"] = e2e_mod
spec.loader.exec_module(e2e_mod)


def test_complete_end_to_end_business_flow():
    """Execute complete 9-step business lifecycle in pytest."""
    e2e_mod.run_e2e_business_flow(mode="dev")
