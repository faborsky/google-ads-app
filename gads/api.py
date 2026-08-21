"""Engine: credentials, client, quota guard, QPS retry, query & mutation runners.

Auth model (configured via .env) — two alternatives:
  A) Installed-app OAuth2: developer_token + client_id + client_secret
     + refresh_token (+ login_customer_id for MCC access). `./run.sh auth`
     generates the refresh token and writes it into .env.
  B) Service account: developer_token + GOOGLE_ADS_JSON_KEY_FILE_PATH (the
     service-account email is added as a user of the Google Ads account in
     Admin → Access and security). No browser flow, no 7-day token expiry.

Quota & rate limits (so the app never gets the account throttled/blocked):
  - Daily operation quota per developer token: Basic Access = 15 000 ops,
    Explorer Access = 2 880 ops on production accounts, Standard = unlimited.
    Google measures it over a SLIDING 24-hour window (access-levels docs), not
    a calendar day. A Search/SearchStream request counts as 1 operation
    regardless of rows; each mutate operation counts as 1. Google does not
    document whether validate_only requests are exempt, so we count them too
    (the local estimate is always >= reality). We keep a per-account log of
    (timestamp, ops) in .quota/ and HARD-STOP before a call would push the
    last-24-h total over the cap (GOOGLE_ADS_DAILY_OP_CAP).
  - Per-second rate limits (QPS, metered per CID + developer token, token
    bucket): the server returns RESOURCE_EXHAUSTED / RESOURCE_TEMPORARILY_-
    EXHAUSTED. We retry those with exponential back-off (honouring Google's
    suggested retry delay). Planning services (Keyword Planner) are
    additionally capped at 1 QPS.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

from gads.formatting import _die, _err

# Project root = parent of the gads/ package, so .env and .quota/ stay where
# they were in the single-file era.
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

API_VERSION = "v25"
QUOTA_DIR = BASE_DIR / ".quota"
QUOTA_WINDOW_SECONDS = 24 * 3600
SCOPES = ["https://www.googleapis.com/auth/adwords"]

# Sensible defaults for Czech accounts.
DEFAULT_LANGUAGE_ID = "1021"      # Czech
DEFAULT_GEO_TARGET_ID = "2203"    # Czech Republic


# ---------------------------------------------------------------------------
# Account / credential resolution (multi-account via env suffixes)
# ---------------------------------------------------------------------------
def _env(key: str, account: str | None) -> str | None:
    """Resolve an env var, preferring the named-account variant when present."""
    if account and account != "default":
        v = os.getenv(f"{key}_{account.upper()}")
        if v:
            return v
    return os.getenv(key)


def _config_dict(account: str | None) -> dict:
    """Build the google-ads client config from .env.

    Service-account mode wins when GOOGLE_ADS_JSON_KEY_FILE_PATH is set;
    otherwise the installed-app OAuth2 keys are required. (The library picks
    the flow by which keys are PRESENT, so the unused trio is left out.)
    """
    suffix = f"_{account.upper()}" if account and account != "default" else ""
    cfg: dict = {
        "developer_token": _env("GOOGLE_ADS_DEVELOPER_TOKEN", account),
        "login_customer_id": _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID", account),
        "use_proto_plus": True,
    }
    key_file = _env("GOOGLE_ADS_JSON_KEY_FILE_PATH", account)
    if key_file:
        path = Path(os.path.expanduser(key_file))
        if not path.is_absolute():
            path = BASE_DIR / path
        if not path.exists():
            _die(f"GOOGLE_ADS_JSON_KEY_FILE_PATH{suffix} ukazuje na neexistující soubor: {path}")
        cfg["json_key_file_path"] = str(path)
        impersonated = _env("GOOGLE_ADS_IMPERSONATED_EMAIL", account)
        if impersonated:
            cfg["impersonated_email"] = impersonated
        missing = [] if cfg["developer_token"] else ["GOOGLE_ADS_DEVELOPER_TOKEN"]
    else:
        cfg.update({
            "client_id": _env("GOOGLE_ADS_CLIENT_ID", account),
            "client_secret": _env("GOOGLE_ADS_CLIENT_SECRET", account),
            "refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN", account),
        })
        missing = [f"GOOGLE_ADS_{k.upper()}" for k in
                   ("developer_token", "client_id", "client_secret", "refresh_token")
                   if not cfg.get(k)]
    if missing:
        _die(
            "Chybí přístupy v .env: " + ", ".join(m + suffix for m in missing)
            + ".\n  Postup: README → Autentizace. Refresh token vygeneruje `./run.sh auth` "
            "(zapíše ho do .env sám); alternativa bez prohlížeče = service account "
            "(GOOGLE_ADS_JSON_KEY_FILE_PATH)."
        )
    # login_customer_id must be digits only (no dashes)
    if cfg["login_customer_id"]:
        cfg["login_customer_id"] = cfg["login_customer_id"].replace("-", "")
    else:
        cfg.pop("login_customer_id")
    return cfg


def _get_client(account: str | None):
    """Build the GoogleAdsClient — with clean, actionable errors instead of
    tracebacks for the classic first-contact failures (expired refresh token,
    bad OAuth client, broken key file)."""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        _die("google-ads není nainstalovaná. Spusť ./setup.sh.")
    from google.auth.exceptions import GoogleAuthError, RefreshError

    cfg = _config_dict(account)
    try:
        return GoogleAdsClient.load_from_dict(cfg, version=API_VERSION)
    except RefreshError as ex:
        detail = str(ex.args[0]) if ex.args else str(ex)
        if "invalid_grant" in detail:
            _die("OAuth refresh token je neplatný nebo expirovaný (invalid_grant). Typické "
                 "příčiny: OAuth consent screen v Cloud Console je v režimu „Testing“ "
                 "(refresh tokeny tam vyprší po 7 dnech — přepni appku na „In production“), "
                 "odvolaný přístup, nebo token z jiného OAuth klienta.\n"
                 "  Oprava: `./run.sh auth` (vygeneruje nový token a zapíše ho do .env). "
                 "Dlouhodobá alternativa bez expirace: service account "
                 "(GOOGLE_ADS_JSON_KEY_FILE_PATH — viz README).")
        if "invalid_client" in detail or "unauthorized_client" in detail:
            _die("OAuth klient odmítnut (invalid_client/unauthorized_client) — zkontroluj "
                 "GOOGLE_ADS_CLIENT_ID a GOOGLE_ADS_CLIENT_SECRET v .env (typ klienta musí "
                 "být „Desktop app“).")
        _die(f"OAuth selhalo: {detail}\n  Zkus `./run.sh auth` pro nový refresh token.")
    except GoogleAuthError as ex:
        _die(f"Autentizace selhala: {ex}")
    except (ValueError, FileNotFoundError) as ex:
        _die(f"Konfigurace klienta selhala: {ex}")
    return None


def _clean_id(cid: str) -> str:
    return cid.replace("-", "").strip()


# ---------------------------------------------------------------------------
# Quota tracking — sliding 24-hour window per account (Google meters the daily
# operation limit over the last 24 h, not per calendar day). Search/SearchStream
# = 1 op per REQUEST (regardless of rows); each mutate operation = 1 op;
# validate_only dry-runs are counted too (conservative — Google doesn't
# document an exemption).
# ---------------------------------------------------------------------------
def _quota_file(account: str | None) -> Path:
    return QUOTA_DIR / f"{(account or 'default').lower()}.json"


def _quota_cap() -> int:
    try:
        return int(os.getenv("GOOGLE_ADS_DAILY_OP_CAP", "15000"))
    except ValueError:
        return 15000


def _atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    """Write a file atomically (temp + rename) so a crash never leaves it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _quota_events(account: str | None, now: float | None = None) -> list[list]:
    """[[timestamp, ops], …] within the last 24 h (older entries are dropped)."""
    now = time.time() if now is None else now
    f = _quota_file(account)
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text())
        events = data.get("events", []) if isinstance(data, dict) else []
    except (ValueError, json.JSONDecodeError, OSError):
        return []
    cutoff = now - QUOTA_WINDOW_SECONDS
    out = []
    for e in events:
        try:
            ts, n = float(e[0]), int(e[1])
        except (TypeError, ValueError, IndexError):
            continue
        if ts > cutoff and n > 0:
            out.append([ts, n])
    return out


