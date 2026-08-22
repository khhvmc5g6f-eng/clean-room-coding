"""Parts XXXVII-XXXVIII: SBOM generation (SPDX + CycloneDX) and dependency discovery.

v0.1 scope: parses declared direct dependencies from requirements.txt,
pyproject.toml ([project.dependencies]) and package.json
(dependencies/devDependencies). It does NOT resolve a transitive dependency
tree or fetch registry metadata (licence/hash of the resolved version) --
those fields are populated only where already available on disk (e.g. an
existing lockfile hash), and left null otherwise rather than guessed. This
is a documented limitation, not silently overclaimed completeness (Part
LXVIII: an untested/unresolved field is UNKNOWN, not PASS).

Since the 2026-08-22 integration research, `to_spdx()`/`to_cyclonedx()`
build real `spdx_tools`/`cyclonedx-python-lib` model objects and serialize
through each library's own converter, rather than hand-typing JSON that
merely resembles the format -- the output is schema-validated for real
(`validate_full_spdx_document()` / `make_schemabased_validator()`, both
exercised in tests/unit/test_sbom.py). Discovery (`discover_dependencies`)
is unchanged; only the serialization half these libraries are for was
replaced.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cleanroom.licence.spdx import parse as parse_spdx_expression
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


def _spdx_id(prefix: str, name: str) -> str:
    return f"{prefix}-{re.sub(r'[^A-Za-z0-9.-]', '-', name)}"


def _spdx_license_value(licence: str | None) -> Any:
    """A real SPDX license-expression object for `license_concluded`/
    `license_declared`, or SpdxNoAssertion() when `licence` is missing or
    isn't a real SPDX-recognised expression -- passing an unrecognised bare
    identifier through as-is produces a document `validate_full_spdx_document`
    correctly flags as non-conformant (confirmed by direct testing), so we
    don't emit one rather than silently shipping invalid output."""
    from spdx_tools.spdx.model.spdx_no_assertion import SpdxNoAssertion

    if not licence:
        return SpdxNoAssertion()
    parsed = parse_spdx_expression(licence)
    if not parsed.all_known:
        return SpdxNoAssertion()
    from license_expression import get_spdx_licensing

    return get_spdx_licensing().parse(licence, validate=False)


def to_spdx(project_name: str, project_version: str, deps: list[Dependency]) -> dict[str, Any]:
    """Real SPDX 2.3 JSON document, built via `spdx_tools`'s model/converter
    (not hand-typed) so the output is genuinely schema-conformant. See
    https://spdx.github.io/spdx-spec/v2.3/."""
    from spdx_tools.spdx.model import (
        Actor, ActorType, CreationInfo, Document, Package, Relationship, RelationshipType,
    )
    from spdx_tools.spdx.model.package import ExternalPackageRef, ExternalPackageRefCategory
    from spdx_tools.spdx.model.spdx_no_assertion import SpdxNoAssertion
    from spdx_tools.spdx.jsonschema.document_converter import DocumentConverter

    root_id = _spdx_id("SPDXRef-Package", project_name)
    creation_info = CreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name=f"{project_name}-sbom",
        document_namespace=f"https://cleanroom.dev/spdx/{project_name}-{new_id()}",
        creators=[Actor(ActorType.TOOL, "clean-room-coding-0.1.0")],
        created=datetime.now(timezone.utc),
    )
    packages = [
        Package(
            spdx_id=root_id, name=project_name, version=project_version,
            download_location=SpdxNoAssertion(), license_concluded=SpdxNoAssertion(),
        )
    ]
    relationships = [Relationship("SPDXRef-DOCUMENT", RelationshipType.DESCRIBES, root_id)]
    for i, dep in enumerate(deps):
        dep_id = _spdx_id(f"SPDXRef-Package-{i}", dep.name)
        licence_value = _spdx_license_value(dep.licence)
        packages.append(
            Package(
                spdx_id=dep_id, name=dep.name, version=dep.version or "NOASSERTION",
                download_location=SpdxNoAssertion(),
                license_concluded=licence_value,
                license_declared=licence_value,
                external_references=(
                    [ExternalPackageRef(ExternalPackageRefCategory.PACKAGE_MANAGER, "purl", dep.purl)]
                    if dep.purl
                    else []
                ),
            )
        )
        relationships.append(Relationship(root_id, RelationshipType.DEPENDS_ON, dep_id))

    document = Document(creation_info, packages=packages, relationships=relationships)
    converted = DocumentConverter().convert(document)
    # spdx-tools 0.8.5 serializes ExternalPackageRefCategory via the Python
    # enum's .name ("PACKAGE_MANAGER"), but the real SPDX 2.3 JSON schema
    # requires the hyphenated spec value ("PACKAGE-MANAGER") -- confirmed
    # directly against spdx/spdx-spec's spdx-schema-2-3.json. Corrected here
    # rather than silently shipping the library's non-conformant value.
    for pkg in converted.get("packages", []):
        for ref in pkg.get("externalRefs", []):
            ref["referenceCategory"] = ref["referenceCategory"].replace("_", "-")
    return converted


