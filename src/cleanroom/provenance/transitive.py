"""Part XXXVII (extension): opt-in transitive dependency resolution.

`sbom.discover_dependencies()` reads direct dependencies only, straight
from a manifest file -- a documented v0.1 limitation (see ROADMAP.md).
This module closes that gap for the two ecosystems `sbom.py` already
understands (PyPI, npm) by walking each dependency's *real* registry
metadata (PyPI's JSON API, the npm registry API) -- read-only HTTP GET
requests for published package metadata. It never installs a package or
executes any of its code (no `pip install`, no `setup.py`, no npm
lifecycle scripts), so it's safe to run against dependency names taken
from an untrusted reference project's manifest.

This makes real network calls to third-party registries and is therefore
opt-in (`cleanroom provenance --resolve-transitive`), never the default --
`cleanroom provenance`'s existing offline behaviour is unchanged unless a
user asks for this. A registry lookup that fails (network error, unknown
package, rate limit) is recorded as `unresolved` with a reason, never
silently dropped or guessed at.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

_TIMEOUT_SECONDS = 10
_MAX_DEPTH = 5  # guards against pathological or (in principle) circular dependency graphs
_USER_AGENT = "clean-room-coding/0.1.0 (+https://github.com/khhvmc5g6f-eng/clean-room-coding)"

_REQUIRES_DIST_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


@dataclass
class TransitiveDependency:
    name: str
    ecosystem: str  # "pypi" | "npm"
    depth: int
    required_by: str
    version: str | None = None
    licence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "ecosystem": self.ecosystem, "depth": self.depth, "required_by": self.required_by}
        if self.version:
            d["version"] = self.version
        if self.licence:
            d["licence"] = self.licence
        return d


@dataclass
class TransitiveResolution:
    resolved: list[TransitiveDependency] = field(default_factory=list)
    unresolved: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"resolved": [d.to_dict() for d in self.resolved], "unresolved": self.unresolved}


def _http_get_json(url: str) -> dict[str, Any] | None:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 -- fixed https registry hosts only
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def _pypi_lookup(name: str, version: str | None) -> tuple[str | None, list[str], str | None] | None:
    """Returns (resolved_version, direct_dependency_names, licence), or
    None if the PyPI JSON API lookup failed."""
    url = f"https://pypi.org/pypi/{name}/{version}/json" if version else f"https://pypi.org/pypi/{name}/json"
    data = _http_get_json(url)
    if data is None:
        return None
    info = data.get("info") or {}
    resolved_version = info.get("version")
    licence = info.get("license") or None
    names: list[str] = []
    for requirement in info.get("requires_dist") or []:
        # A marker like "; extra == 'test'" means this dependency is only
        # needed for an optional extra, not the base install -- skip it
        # rather than pulling in test/dev-only subtrees no consumer of the
        # base package actually needs.
        if ";" in requirement and "extra ==" in requirement:
            continue
        match = _REQUIRES_DIST_NAME_RE.match(requirement.strip())
        if match:
            names.append(match.group(1))
    return resolved_version, names, licence


def _npm_lookup(name: str, version: str | None) -> tuple[str | None, list[str], str | None] | None:
    """Returns (resolved_version, direct_dependency_names, licence), or
    None if the npm registry lookup failed."""
    data = _http_get_json(f"https://registry.npmjs.org/{name}")
    if data is None:
        return None
    versions = data.get("versions") or {}
    resolved_version = version if version in versions else (data.get("dist-tags") or {}).get("latest")
    version_data = versions.get(resolved_version) if resolved_version else None
    if not version_data:
        return None
    licence = version_data.get("license")
    if isinstance(licence, dict):
        licence = licence.get("type")
    names = list((version_data.get("dependencies") or {}).keys())
    return resolved_version, names, licence


def _lookup(ecosystem: str, name: str, version: str | None) -> tuple[str | None, list[str], str | None] | None:
    # Dispatches by name through the module namespace (rather than a
    # dict bound to the functions at import time) so tests can monkeypatch
    # `_pypi_lookup`/`_npm_lookup` directly and have this pick up the
    # replacement.
    import cleanroom.provenance.transitive as _self

    return _self._pypi_lookup(name, version) if ecosystem == "pypi" else _self._npm_lookup(name, version)


def resolve_transitive(deps: list[Any], *, max_depth: int = _MAX_DEPTH) -> TransitiveResolution:
    """`deps` are the direct `Dependency` objects from
    `sbom.discover_dependencies()`. Walks each one's real registry
    metadata breadth-first to `max_depth`, deduping by (ecosystem, name)
    so a diamond dependency is only resolved once rather than
    re-fetched/re-queued per path that reaches it."""
    result = TransitiveResolution()
    seen: set[tuple[str, str]] = set()
    queue: list[tuple[str, str | None, str, int, str]] = []

    for dep in deps:
        ecosystem = "npm" if (dep.purl or "").startswith("pkg:npm/") else "pypi"
        queue.append((dep.name, dep.version, ecosystem, 1, "(direct)"))

    while queue:
        name, version, ecosystem, depth, required_by = queue.pop(0)
        key = (ecosystem, name.lower())
        if key in seen:
            continue
        seen.add(key)

        if depth > max_depth:
            result.unresolved.append({"name": name, "ecosystem": ecosystem, "reason": f"max resolution depth ({max_depth}) exceeded"})
            continue

        lookup = _lookup(ecosystem, name, version)
        if lookup is None:
            result.unresolved.append({"name": name, "ecosystem": ecosystem, "reason": "registry lookup failed (network error, unknown package, or rate limit)"})
            continue

        resolved_version, child_names, licence = lookup
        result.resolved.append(
            TransitiveDependency(name=name, ecosystem=ecosystem, depth=depth, required_by=required_by, version=resolved_version, licence=licence)
        )
        for child_name in child_names:
            queue.append((child_name, None, ecosystem, depth + 1, name))

    return result