def _quota_read(account: str | None, now: float | None = None) -> int:
    """Operations used in the last 24 h (local estimate)."""
    return sum(n for _, n in _quota_events(account, now))


def _quota_oldest_expiry(account: str | None, now: float | None = None) -> float | None:
    """Seconds until the oldest counted op falls out of the window (None = empty)."""
    now = time.time() if now is None else now
    events = _quota_events(account, now)
    if not events:
        return None
    return max(0.0, min(ts for ts, _ in events) + QUOTA_WINDOW_SECONDS - now)


def _track_ops(account: str | None, n: int) -> None:
    if n <= 0:
        return
    now = time.time()
    events = _quota_events(account, now) + [[now, int(n)]]
    _atomic_write_text(_quota_file(account), json.dumps({"events": events}))
    used = sum(k for _, k in events)
    cap = _quota_cap()
    if used >= cap:
        _err(f"⚠️  QUOTA: {used}/{cap} operací za posledních 24 h — limit dosažen.")
    elif used >= cap * 0.8:
        _err(f"⚠️  QUOTA: {used}/{cap} operací za posledních 24 h ({used / cap:.0%}).")


def _quota_guard(account: str | None, n: int) -> None:
    """Refuse BEFORE a call that would exceed the daily operation cap.

    Basic Access = 15 000 ops / sliding 24 h. Standard Access has no daily op
    limit — raise GOOGLE_ADS_DAILY_OP_CAP (or set it very high) so this never
    blocks you. Explorer Access = 2 880 on production accounts — lower the cap.
    """
    if n <= 0:
        return
    cap = _quota_cap()
    used = _quota_read(account)
    if used + n > cap:
        wait = _quota_oldest_expiry(account)
        hint = (f"nejstarší započtené operace vyprší za ~{wait / 60:.0f} min"
                if wait else "okno je prázdné — zvyš cap")
        _die(f"QUOTA: {used}/{cap} operací za posledních 24 h — dalších {n} by překročilo "
             f"denní limit účtu '{(account or 'default')}' ({hint}). Google měří limit "
             f"klouzavě za 24 h. Pokud máš Standard Access (bez denního limitu), zvyš "
             f"GOOGLE_ADS_DAILY_OP_CAP v .env.")