def to_cyclonedx(project_name: str, project_version: str, deps: list[Dependency]) -> dict[str, Any]:
    """Real CycloneDX 1.5 JSON document, built via `cyclonedx-python-lib`'s
    model/outputter (not hand-typed) so the output is genuinely schema-
    conformant. See https://cyclonedx.org/docs/1.5/json/."""
    from packageurl import PackageURL

    from cyclonedx.model import HashAlgorithm, HashType
    from cyclonedx.model.bom import Bom, BomMetaData
    from cyclonedx.model.bom_ref import BomRef
    from cyclonedx.model.component import Component, ComponentType
    from cyclonedx.model.dependency import Dependency as CdxDependency
    from cyclonedx.model.license import LicenseExpression
    from cyclonedx.model.tool import ToolRepository
    from cyclonedx.output import make_outputter
    from cyclonedx.schema import OutputFormat, SchemaVersion

    root_ref = BomRef(_spdx_id("cleanroom-root", project_name))
    root_component = Component(name=project_name, version=project_version, type=ComponentType.APPLICATION, bom_ref=root_ref)

    components = []
    dependency_entries = []
    for i, dep in enumerate(deps):
        dep_ref = BomRef(_spdx_id(f"cleanroom-dep-{i}", dep.name))
        licences = []
        parsed = parse_spdx_expression(dep.licence) if dep.licence else None
        if parsed is not None and parsed.all_known:
            licences.append(LicenseExpression(dep.licence))
        hashes = [HashType(alg=HashAlgorithm.SHA_256, content=dep.sha256)] if dep.sha256 else []
        components.append(
            Component(
                name=dep.name, version=dep.version or "unknown", type=ComponentType.LIBRARY, bom_ref=dep_ref,
                purl=PackageURL.from_string(dep.purl) if dep.purl else None,
                licenses=licences,
                hashes=hashes,
            )
        )
        dependency_entries.append(CdxDependency(ref=dep_ref))

    # CycloneDX 1.5 deprecated the flat `metadata.tools` list of `Tool` in
    # favour of describing the producing tool as a `Component` inside a
    # `ToolRepository` (confirmed: constructing with a bare `Tool` list
    # raises `SchemaDeprecationWarning1Dot5` under SchemaVersion.V1_5).
    tool_component = Component(name="cleanroom", version="0.1.0", type=ComponentType.APPLICATION, group="Clean Room Coding")
    bom = Bom(
        metadata=BomMetaData(
            component=root_component,
            tools=ToolRepository(components=[tool_component]),
        ),
        components=components,
        dependencies=[CdxDependency(ref=root_ref, dependencies=dependency_entries)] + dependency_entries,
    )
    outputter = make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_5)
    return json.loads(outputter.output_as_string())


def save(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
