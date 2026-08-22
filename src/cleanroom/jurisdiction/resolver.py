"""Parts XII-XIV: jurisdiction resolution.

Builds a JURISDICTION_MATRIX from a project's configured markets and the
available jurisdiction packs. Deliberately does NOT default to any single
jurisdiction (Part XII: "Do not automatically use England and Wales /
United States / the developer's / the licensor's jurisdiction"). A market
with no matching pack is recorded as tier "unknown", never silently
dropped.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from cleanroom.util import utc_now_iso

# ISO 3166-1 alpha-2 / 'eu' -> jurisdiction pack id. Extend as packs are added.
COUNTRY_TO_PACK = {
    "gb": "england-wales",
    "uk": "england-wales",
    "us": "usa-federal",
}

LEGAL_ISSUES = [
    "copyright", "licence_contract", "patents", "trademarks",
    "database_rights", "trade_secrets", "confidentiality",
    "consumer_law", "competition_law",
]

_PACKAGE_DIR = Path(__file__).resolve().parent


def _candidate_pack_roots() -> list[Path]:
    candidates = []
    for parent in _PACKAGE_DIR.parents:
        candidate = parent / "jurisdictions"
        if candidate.is_dir():
            candidates.append(candidate)
    return candidates


@functools.lru_cache(maxsize=1)
def pack_root() -> Path | None:
    for candidate in _candidate_pack_roots():
        if any(candidate.glob("*/framework.yml")):
            return candidate
    return None


@functools.lru_cache(maxsize=None)
def load_pack(pack_id: str) -> dict[str, Any] | None:
    root = pack_root()
    if root is None:
        return None
    path = root / pack_id / "framework.yml"
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def available_packs() -> list[str]:
    root = pack_root()
    if root is None:
        return []
    return sorted(p.parent.name for p in root.glob("*/framework.yml"))


def build_matrix(
    *,
    project_id: str,
    required_markets: list[str],
    informational_markets: list[str] | None = None,
) -> dict[str, Any]:
    informational_markets = informational_markets or []
    issues = []
    panels_convened: set[str] = set()

    for issue in LEGAL_ISSUES:
        jurisdictions = []
        for market in required_markets:
            jurisdictions.append(_entry_for_market(market, tier="primary", basis=["markets"]))
            pack_id = COUNTRY_TO_PACK.get(market.lower())
            if pack_id:
                panels_convened.add(pack_id)
        for market in informational_markets:
            if market in required_markets:
                continue
            jurisdictions.append(_entry_for_market(market, tier="secondary", basis=["markets"]))
        issues.append({"issue": issue, "jurisdictions": jurisdictions})

    return {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "generated_utc": utc_now_iso(),
        "issues": issues,
        "conflicts_of_law_panel_required": len({*required_markets, *informational_markets}) > 1,
        "legal_panels_convened": sorted(panels_convened),
    }


def _entry_for_market(market: str, *, tier: str, basis: list[str]) -> dict[str, Any]:
    pack_id = COUNTRY_TO_PACK.get(market.lower())
    if pack_id and load_pack(pack_id):
        reasoning = (
            f"'{market}' is a configured distribution market with an available jurisdiction "
            f"pack ({pack_id})."
        )
    else:
        pack_id = None
        reasoning = (
            f"'{market}' is a configured distribution market, but no jurisdiction pack is "
            "available for it in this installation -- treat as UNKNOWN, not resolved, until "
            "a pack is added or qualified local counsel is consulted (Part LXIII)."
        )
        tier = "unknown"
    return {"jurisdiction": market, "tier": tier, "reasoning": reasoning, "basis": basis}