# ---------------------------------------------------------------------------
# Rate-limit retry (QPS) — RESOURCE_EXHAUSTED / RESOURCE_TEMPORARILY_EXHAUSTED
# ---------------------------------------------------------------------------
def _rate_error_retry_after(ex) -> int | None:
    """If the exception is a quota/rate-exhaustion error, return a retry delay in
    seconds (Google's suggested delay when present, else 0 = use our back-off);
    otherwise None (not a rate error → not retryable)."""
    try:
        for err in ex.failure.errors:
            if err.error_code.quota_error:  # RESOURCE_EXHAUSTED / _TEMPORARILY_
                qd = getattr(getattr(err, "details", None), "quota_error_details", None)
                secs = getattr(getattr(qd, "retry_delay", None), "seconds", 0)
                return int(secs) if secs else 0
    except (AttributeError, ValueError):
        pass
    return None


_AUTHZ_HINTS = {
    "DEVELOPER_TOKEN_NOT_APPROVED": (
        "Developer token má jen Test Account Access — na produkční účet nesmí. "
        "Požádej o Basic Access v API Center (Tools → API Center), nebo zkoušej na testovacím účtu."),
    "CLOUD_PROJECT_NOT_APPROVED_FOR_PRODUCTION": (
        "Cloud projekt (OAuth klient) není schválený pro produkční účty — viz README → "
        "Autentizace (přístupová úroveň tokenu a Cloud projekt)."),
    "DEVELOPER_TOKEN_PROHIBITED": (
        "Developer token je pro tento Cloud projekt zakázaný — každý Cloud projekt smí používat "
        "jen jeden developer token (vytvoř nový projekt, nebo použij původní token)."),
    "USER_PERMISSION_DENIED": (
        "Přihlášený uživatel nemá k účtu přístup — zkontroluj GOOGLE_ADS_LOGIN_CUSTOMER_ID (MCC) "
        "a že je účet pod tímhle MCC propojený / uživatel má roli na účtu."),
    "CUSTOMER_NOT_ENABLED": "Účet není aktivní (zrušený / nedokončená registrace).",
}


def _report_google_ads_exception(ex) -> None:
    msgs = []
    hints = []
    for error in ex.failure.errors:
        loc = ""
        if error.location and error.location.field_path_elements:
            loc = " on " + ".".join(e.field_name for e in error.location.field_path_elements)
        msgs.append(f"  - {error.message}{loc}")
        # authorization errors carry the enum name in error_code.authorization_error
        try:
            code = error.error_code.authorization_error.name
        except AttributeError:
            code = ""
        if code in _AUTHZ_HINTS:
            hints.append(f"  ↳ {_AUTHZ_HINTS[code]}")
    _die("Google Ads API request failed (request_id="
         + f"{ex.request_id}):\n" + "\n".join(msgs + hints))


