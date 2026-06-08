import json
import subprocess
import sys
from pathlib import Path


def test_update_data_script_runs_from_repo_root(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    output = tmp_path / "latest.json"
    archive = tmp_path / "history"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/update_data.py",
            "--config",
            "config/tickers.json",
            "--output",
            str(output),
            "--archive-dir",
            str(archive),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "sample_fallback"
    assert payload["tickers"]

