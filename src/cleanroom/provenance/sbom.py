"""Parts XXXVII-XXXVIII: SBOM generation (SPDX + CycloneDX) and dependency discovery.

v0.1 scope: parses declared direct dependencies from requirements.txt,
pyproject.toml ([project.dependencies]) and package.json
(dependencies/devDependencies). It does NOT resolve a transitive dependency
tree or fetch registry metadata (licence/hash of the resolved version) --
those fields are populated only where already available on disk (e.g. an
existing lockfile hash), and left null otherwise rather than guessed. This
is a documented limitation, not silently overclaimed completeness (Part
LXVIII: an untested/unresolved field is UNKNOWN, not PASS).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cleanroom.util import new_id, utc_now_iso


@dataclass
class Dependency:
    name: str
    version: str | None
    licence: str | None = None
    source_manifest: str | None = None
    purl: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _parse_requirements_txt(path: Path) -> list[Dependency]:
    deps = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)?\s*([A-Za-z0-9_.\-]*)", line)
        if match:
            name, _, version = match.groups()
            deps.append(Dependency(name=name, version=version or None, source_manifest=path.name, purl=f"pkg:pypi/{name}"))
    return deps


def _parse_pyproject_toml(path: Path) -> list[Dependency]:
    deps = []
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not match:
        return deps
    for item in re.findall(r'"([^"]+)"', match.group(1)):
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)?\s*([A-Za-z0-9_.\-]*)", item)
        if m:
            name, _, version = m.groups()
            deps.append(Dependency(name=name, version=version or None, source_manifest=path.name, purl=f"pkg:pypi/{name}"))
    return deps


def _parse_package_json(path: Path) -> list[Dependency]:
    deps = []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return deps
    for section in ("dependencies", "devDependencies"):
        for name, version in (data.get(section) or {}).items():
            deps.append(Dependency(name=name, version=str(version), source_manifest=path.name, purl=f"pkg:npm/{name}"))
    return deps


def discover_dependencies(root: Path) -> list[Dependency]:
    deps: list[Dependency] = []
    req = root / "requirements.txt"
    if req.is_file():
        deps.extend(_parse_requirements_txt(req))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        deps.extend(_parse_pyproject_toml(pyproject))
    package_json = root / "package.json"
    if package_json.is_file():
        deps.extend(_parse_package_json(package_json))
    return deps


def to_spdx(project_name: str, project_version: str, deps: list[Dependency]) -> dict[str, Any]:
    """Minimal SPDX 2.3 JSON document. See https://spdx.github.io/spdx-spec/v2.3/."""
    packages = [
        {
            "SPDXID": f"SPDXRef-Package-{project_name}",
            "name": project_name,
            "versionInfo": project_version,
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": "NOASSERTION",
        }
    ]
    relationships = []
    for i, dep in enumerate(deps):
        spdx_ref = f"SPDXRef-Package-{i}-{re.sub(r'[^A-Za-z0-9.-]', '-', dep.name)}"
        packages.append(
            {
                "SPDXID": spdx_ref,
                "name": dep.name,
                "versionInfo": dep.version or "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": dep.licence or "NOASSERTION",
                "licenseDeclared": dep.licence or "NOASSERTION",
                "externalRefs": (
                    [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": dep.purl}]
                    if dep.purl
                    else []
                ),
            }
        )
        relationships.append(
            {"spdxElementId": f"SPDXRef-Package-{project_name}", "relationshipType": "DEPENDS_ON", "relatedSpdxElement": spdx_ref}
        )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{project_name}-sbom",
        "documentNamespace": f"https://cleanroom.dev/spdx/{project_name}-{new_id()}",
        "creationInfo": {
            "created": utc_now_iso(),
            "creators": ["Tool: clean-room-coding-0.1.0"],
        },
        "packages": packages,
        "relationships": relationships,
    }


def to_cyclonedx(project_name: str, project_version: str, deps: list[Dependency]) -> dict[str, Any]:
    """Minimal CycloneDX 1.5 JSON document. See https://cyclonedx.org/docs/1.5/json/."""
    components = []
    for dep in deps:
        component: dict[str, Any] = {
            "type": "library",
            "name": dep.name,
            "version": dep.version or "unknown",
        }
        if dep.purl:
            component["purl"] = dep.purl
        if dep.licence:
            component["licenses"] = [{"license": {"id": dep.licence}}]
        if dep.sha256:
            component["hashes"] = [{"alg": "SHA-256", "content": dep.sha256}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{new_id()}",
        "version": 1,
        "metadata": {
            "timestamp": utc_now_iso(),
            "component": {"type": "application", "name": project_name, "version": project_version},
            "tools": [{"vendor": "Clean Room Coding", "name": "cleanroom", "version": "0.1.0"}],
        },
        "components": components,
    }


def save(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
