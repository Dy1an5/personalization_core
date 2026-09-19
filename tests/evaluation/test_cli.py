import json
from pathlib import Path

import pytest

from personalization_core.evaluation.cli import main
from personalization_core.evaluation.runner import default_dataset_path

pytestmark = pytest.mark.unit


def test_cli_writes_json_and_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    json_path = tmp_path / "reports" / "evaluation.json"
    markdown_path = tmp_path / "reports" / "evaluation.md"

    exit_code = main(
        [
            "--json-out",
            str(json_path),
            "--markdown-out",
            str(markdown_path),
        ]
    )

    assert exit_code == 0
    assert json.loads(json_path.read_text(encoding="utf-8"))["metrics"]
    assert "Overall: **PASS**" in markdown_path.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_cli_returns_input_error_for_missing_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--dataset", str(tmp_path / "missing.json")])

    assert exit_code == 2
    assert "evaluation input error" in capsys.readouterr().err


def test_cli_returns_one_when_a_metric_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.loads(default_dataset_path().read_text(encoding="utf-8"))
    payload["memory_extraction"][0]["predicted_keys"] = ["unexpected"]
    dataset_path = tmp_path / "failing.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["--dataset", str(dataset_path)]) == 1
    assert '"passed": false' in capsys.readouterr().out
