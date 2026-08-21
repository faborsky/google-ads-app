"""Shared fixtures. No test may ever touch the real API, the real .env or .quota/.

Strategy: a REAL GoogleAdsClient (v25 proto stubs, fake credentials, no network)
so every operation the CLI builds is validated against the actual API types —
and the gRPC service methods are replaced by a recorder that captures requests
and returns stubs. The engine (quota guard, retry, validate_only) runs for real.
"""
from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gads import api  # noqa: E402
from gads.commands import auth as auth_cmd  # noqa: E402

# Service methods the CLI calls — all replaced by the recorder.
SERVICE_METHODS = {
    "GoogleAdsService": ["mutate", "search_stream"],
    "CustomerService": ["list_accessible_customers"],
    "CampaignService": ["mutate_campaigns"],
    "CampaignBudgetService": ["mutate_campaign_budgets"],
    "AdGroupService": ["mutate_ad_groups"],
    "AdGroupAdService": ["mutate_ad_group_ads"],
    "AdService": ["mutate_ads"],
    "AdGroupCriterionService": ["mutate_ad_group_criteria"],
    "CampaignCriterionService": ["mutate_campaign_criteria"],
    "SharedSetService": ["mutate_shared_sets"],
    "SharedCriterionService": ["mutate_shared_criteria"],
    "CampaignSharedSetService": ["mutate_campaign_shared_sets"],
    "CustomerNegativeCriterionService": ["mutate_customer_negative_criteria"],
    "AssetService": ["mutate_assets"],
    "CampaignAssetService": ["mutate_campaign_assets"],
    "AdGroupAssetService": ["mutate_ad_group_assets"],
    "CustomerAssetService": ["mutate_customer_assets"],
    "UserListService": ["mutate_user_lists"],
    "LabelService": ["mutate_labels"],
    "CampaignLabelService": ["mutate_campaign_labels"],
    "AdGroupLabelService": ["mutate_ad_group_labels"],
    "AdGroupAdLabelService": ["mutate_ad_group_ad_labels"],
    "AdGroupCriterionLabelService": ["mutate_ad_group_criterion_labels"],
    "ConversionActionService": ["mutate_conversion_actions"],
    "RecommendationService": ["apply_recommendation", "dismiss_recommendation"],
    "ExperimentService": ["mutate_experiments", "schedule_experiment",
                          "end_experiment", "promote_experiment"],
    "ExperimentArmService": ["mutate_experiment_arms"],
    "GeoTargetConstantService": ["suggest_geo_target_constants"],
    "KeywordPlanIdeaService": ["generate_keyword_ideas"],
}


class Stub:
    """Duck-typed stand-in for any API response: attributes + iterable."""

    def __init__(self, **kw):
        self._items = kw.pop("_items", [])
        self.__dict__.update(kw)

    def __iter__(self):
        return iter(self._items)


class Recorder:
    """Captures every service call; `rows` feeds search_stream results."""

    def __init__(self):
        self.calls: list[dict] = []
        self.rows: list = []

    def last(self, method: str | None = None) -> dict:
        calls = [c for c in self.calls if method is None or c["method"] == method]
        assert calls, f"no recorded call for {method!r}; have {[c['method'] for c in self.calls]}"
        return calls[-1]

    def methods(self) -> list[str]:
        return [c["method"] for c in self.calls]


def _make_client():
    from google.ads.googleads.client import GoogleAdsClient
    from google.oauth2.credentials import Credentials
    return GoogleAdsClient(credentials=Credentials(token="fake-access-token"),
                           developer_token="fake-dev-token",
                           login_customer_id="1234567890",
                           version=api.API_VERSION, use_proto_plus=True)


@pytest.fixture(scope="session")
def fake_client():
    return _make_client()


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Redirect all persistent state to a temp dir, scrub real credentials,
    make sleeps instant and make the client factory return the fake client."""
    monkeypatch.setattr(api, "QUOTA_DIR", tmp_path / ".quota")
    monkeypatch.setattr(api, "BASE_DIR", tmp_path)
    monkeypatch.setattr(api, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(auth_cmd, "BASE_DIR", tmp_path)
    monkeypatch.setattr(auth_cmd, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(api.time, "sleep", lambda s: None)
    for k in list(os.environ):
        if k.startswith("GOOGLE_ADS_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-dev-token")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_ID", "fake.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_ADS_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("GOOGLE_ADS_REFRESH_TOKEN", "fake-refresh")
    monkeypatch.setenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "123-456-7890")
    monkeypatch.setenv("GOOGLE_ADS_DAILY_OP_CAP", "15000")


@pytest.fixture
def recorder(monkeypatch, fake_client):
    """Patch every service method the CLI uses + the client factory."""
    from google.ads.googleads.client import GoogleAdsClient

    rec = Recorder()
    monkeypatch.setattr(GoogleAdsClient, "load_from_dict",
                        classmethod(lambda cls, cfg, version=None: fake_client))

    def make(service_name, method_name):
        def fake(self, request=None, **kwargs):
            rec.calls.append({"service": service_name, "method": method_name,
                              "request": request, "kwargs": kwargs})
            if method_name == "search_stream":
                return [Stub(results=list(rec.rows))]
            result = Stub(resource_name="customers/1234567890/stub/1", experiment_arm=None)
            return Stub(results=[result], mutate_operation_responses=[],
                        name="operations/stub", resource_names=[],
                        geo_target_constant_suggestions=[], _items=[])
        return fake

    for svc, methods in SERVICE_METHODS.items():
        cls = type(fake_client.get_service(svc))
        for m in methods:
            assert hasattr(cls, m), f"{svc}.{m} missing in {api.API_VERSION} stubs"
            monkeypatch.setattr(cls, m, make(svc, m))
    return rec


def ns(**kw):
    """argparse.Namespace factory with the global defaults filled in."""
    import argparse
    base = {"account": None, "json": False, "customer_id": "123-456-7890", "confirm": False}
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def row_factory(fake_client):
    """Build a GoogleAdsRow with nested fields set from a dict of dotted paths."""
    def build(**fields):
        row = fake_client.get_type("GoogleAdsRow")
        for path, value in fields.items():
            obj = row
            parts = path.split(".")
            for p in parts[:-1]:
                obj = getattr(obj, p)
            setattr(obj, parts[-1], value)
        return row
    return build
