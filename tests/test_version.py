import subprocess
import sys

import tum_daily_assistant


def test_version_constant():
    assert tum_daily_assistant.__version__ == "0.1.0.dev0"


def test_cli_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "tum_daily_assistant", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "0.1.0.dev0"


def test_cli_stub_subcommands_report_not_implemented():
    for command in ("run", "discover", "preview", "settings"):
        result = subprocess.run(
            [sys.executable, "-m", "tum_daily_assistant", command],
            capture_output=True,
            text=True,
        )
        assert "not implemented" in result.stdout
