import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def live_environment():
    return {
        **os.environ,
        "AR_PROVIDER_MODE": "openai_compatible",
        "AR_CHEAP_API_KEY": "",
        "AR_EXPENSIVE_API_KEY": "",
    }


def test_mock_demo_runs_with_incomplete_live_configuration(tmp_path):
    for name in ("run_examples.py", "request.json", "escalation-request.json"):
        shutil.copyfile(ROOT / "demo" / name, tmp_path / name)
    result = subprocess.run(
        [sys.executable, str(tmp_path / "run_examples.py")],
        cwd=tmp_path,
        env=live_environment(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert len(list(tmp_path.glob("*response.json"))) == 5
    response = json.loads((tmp_path / "response.json").read_text(encoding="utf-8"))
    assert response["decision"] == "ACCEPT"
    assert response["selected_path"] == "cheap"


def test_simulation_runner_help_does_not_require_live_credentials():
    result = subprocess.run(
        [sys.executable, str(ROOT / "demo" / "check_llm_routing.py"), "--help"],
        env=live_environment(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "--simulation-url" in result.stdout