def _execute_with_retry(call, what: str, *, retry_transient: bool = False):
    """Run an API call, retrying on quota/rate exhaustion with exponential
    back-off (honouring Google's suggested delay — the official guidance is
    5→10→20 s). Transient transport errors (UNAVAILABLE / DEADLINE_EXCEEDED /
    INTERNAL) are retried only when `retry_transient` is set — i.e. for READS;
    a write may already have landed, so writes are never replayed. Other
    errors are reported cleanly and abort (never a raw traceback)."""
    from google.ads.googleads.errors import GoogleAdsException
    from google.api_core import exceptions as gexc
    from google.auth.exceptions import GoogleAuthError

    transient = (gexc.ServiceUnavailable, gexc.DeadlineExceeded, gexc.InternalServerError)
    backoff = 5
    for attempt in range(4):  # initial try + up to 3 retries
        try:
            return call()
        except GoogleAdsException as ex:
            retry_after = _rate_error_retry_after(ex)
            if retry_after is None:
                _report_google_ads_exception(ex)  # not a rate error → dies
                return None
            if attempt == 3:
                _die(f"Rate limit ({what}) přetrvává i po 3 pokusech — končím, ať "
                     f"účet nezatěžuju dál. Zkus to za chvíli.")
            wait = retry_after or backoff
            _err(f"⏳ Rate limit ({what}) — čekám {wait}s a zkouším znovu "
                 f"(pokus {attempt + 1}/3)…")
            time.sleep(wait)
            backoff *= 2
        except transient as ex:
            if not retry_transient or attempt == 3:
                _die(f"API dočasně nedostupné ({what}): {ex.__class__.__name__}: "
                     f"{getattr(ex, 'message', ex)}"
                     + ("" if retry_transient else
                        " — zápis se NEopakuje automaticky (mohl už projít): zkontroluj "
                        "stav výpisem a případně spusť znovu."))
                return None
            _err(f"⏳ Přechodná chyba ({what}: {ex.__class__.__name__}) — čekám {backoff}s "
                 f"(pokus {attempt + 1}/3)…")
            time.sleep(backoff)
            backoff *= 2
        except GoogleAuthError as ex:
            _die(f"Autentizace selhala během volání ({what}): {ex}\n"
                 f"  Zkus `./run.sh auth` pro nový refresh token.")
        except gexc.GoogleAPICallError as ex:
            _die(f"API volání selhalo ({what}): {ex.__class__.__name__}: "
                 f"{getattr(ex, 'message', ex)}")
    return None


# ---------------------------------------------------------------------------
# Query execution — a Search/SearchStream request = 1 op regardless of rows.
# ---------------------------------------------------------------------------
def _run_query(client, customer_id: str, gaql: str, account: str | None) -> list:
    service = client.get_service("GoogleAdsService")
    _quota_guard(account, 1)

    def _call() -> list:
        rows: list = []
        stream = service.search_stream(request={"customer_id": customer_id, "query": gaql})
        for batch in stream:
            rows.extend(batch.results)
        return rows

    rows = _execute_with_retry(_call, what=f"query {customer_id}", retry_transient=True) or []
    _track_ops(account, 1)  # 1 op per request — NOT per row
    return rows


# ---------------------------------------------------------------------------
# Mutations — every mutation defaults to validate-only (dry run); --confirm
# performs the real write. Dry-runs are counted toward the local quota
# estimate too (conservatively — see the module docstring).
# ---------------------------------------------------------------------------
def _run_mutation(client, account, customer_id, *, service_name, method_name,
                  request_type, operations, confirm):
    """Execute a mutate request. validate_only=True unless confirm is set."""
    service = client.get_service(service_name)
    request = client.get_type(request_type)
    request.customer_id = customer_id
    for op in operations:
        request.operations.append(op)
    request.validate_only = not confirm

    _quota_guard(account, len(operations))
    response = _execute_with_retry(
        lambda: getattr(service, method_name)(request=request),
        what=f"{method_name} {customer_id}",
    )
    if response is not None:
        _track_ops(account, len(operations))
    return response


