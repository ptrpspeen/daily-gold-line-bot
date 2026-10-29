import os
import subprocess
import textwrap
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "daily-gold.yml"
TODAY = "2026-10-29"


def receipt_check_script() -> str:
    # Execute the workflow's real guard without requiring a YAML dependency.
    step = WORKFLOW.read_text().split("      - name: Check delivery receipt\n", 1)[1]
    step = step.split("\n      - ", 1)[0]
    return textwrap.dedent(step.split("        run: |\n", 1)[1])


@pytest.mark.parametrize(
    ("event", "send_to_line", "force_send", "receipt_day", "expected_skip"),
    [
        pytest.param("workflow_dispatch", True, False, TODAY, True, id="delivered-dispatch"),
        pytest.param("schedule", True, False, TODAY, True, id="delivered-schedule"),
        pytest.param("workflow_dispatch", True, True, TODAY, False, id="forced-delivery"),
        pytest.param("workflow_dispatch", False, False, TODAY, False, id="image-only"),
        pytest.param("workflow_dispatch", True, False, None, False, id="not-delivered"),
        pytest.param("workflow_dispatch", True, False, "2026-10-28", False, id="previous-day"),
    ],
)
def test_delivery_guard(
    tmp_path: Path,
    event: str,
    send_to_line: bool,
    force_send: bool,
    receipt_day: str | None,
    expected_skip: bool,
) -> None:
    if receipt_day:
        receipts = tmp_path / "state" / "sent"
        receipts.mkdir(parents=True)
        (receipts / f"{receipt_day}.json").write_text("{}\n")

    executables = tmp_path / "bin"
    executables.mkdir()
    fake_date = executables / "date"
    fake_date.write_text(f"#!/bin/sh\nprintf '%s\\n' '{TODAY}'\n")
    fake_date.chmod(0o755)
    output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        PATH=f"{executables}{os.pathsep}{environment.get('PATH', '')}",
        GITHUB_EVENT_NAME=event,
        GITHUB_OUTPUT=str(output),
        SEND_TO_LINE=str(send_to_line).lower(),
        FORCE_SEND=str(force_send).lower(),
    )

    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", receipt_check_script()],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert output.read_text() == f"skip={str(expected_skip).lower()}\n", result.stdout
