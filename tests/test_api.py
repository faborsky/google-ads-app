"""Engine tests: credential resolution, clean auth errors, sliding-window quota
guard, retry policy, dry-run mutations."""
from __future__ import annotations

import json
import time

import pytest
from google.protobuf import duration_pb2

from gads import api

from conftest import Stub, ns  # noqa: F401  (ns used by other modules)


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def test_config_installed_app_from_env():
    cfg = api._config_dict(None)
    assert cfg["developer_token"] == "fake-dev-token"
    assert cfg["refresh_token"] == "fake-refresh"
    assert cfg["login_customer_id"] == "1234567890"  # dashes stripped
    assert "json_key_file_path" not in cfg


def test_config_missing_credentials_dies_with_var_names(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_ADS_REFRESH_TOKEN")
    monkeypatch.delenv("GOOGLE_ADS_CLIENT_SECRET")
    with pytest.raises(SystemExit):
        api._config_dict(None)
    err = capsys.readouterr().err
    assert "GOOGLE_ADS_REFRESH_TOKEN" in err and "GOOGLE_ADS_CLIENT_SECRET" in err
    assert "Traceback" not in err


def test_config_named_account_prefers_suffixed_vars(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN_KLIENTB", "token-b")
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID_KLIENTB", "999")
    cfg = api._config_dict("klientb")
    assert cfg["refresh_token"] == "token-b"
    assert cfg["login_customer_id"] == "999"
    assert cfg["developer_token"] == "fake-dev-token"  # falls back to the default var


def test_config_named_account_missing_suffixed_var_names_the_account(monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_ADS_REFRESH_TOKEN")
    with pytest.raises(SystemExit):
        api._config_dict("klientb")
    assert "GOOGLE_ADS_REFRESH_TOKEN_KLIENTB" in capsys.readouterr().err


def test_config_service_account_mode(monkeypatch, tmp_path):
    key = tmp_path / "sa.json"
    key.write_text("{}")
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", str(key))
    monkeypatch.setenv("GOOGLE_ADS_IMPERSONATED_EMAIL", "ops@example.com")
    monkeypatch.delenv("GOOGLE_ADS_REFRESH_TOKEN")  # not needed in SA mode
    cfg = api._config_dict(None)
    assert cfg["json_key_file_path"] == str(key)
    assert cfg["impersonated_email"] == "ops@example.com"
    # the installed-app trio must be ABSENT (the library picks the flow by key presence)
    assert not {"client_id", "client_secret", "refresh_token"} & cfg.keys()


def test_config_service_account_relative_path_resolves_against_repo(monkeypatch, tmp_path):
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets" / "sa.json").write_text("{}")
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", ".secrets/sa.json")
    cfg = api._config_dict(None)
    assert cfg["json_key_file_path"] == str(tmp_path / ".secrets" / "sa.json")


def test_config_service_account_missing_file_dies(monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_ADS_JSON_KEY_FILE_PATH", "/nope/missing.json")
    with pytest.raises(SystemExit):
        api._config_dict(None)
    assert "neexistující soubor" in capsys.readouterr().err


def test_get_client_invalid_grant_is_clean_and_actionable(monkeypatch, capsys):
    from google.ads.googleads.client import GoogleAdsClient
    from google.auth.exceptions import RefreshError

    def boom(cls, cfg, version=None):
        raise RefreshError("invalid_grant: Bad Request", {"error": "invalid_grant"})

    monkeypatch.setattr(GoogleAdsClient, "load_from_dict", classmethod(boom))
    with pytest.raises(SystemExit):
        api._get_client(None)
    err = capsys.readouterr().err
    assert "invalid_grant" in err and "run.sh auth" in err and "Testing" in err
    assert "Traceback" not in err


def test_get_client_invalid_client_points_at_oauth_client(monkeypatch, capsys):
    from google.ads.googleads.client import GoogleAdsClient
    from google.auth.exceptions import RefreshError

    def boom(cls, cfg, version=None):
        raise RefreshError("invalid_client: Unauthorized")

    monkeypatch.setattr(GoogleAdsClient, "load_from_dict", classmethod(boom))
    with pytest.raises(SystemExit):
        api._get_client(None)
    assert "GOOGLE_ADS_CLIENT_ID" in capsys.readouterr().err


def test_get_client_uses_pinned_api_version(monkeypatch):
    from google.ads.googleads.client import GoogleAdsClient
    seen = {}
    monkeypatch.setattr(GoogleAdsClient, "load_from_dict",
                        classmethod(lambda cls, cfg, version=None: seen.update(version=version)))
    api._get_client(None)
    assert seen["version"] == api.API_VERSION == "v25"


# ---------------------------------------------------------------------------
# Quota: sliding 24 h window, hard stop BEFORE the call
# ---------------------------------------------------------------------------

def test_quota_counts_and_persists():
    api._track_ops(None, 3)
    api._track_ops(None, 2)
    assert api._quota_read(None) == 5
    data = json.loads(api._quota_file(None).read_text())
    assert len(data["events"]) == 2


def test_quota_is_a_sliding_24h_window():
    now = time.time()
    api.QUOTA_DIR.mkdir()
    api._quota_file(None).write_text(json.dumps({"events": [
        [now - 25 * 3600, 14000],   # older than 24 h → must NOT count
        [now - 1 * 3600, 10],
    ]}))
    assert api._quota_read(None) == 10
    api._track_ops(None, 1)  # rewrite prunes the stale entry
    assert len(json.loads(api._quota_file(None).read_text())["events"]) == 2


def test_quota_oldest_expiry_reports_minutes_until_relief():
    now = time.time()
    api.QUOTA_DIR.mkdir()
    api._quota_file(None).write_text(json.dumps({"events": [[now - 23 * 3600, 5]]}))
    wait = api._quota_oldest_expiry(None, now=now)
    assert 3500 < wait <= 3600


def test_quota_guard_hard_stops_before_exceeding(monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_ADS_DAILY_OP_CAP", "100")
    api._track_ops(None, 99)
    api._quota_guard(None, 1)  # exactly at cap is still allowed
    with pytest.raises(SystemExit):
        api._quota_guard(None, 2)
    err = capsys.readouterr().err
    assert "QUOTA" in err and "24 h" in err


def test_quota_guard_is_per_account(monkeypatch):
    monkeypatch.setenv("GOOGLE_ADS_DAILY_OP_CAP", "10")
    api._track_ops("klienta", 10)
    api._quota_guard("klientb", 5)  # another account is unaffected
    with pytest.raises(SystemExit):
        api._quota_guard("klienta", 1)


def test_quota_corrupt_file_is_treated_as_empty():
    api.QUOTA_DIR.mkdir()
    api._quota_file(None).write_text("{not json")
    assert api._quota_read(None) == 0


def test_quota_warns_at_80_percent(monkeypatch, capsys):
    monkeypatch.setenv("GOOGLE_ADS_DAILY_OP_CAP", "10")
    api._track_ops(None, 8)
    assert "80%" in capsys.readouterr().err


def test_atomic_write_sets_mode_and_replaces(tmp_path):
    target = tmp_path / "f.txt"
    api._atomic_write_text(target, "one", mode=0o600)
    api._atomic_write_text(target, "two", mode=0o600)
    assert target.read_text() == "two"
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

def _gads_exception(client, *, quota=False, retry_secs=0, authz=None, message="boom"):
    from google.ads.googleads.errors import GoogleAdsException
    failure = client.get_type("GoogleAdsFailure")
    err = client.get_type("GoogleAdsError")
    err.message = message
    if quota:
        err.error_code.quota_error = client.get_type("QuotaErrorEnum").QuotaError.RESOURCE_EXHAUSTED
        if retry_secs:
            err.details.quota_error_details.retry_delay = duration_pb2.Duration(seconds=retry_secs)
    if authz:
        err.error_code.authorization_error = getattr(
            client.get_type("AuthorizationErrorEnum").AuthorizationError, authz)
    failure.errors.append(err)
    return GoogleAdsException(None, None, failure, "req-123")


def test_retry_rate_error_backs_off_then_succeeds(fake_client, monkeypatch, capsys):
    waits = []
    monkeypatch.setattr(api.time, "sleep", lambda s: waits.append(s))
    attempts = {"n": 0}

    def call():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _gads_exception(fake_client, quota=True)
        return "ok"

    assert api._execute_with_retry(call, "test") == "ok"
    assert waits == [5, 10]  # official 5→10→20 schedule
    assert "Rate limit" in capsys.readouterr().err


def test_retry_honours_google_retry_delay(fake_client, monkeypatch):
    waits = []
    monkeypatch.setattr(api.time, "sleep", lambda s: waits.append(s))
    attempts = {"n": 0}

    def call():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise _gads_exception(fake_client, quota=True, retry_secs=7)
        return "ok"

    api._execute_with_retry(call, "test")
    assert waits == [7]


def test_retry_gives_up_after_three_retries(fake_client, capsys):
    def call():
        raise _gads_exception(fake_client, quota=True)

    with pytest.raises(SystemExit):
        api._execute_with_retry(call, "test")
    assert "3 pokusech" in capsys.readouterr().err


def test_non_rate_error_dies_with_request_id_and_hint(fake_client, capsys):
    def call():
        raise _gads_exception(fake_client, authz="DEVELOPER_TOKEN_NOT_APPROVED",
                              message="The developer token is not approved.")

    with pytest.raises(SystemExit):
        api._execute_with_retry(call, "test")
    err = capsys.readouterr().err
    assert "req-123" in err and "not approved" in err and "Basic Access" in err
    assert "Traceback" not in err


def test_transient_error_retried_for_reads_only(monkeypatch, capsys):
    from google.api_core import exceptions as gexc
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise gexc.ServiceUnavailable("503")
        return "ok"

    assert api._execute_with_retry(flaky, "query", retry_transient=True) == "ok"

    def always():
        raise gexc.ServiceUnavailable("503")

    with pytest.raises(SystemExit):
        api._execute_with_retry(always, "mutate_campaigns")  # a write: never replayed
    assert "NEopakuje" in capsys.readouterr().err


def test_auth_error_during_call_is_clean(capsys):
    from google.auth.exceptions import RefreshError

    def call():
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    with pytest.raises(SystemExit):
        api._execute_with_retry(call, "query")
    err = capsys.readouterr().err
    assert "run.sh auth" in err and "Traceback" not in err


# ---------------------------------------------------------------------------
# Mutations: validate_only by default, counted toward the local quota estimate
# ---------------------------------------------------------------------------

def test_run_mutation_defaults_to_validate_only(recorder, fake_client):
    op = fake_client.get_type("CampaignOperation")
    op.update.resource_name = "customers/1234567890/campaigns/1"
    api._run_mutation(fake_client, None, "1234567890", service_name="CampaignService",
                      method_name="mutate_campaigns", request_type="MutateCampaignsRequest",
                      operations=[op], confirm=False)
    req = recorder.last("mutate_campaigns")["request"]
    assert req.validate_only is True
    assert req.customer_id == "1234567890"
    assert api._quota_read(None) == 1  # dry-runs are counted (conservative)


def test_run_mutation_confirm_writes_and_counts_each_operation(recorder, fake_client):
    ops = []
    for i in range(3):
        op = fake_client.get_type("CampaignOperation")
        op.update.resource_name = f"customers/1234567890/campaigns/{i}"
        ops.append(op)
    api._run_mutation(fake_client, None, "1234567890", service_name="CampaignService",
                      method_name="mutate_campaigns", request_type="MutateCampaignsRequest",
                      operations=ops, confirm=True)
    assert recorder.last("mutate_campaigns")["request"].validate_only is False
    assert api._quota_read(None) == 3


def test_run_query_counts_one_op_regardless_of_rows(recorder, fake_client, row_factory):
    recorder.rows = [row_factory() for _ in range(50)]
    rows = api._run_query(fake_client, "1234567890", "SELECT campaign.id FROM campaign", None)
    assert len(rows) == 50
    assert api._quota_read(None) == 1
    assert recorder.last("search_stream")["request"]["query"].startswith("SELECT")
