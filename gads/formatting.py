"""Output helpers: stderr/die, JSON output, micros⇄CZK conversion."""
from __future__ import annotations

import json
import sys


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _die(msg: str, code: int = 1) -> None:
    _err(f"Error: {msg}")
    sys.exit(code)


def _output_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _micros(m) -> float:
    """Convert API micros to currency units."""
    return (m or 0) / 1_000_000


def _fmt_money(m, currency: str = "") -> str:
    return f"{_micros(m):,.2f} {currency}".strip()


def _to_micros(units) -> int:
    """Convert currency units to API micros."""
    return int(round(float(units) * 1_000_000))


def _pct(value, total) -> float:
    return round(value / total * 100, 1) if total else 0.0


def _row_to_dict(row) -> dict:
    """Protobuf GAQL row → plain dict (camelCase keys, enums as names)."""
    from google.protobuf.json_format import MessageToDict
    return MessageToDict(row._pb)