def _show_result(response, confirm: bool, label: str) -> None:
    if not confirm:
        print(f"\n✅ VALIDACE OK — {label}.")
        print("   (dry-run: NIC nebylo zapsáno) — přidej --confirm pro skutečný zápis.")
        return
    print(f"\n✅ ZAPSÁNO — {label}:")
    results = getattr(response, "results", None) or []
    for r in results:
        print(f"   {r.resource_name}")


def _field_mask(client, obj):
    """Presence-aware update mask.

    `protobuf_helpers.field_mask(None, msg)` diffs VALUES against defaults, so a
    field deliberately set to its default value — `primary_for_goal = False`,
    `bid_modifier = 0` (device off), an empty `manual_cpc`/`maximize_conversions`
    bidding message — silently drops out of the mask and the API then performs
    a NO-OP update without any error. We therefore add every field that is
    SET on the message (`ListFields()` honours proto3 presence), unless the
    helper already produced a more specific nested path under it.
    """
    from google.api_core import protobuf_helpers
    from google.protobuf import field_mask_pb2
    from google.protobuf.descriptor import FieldDescriptor

    paths = list(protobuf_helpers.field_mask(None, obj._pb).paths)

    def walk(msg, prefix: str) -> None:
        for descriptor, value in msg.ListFields():
            path = prefix + descriptor.name
            # Sub-messages (repeated fields come back as containers without
            # ListFields — they are leaves here; upb descriptors lack `.label`).
            if descriptor.type == FieldDescriptor.TYPE_MESSAGE and hasattr(value, "ListFields"):
                if value.ListFields():
                    walk(value, path + ".")      # recurse down to the leaves
                    continue
                # A mask may not name an EMPTY message field (FieldMaskError
                # FIELD_HAS_SUBFIELDS, verified live on v25) — Google's documented
                # workaround is to name one mutable subfield instead, e.g.
                # "maximize_conversions.target_cpa_micros" for a plain Maximize
                # conversions strategy (client-libs field-masks guide).
                leaf = _EMPTY_MESSAGE_LEAF.get(path)
                if leaf is None:
                    scalars = [f for f in value.DESCRIPTOR.fields
                               if f.type != FieldDescriptor.TYPE_MESSAGE]
                    leaf = f"{path}.{scalars[0].name}" if scalars else path
                if leaf not in paths:
                    paths.append(leaf)
                continue
            if path not in paths:
                paths.append(path)

    walk(obj._pb, "")
    return field_mask_pb2.FieldMask(paths=paths)


# Subfield to name in an update mask when the message itself is set but empty
# (see _field_mask). Only campaign-level (non-portfolio) targets are mutable
# here — never name cpc_bid_ceiling/floor, those are portfolio-only.
_EMPTY_MESSAGE_LEAF = {
    "maximize_conversions": "maximize_conversions.target_cpa_micros",
    "maximize_conversion_value": "maximize_conversion_value.target_roas",
    "manual_cpc": "manual_cpc.enhanced_cpc_enabled",
}


# ---------------------------------------------------------------------------
# Safety: Google Ads has NO undelete — REMOVED is permanent. The rescue brake
# is "PAUSED before REMOVED": removal is refused unless the entity is already
# paused (override with --force).
# ---------------------------------------------------------------------------
def _require_paused_before_remove(client, account, customer_id: str, *,
                                  gaql: str, entity_label: str, force: bool) -> None:
    """Refuse removal of an entity that isn't PAUSED (REMOVED is irreversible).

    `gaql` must select exactly one row whose first field path ends in `.status`.
    """
    if force:
        _err(f"⚠️  --force: přeskakuji pojistku PAUSED-před-REMOVED pro {entity_label}.")
        return
    rows = _run_query(client, customer_id, gaql, account)
    if not rows:
        _die(f"{entity_label} nenalezen(a).")
    row = rows[0]
    # walk to the status field of the first selected resource
    resource = gaql.split("FROM")[1].split()[0].strip()
    attr = {"ad_group_ad": "ad_group_ad"}.get(resource, resource)
    status = getattr(getattr(row, attr), "status").name
    if status != "PAUSED":
        _die(f"POJISTKA: {entity_label} má status {status}, ne PAUSED. REMOVED je "
             f"v Google Ads TRVALÉ (žádné obnovení). Nejdřív pauzni "
             f"(… --status paused --confirm), zkontroluj, a pak teprve maž. "
             f"Vědomé obejití: --force.")
