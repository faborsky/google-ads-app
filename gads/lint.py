"""Preflight lint — local (free) checks of ad texts against Google Ads editorial
policy BEFORE any API call. Hard limits (counts/lengths) kill the command; style
findings are printed as warnings and validate_only remains the final arbiter.

Policy source: Google Ads editorial requirements (support.google.com/adspolicy)
+ RSA asset specs. Verified 2026-07-19 against API v24.
"""
from __future__ import annotations

import re

from gads.formatting import _die, _err

# Abbreviations commonly (and legitimately) written in caps — not SHOUTING.
_CAPS_OK = {
    "AI", "SEO", "PPC", "CRM", "DPH", "ČR", "SR", "EU", "USA", "UK", "IT",
    "GPT", "API", "B2B", "B2C", "SaaS", "HR", "PR", "CEO", "ROI", "KPI",
    "GA4", "GTM", "RSA", "DSA", "FAQ", "PDF", "CSS", "HTML", "SQL", "MBA",
}

RSA_HEADLINE_MAX = 30
RSA_DESCRIPTION_MAX = 90
RSA_HEADLINES_RANGE = (3, 15)
RSA_DESCRIPTIONS_RANGE = (2, 4)
PATH_MAX = 15

SITELINK_TEXT_MAX = 25
SITELINK_DESC_MAX = 35
CALLOUT_MAX = 25
SNIPPET_VALUE_MAX = 25
SNIPPET_VALUES_RANGE = (3, 10)
# Structured snippet headers must come from Google's fixed localized list.
SNIPPET_HEADERS = [
    "Amenities", "Brands", "Courses", "Degree programs", "Destinations",
    "Featured hotels", "Insurance coverage", "Models", "Neighborhoods",
    "Service catalog", "Shows", "Styles", "Types",
]


def _style_findings(text: str, *, is_headline: bool) -> list[str]:
    """Google editorial-policy style checks for one ad text."""
    findings = []
    if is_headline and "!" in text:
        findings.append("vykřičník v headline (Google je v headlines zakazuje)")
    if not is_headline and text.count("!") > 1:
        findings.append("víc než jeden vykřičník")
    if re.search(r"[!?.,]{2,}", text.replace("...", "").replace("…", "")):
        findings.append("opakovaná interpunkce (!!, ?? …)")
    words = re.findall(r"[^\W\d_]{3,}", text)
    shouting = [w for w in words if w.isupper() and w not in _CAPS_OK]
    if shouting:
        findings.append(f"CAPS slova (vypadá jako křičení): {', '.join(shouting)}")
    if "  " in text or text != text.strip():
        findings.append("nadbytečné mezery")
    if re.search(r"[♥★☆✓✔➤►]|[\U0001F300-\U0001FAFF]", text):
        findings.append("symboly/emoji (editorial policy je v textech nepovoluje)")
    return findings


def lint_rsa(headlines: list[str], descriptions: list[str],
             path1: str | None = None, path2: str | None = None) -> None:
    """Hard-fail on count/length violations; print style warnings otherwise."""
    lo, hi = RSA_HEADLINES_RANGE
    if not (lo <= len(headlines) <= hi):
        _die(f"RSA potřebuje {lo}–{hi} headlines (máš {len(headlines)}).")
    lo, hi = RSA_DESCRIPTIONS_RANGE
    if not (lo <= len(descriptions) <= hi):
        _die(f"RSA potřebuje {lo}–{hi} descriptions (máš {len(descriptions)}).")
    too_long = [t for t in headlines if len(t) > RSA_HEADLINE_MAX]
    if too_long:
        _die(f"Headlines max {RSA_HEADLINE_MAX} znaků, překračují: {too_long}")
    too_long = [t for t in descriptions if len(t) > RSA_DESCRIPTION_MAX]
    if too_long:
        _die(f"Descriptions max {RSA_DESCRIPTION_MAX} znaků, překračují: {too_long}")
    for p, name in ((path1, "path1"), (path2, "path2")):
        if p and len(p) > PATH_MAX:
            _die(f"{name} max {PATH_MAX} znaků: '{p}'")

    warnings: list[str] = []
    for texts, is_h, label in ((headlines, True, "headline"), (descriptions, False, "description")):
        seen: set[str] = set()
        for t in texts:
            for f in _style_findings(t, is_headline=is_h):
                warnings.append(f"{label} „{t}“: {f}")
            key = t.lower().strip()
            if key in seen:
                warnings.append(f"duplicitní {label}: „{t}“ (API duplicity odmítne)")
            seen.add(key)
    if warnings:
        _err(f"⚠️  LINT ({len(warnings)}) — zkontroluj před zápisem:")
        for w in warnings:
            _err(f"   - {w}")


def lint_texts(items: list[str], *, max_len: int, label: str) -> None:
    """Generic length + style check for asset texts (sitelinks, callouts…)."""
    too_long = [t for t in items if len(t) > max_len]
    if too_long:
        _die(f"{label} max {max_len} znaků, překračují: {too_long}")
    warnings = []
    for t in items:
        for f in _style_findings(t, is_headline=True):
            warnings.append(f"{label} „{t}“: {f}")
    if warnings:
        _err(f"⚠️  LINT ({len(warnings)}):")
        for w in warnings:
            _err(f"   - {w}")
