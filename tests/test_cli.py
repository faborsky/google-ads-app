"""End-to-end CLI behaviour via subprocess (a student's first-contact paths).
Runs with EMPTY credentials so nothing ever reaches the network."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from gads import __version__

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(APP_DIR, "google_ads_cli.py")


def _run(*argv, creds: bool = False):
    """Run the CLI. Empty-string env vars win over .env (dotenv never overrides
    existing variables), so the real .env is neutralised."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_ADS_")}
    for k in ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
              "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
              "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_JSON_KEY_FILE_PATH"):
        env[k] = ""
    return subprocess.run([sys.executable, CLI, *argv], capture_output=True, text=True,
                          env=env, cwd=APP_DIR, timeout=90)


def test_help_works_without_configured_env():
    r = _run("--help")
    assert r.returncode == 0
    assert "usage:" in r.stdout and "pulse" in r.stdout


def test_version_works_without_configured_env():
    r = _run("--version")
    assert r.returncode == 0
    assert __version__ in r.stdout


def test_subcommand_help_shows_confirm_flag():
    r = _run("campaign-create", "--help")
    assert r.returncode == 0
    assert "--confirm" in r.stdout and "--json" in r.stdout


def test_missing_credentials_fail_cleanly():
    r = _run("campaigns", "1234567890")
    assert r.returncode == 1
    assert "Chybí přístupy v .env" in r.stderr
    assert "Traceback" not in r.stderr


def test_json_flag_keeps_stdout_clean_on_error_path():
    r = _run("campaigns", "1234567890", "--json")
    assert r.returncode == 1
    assert r.stdout.strip() == ""


def test_json_accepted_after_subcommand():
    r = _run("quota", "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["window"] == "sliding 24 h" and data["daily_cap"] == 15000


def test_json_accepted_before_subcommand():
    r = _run("--json", "api-limits")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["limits"]["api_version"] == "v25"


def test_human_output_has_no_banner_when_piped():
    r = _run("quota")
    assert r.returncode == 0
    assert "██" not in r.stdout  # banner is TTY-only


def test_unknown_command_is_a_usage_error():
    r = _run("campaign-restore", "1234567890")
    assert r.returncode == 2
    assert "invalid choice" in r.stderr


def test_every_subcommand_help_renders():
    """Each subparser must build and print help (catches wiring typos)."""
    r = _run("--help")
    block = r.stdout.split("{", 1)[1].split("}", 1)[0]
    commands = [c.strip() for c in block.replace("\n", "").split(",") if c.strip()]
    assert len(commands) == 85
    for cmd in commands:
        rr = _run(cmd, "--help")
        assert rr.returncode == 0, f"{cmd} --help failed: {rr.stderr}"
