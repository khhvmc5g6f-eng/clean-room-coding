"""Parts XXXVII-XXXVIII: SBOM generation (SPDX + CycloneDX) and dependency discovery.

`discover_dependencies()` parses declared *direct* dependencies from
requirements.txt, pyproject.toml ([project.dependencies]), package.json
(dependencies/devDependencies), Cargo.toml ([dependencies]/
[dev-dependencies]/[build-dependencies], real TOML parsing via
`tomllib`/`tomli`, not a regex) and composer.json (require/require-dev,
skipping platform pseudo-packages like `php`/`ext-*`/`lib-*`). It does not
itself fetch registry metadata (licence/hash of the resolved version) --
those fields are populated only where already available on disk (e.g. an
existing lockfile hash) or via `provenance/transitive.py`'s opt-in
`--resolve-transitive` real registry lookups (PyPI and npm only; Cargo/
Composer dependencies are recorded `unresolved` with an honest reason if
`--resolve-transitive` is used, since no crates.io/Packagist lookup is
implemented yet), and left null otherwise rather than guessed. This is a
documented limitation, not silently overclaimed completeness (Part
LXVIII: an untested/unresolved field is UNKNOWN, not PASS).

`to_spdx()`/`to_cyclonedx()` build real `spdx_tools`/`cyclonedx-python-lib`
model objects and serialize through each library's own converter, rather
than hand-typing JSON that merely resembles the format -- the output is
schema-validated for real (`validate_full_spdx_document()` /
`make_schemabased_validator()`, both exercised in tests/unit/test_sbom.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cleanroom.licence.spdx import parse as parse_spdx_expression
from cleanroom.util import new_id, utc_now_iso

if TYPE_CHECKING:
    from cleanroom.provenance.transitive import TransitiveResolution


_PURL_ECOSYSTEM_PREFIXES = {"pkg:npm/": "npm", "pkg:cargo/": "cargo", "pkg:composer/": "composer"}


def _dependency_ecosystem(purl: str | None) -> str:
    for prefix, ecosystem in _PURL_ECOSYSTEM_PREFIXES.items():
        if (purl or "").startswith(prefix):
            return ecosystem
    return "pypi"


def _load_toml(path: Path) -> dict[str, Any]:
    """Real TOML parsing (stdlib `tomllib` on 3.11+, the `tomli` backport
    on 3.10) -- not a hand-rolled regex, since Cargo.toml's dependency
    tables use shapes a `pyproject.toml`-style `dependencies = [...]` list
    regex can't represent (bare string versions, inline tables with a
    `version` key, path/git-only entries with no version at all)."""
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[import-not-found, no-redef]

    with open(path, "rb") as f:
        return tomllib.load(f)


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


def _parse_cargo_toml(path: Path) -> list[Dependency]:
    deps = []
    try:
        data = _load_toml(path)
    except (OSError, ValueError):
        return deps
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, value in (data.get(section) or {}).items():
            if isinstance(value, str):
                version = value
            elif isinstance(value, dict):
                version = value.get("version")
            else:
                version = None
            if version is None:
                # A path/git-only dependency (no registry version) isn't a
                # third-party component this SBOM can meaningfully name --
                # skipped rather than listed with a fabricated version.
                continue
            deps.append(Dependency(name=name, version=str(version), source_manifest=path.name, purl=f"pkg:cargo/{name}"))
    return deps


_COMPOSER_PLATFORM_PACKAGE_RE = re.compile(r"^(php|hhvm|ext-|lib-)")


def _parse_composer_json(path: Path) -> list[Dependency]:
    deps = []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return deps
    for section in ("require", "require-dev"):
        for name, version in (data.get(section) or {}).items():
            if _COMPOSER_PLATFORM_PACKAGE_RE.match(name):
                # A platform requirement (PHP itself, an HHVM version, a
                # PHP extension, a system library) -- not an installable
                # third-party package this SBOM can list a component for.
                continue
            deps.append(Dependency(name=name, version=str(version), source_manifest=path.name, purl=f"pkg:composer/{name}"))
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
    cargo_toml = root / "Cargo.toml"
    if cargo_toml.is_file():
        deps.extend(_parse_cargo_toml(cargo_toml))
    composer_json = root / "composer.json"
    if composer_json.is_file():
        deps.extend(_parse_composer_json(composer_json))
    return deps


def _spdx_id(prefix: str, name: str) -> str:
    return f"{prefix}-{re.sub(r'[^A-Za-z0-9.-]', '-', name)}"


# Algorithms provenance/transitive.py's registry-derived digests actually
# use ("<algorithm>:<hex>", e.g. "sha256:..."/"sha512:..."/"sha1:...") --
# an unrecognised algorithm is dropped from the SBOM rather than
# fabricated as one of these.
_SPDX_DIGEST_ALGORITHMS = {"sha256": "SHA256", "sha512": "SHA512", "sha1": "SHA1"}
_CYCLONEDX_DIGEST_ALGORITHMS = {"sha256": "SHA_256", "sha512": "SHA_512", "sha1": "SHA_1"}


def _parse_digest(digest: str | None) -> tuple[str, str] | None:
    """Splits a "<algorithm>:<hex>" digest string (see
    provenance/transitive.py) into (algorithm, hex), or None if `digest`
    is absent or not in that shape."""
    if not digest or ":" not in digest:
        return None
    algorithm, _, hex_value = digest.partition(":")
    return algorithm.lower(), hex_value


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


def to_spdx(
    project_name: str, project_version: str, deps: list[Dependency],
    *, transitive: "TransitiveResolution | None" = None,
) -> dict[str, Any]:
    """Real SPDX 2.3 JSON document, built via `spdx_tools`'s model/converter
    (not hand-typed) so the output is genuinely schema-conformant. See
    https://spdx.github.io/spdx-spec/v2.3/.

    `transitive`, if given (from `provenance.transitive.resolve_transitive`),
    adds every non-direct resolved dependency as its own package with a
    DEPENDS_ON relationship from its real parent -- depth-1 entries are
    skipped since those are the same dependencies already added from
    `deps` above, not a duplicate. A transitive entry whose parent can't
    be matched (e.g. `transitive` was resolved against a different `deps`
    list) is still included as a package, just without that one edge,
    rather than being dropped."""
    from spdx_tools.spdx.model import (
        Actor, ActorType, CreationInfo, Document, Package, Relationship, RelationshipType,
    )
    from spdx_tools.spdx.model.checksum import Checksum, ChecksumAlgorithm
    from spdx_tools.spdx.model.package import ExternalPackageRef, ExternalPackageRefCategory
    from spdx_tools.spdx.model.spdx_no_assertion import SpdxNoAssertion
    from spdx_tools.spdx.jsonschema.document_converter import DocumentConverter

    def _spdx_checksums(digest: str | None) -> list[Any]:
        parsed = _parse_digest(digest)
        if parsed is None or parsed[0] not in _SPDX_DIGEST_ALGORITHMS:
            return []
        return [Checksum(ChecksumAlgorithm[_SPDX_DIGEST_ALGORITHMS[parsed[0]]], parsed[1])]

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
    id_by_key: dict[tuple[str, str], str] = {}
    for i, dep in enumerate(deps):
        dep_id = _spdx_id(f"SPDXRef-Package-{i}", dep.name)
        id_by_key[(_dependency_ecosystem(dep.purl), dep.name)] = dep_id
        licence_value = _spdx_license_value(dep.licence)
        packages.append(
            Package(
                spdx_id=dep_id, name=dep.name, version=dep.version or "NOASSERTION",
                download_location=SpdxNoAssertion(),
                license_concluded=licence_value,
                license_declared=licence_value,
                checksums=_spdx_checksums(f"sha256:{dep.sha256}" if dep.sha256 else None),
                external_references=(
                    [ExternalPackageRef(ExternalPackageRefCategory.PACKAGE_MANAGER, "purl", dep.purl)]
                    if dep.purl
                    else []
                ),
            )
        )
        relationships.append(Relationship(root_id, RelationshipType.DEPENDS_ON, dep_id))

    if transitive is not None:
        for i, tdep in enumerate(transitive.resolved):
            if tdep.depth == 1:
                continue  # already added above from `deps` -- not a duplicate package
            key = (tdep.ecosystem, tdep.name)
            tdep_id = _spdx_id(f"SPDXRef-Package-t{i}", tdep.name)
            id_by_key[key] = tdep_id
            licence_value = _spdx_license_value(tdep.licence)
            packages.append(
                Package(
                    spdx_id=tdep_id, name=tdep.name, version=tdep.version or "NOASSERTION",
                    download_location=SpdxNoAssertion(),
                    license_concluded=licence_value, license_declared=licence_value,
                    checksums=_spdx_checksums(tdep.digest),
                )
            )
            parent_id = id_by_key.get((tdep.ecosystem, tdep.required_by))
            if parent_id is not None:
                relationships.append(Relationship(parent_id, RelationshipType.DEPENDS_ON, tdep_id))

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


def to_cyclonedx(
    project_name: str, project_version: str, deps: list[Dependency],
    *, transitive: "TransitiveResolution | None" = None,
) -> dict[str, Any]:
    """Real CycloneDX 1.5 JSON document, built via `cyclonedx-python-lib`'s
    model/outputter (not hand-typed) so the output is genuinely schema-
    conformant. See https://cyclonedx.org/docs/1.5/json/.

    `transitive`, if given, adds every non-direct resolved dependency as
    its own component, nested under its real parent in the dependency
    graph -- see `to_spdx()`'s docstring for the same caveats (depth-1
    entries skipped as duplicates, an unmatched parent doesn't drop the
    component, just that one edge)."""
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

    def _cyclonedx_hashes(digest: str | None) -> list[Any]:
        parsed = _parse_digest(digest)
        if parsed is None or parsed[0] not in _CYCLONEDX_DIGEST_ALGORITHMS:
            return []
        return [HashType(alg=HashAlgorithm[_CYCLONEDX_DIGEST_ALGORITHMS[parsed[0]]], content=parsed[1])]

    root_ref = BomRef(_spdx_id("cleanroom-root", project_name))
    root_component = Component(name=project_name, version=project_version, type=ComponentType.APPLICATION, bom_ref=root_ref)

    components = []
    ref_by_key: dict[tuple[str, str], BomRef] = {}
    children_by_ref: dict[BomRef, list[BomRef]] = {root_ref: []}

    for i, dep in enumerate(deps):
        dep_ref = BomRef(_spdx_id(f"cleanroom-dep-{i}", dep.name))
        ref_by_key[(_dependency_ecosystem(dep.purl), dep.name)] = dep_ref
        children_by_ref.setdefault(dep_ref, [])
        children_by_ref[root_ref].append(dep_ref)
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

    if transitive is not None:
        for i, tdep in enumerate(transitive.resolved):
            if tdep.depth == 1:
                continue  # already added above from `deps` -- not a duplicate component
            key = (tdep.ecosystem, tdep.name)
            tdep_ref = BomRef(_spdx_id(f"cleanroom-trans-{i}", tdep.name))
            ref_by_key[key] = tdep_ref
            children_by_ref.setdefault(tdep_ref, [])
            parent_ref = ref_by_key.get((tdep.ecosystem, tdep.required_by))
            if parent_ref is not None:
                children_by_ref.setdefault(parent_ref, []).append(tdep_ref)
            licences = (
                [LicenseExpression(tdep.licence)]
                if tdep.licence and parse_spdx_expression(tdep.licence).all_known
                else []
            )
            components.append(
                Component(
                    name=tdep.name, version=tdep.version or "unknown", type=ComponentType.LIBRARY, bom_ref=tdep_ref,
                    licenses=licences,
                    hashes=_cyclonedx_hashes(tdep.digest),
                )
            )

    dependency_entries = [
        CdxDependency(ref=ref, dependencies=[CdxDependency(ref=child) for child in children])
        for ref, children in children_by_ref.items()
    ]

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
        dependencies=dependency_entries,
    )
    outputter = make_outputter(bom, OutputFormat.JSON, SchemaVersion.V1_5)
    return json.loads(outputter.output_as_string())


def save(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
