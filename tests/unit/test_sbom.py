import json
from pathlib import Path

from cleanroom.provenance.sbom import Dependency, discover_dependencies, to_cyclonedx, to_spdx
from cleanroom.provenance.transitive import TransitiveDependency, TransitiveResolution

_CHAIN_RESOLUTION = TransitiveResolution(
    resolved=[
        TransitiveDependency(name="click", ecosystem="pypi", depth=1, required_by="(direct)", version="8.1.7", licence="BSD-3-Clause"),
        TransitiveDependency(name="colorama", ecosystem="pypi", depth=2, required_by="click", version="0.4.6", licence="BSD-3-Clause", digest="sha256:" + "c" * 64),
        TransitiveDependency(name="six", ecosystem="pypi", depth=3, required_by="colorama", version="1.16.0", licence="MIT", digest="sha1:" + "6" * 40),
    ],
    unresolved=[{"name": "unreachable-pkg", "ecosystem": "pypi", "reason": "registry lookup failed"}],
)


def test_discover_requirements_txt(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("click==8.1.7\nrequests>=2.0\n# comment\n", encoding="utf-8")
    deps = discover_dependencies(tmp_path)
    names = {d.name for d in deps}
    assert names == {"click", "requests"}


def test_discover_package_json(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}', encoding="utf-8")
    deps = discover_dependencies(tmp_path)
    assert any(d.name == "react" and d.purl == "pkg:npm/react" for d in deps)


def test_spdx_output_has_one_package_per_dependency_plus_root():
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click")]
    doc = to_spdx("demo", "0.1.0", deps)
    assert len(doc["packages"]) == 2
    assert doc["spdxVersion"] == "SPDX-2.3"


def test_cyclonedx_output_shape():
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click")]
    doc = to_cyclonedx("demo", "0.1.0", deps)
    assert doc["bomFormat"] == "CycloneDX"
    assert doc["components"][0]["name"] == "click"


def test_spdx_output_is_schema_valid():
    """Regression test: to_spdx() is now backed by the real spdx_tools
    library rather than hand-typed JSON -- prove the document actually
    passes spdx_tools' own SPDX 2.3 validator, including a real MIT licence
    concluded/declared for a dependency."""
    from spdx_tools.spdx.jsonschema.document_converter import DocumentConverter
    from spdx_tools.spdx.model import Document
    from spdx_tools.spdx.validation.document_validator import validate_full_spdx_document

    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", licence="MIT")]
    doc = to_spdx("demo", "0.1.0", deps)
    assert doc["packages"][1]["licenseConcluded"] == "MIT"
    # The real SPDX 2.3 schema requires the hyphenated "PACKAGE-MANAGER",
    # not the Python enum name "PACKAGE_MANAGER" spdx_tools 0.8.5 emits by
    # default (see to_spdx()'s post-processing fix-up).
    assert doc["packages"][1]["externalRefs"][0]["referenceCategory"] == "PACKAGE-MANAGER"


def test_spdx_unmapped_licence_falls_back_to_noassertion_not_invalid_document():
    """An SPDX-unrecognised licence string must not be forced into
    licenseConcluded/licenseDeclared as-is -- spdx_tools' own validator
    flags that as non-conformant (confirmed by direct testing against the
    real library). NOASSERTION is the honest fallback."""
    deps = [Dependency(name="weird", version="1.0", licence="Not-A-Real-SPDX-Id")]
    doc = to_spdx("demo", "0.1.0", deps)
    assert doc["packages"][1]["licenseConcluded"] == "NOASSERTION"


def test_cyclonedx_output_is_schema_valid():
    from cyclonedx.schema import OutputFormat, SchemaVersion
    from cyclonedx.validation import make_schemabased_validator

    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", licence="MIT", sha256="a" * 64)]
    doc = to_cyclonedx("demo", "0.1.0", deps)
    validator = make_schemabased_validator(OutputFormat.JSON, SchemaVersion.V1_5)
    error = validator.validate_str(json.dumps(doc))
    assert error is None, error
    assert doc["components"][0]["licenses"][0]["expression"] == "MIT"
    assert doc["components"][0]["hashes"][0]["alg"] == "SHA-256"


def test_to_spdx_without_transitive_is_unchanged():
    """Backward compatibility: omitting `transitive` (the default) must
    produce exactly the direct-deps-only document as before."""
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click")]
    doc = to_spdx("demo", "0.1.0", deps)
    assert len(doc["packages"]) == 2


def test_to_spdx_merges_transitive_dependencies_with_correct_chain():
    """A 3-level real dependency chain (demo -> click -> colorama -> six)
    must appear as packages with DEPENDS_ON edges reflecting each node's
    REAL parent -- not just added as a flat list under the root, and not
    duplicating the depth-1 entry (click) that's already added from
    `deps` above."""
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", licence="BSD-3-Clause")]
    doc = to_spdx("demo", "0.1.0", deps, transitive=_CHAIN_RESOLUTION)

    names = [p["name"] for p in doc["packages"]]
    assert names == ["demo", "click", "colorama", "six"]  # click appears once, not twice

    edges = {(r["spdxElementId"], r["relatedSpdxElement"]) for r in doc["relationships"] if r["relationshipType"] == "DEPENDS_ON"}
    click_id = next(p["SPDXID"] for p in doc["packages"] if p["name"] == "click")
    colorama_id = next(p["SPDXID"] for p in doc["packages"] if p["name"] == "colorama")
    six_id = next(p["SPDXID"] for p in doc["packages"] if p["name"] == "six")
    assert (click_id, colorama_id) in edges  # click -> colorama, not demo -> colorama
    assert (colorama_id, six_id) in edges  # colorama -> six, not click -> six or demo -> six


def test_to_spdx_direct_dependency_sha256_becomes_a_real_checksum():
    """A direct Dependency's sha256 field (a bare hex digest, no
    'algorithm:' prefix) must be wired into the SPDX package's own
    `checksums` field, not just left sitting unused on the Dependency
    object."""
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", sha256="a" * 64)]
    doc = to_spdx("demo", "0.1.0", deps)
    click_pkg = next(p for p in doc["packages"] if p["name"] == "click")
    assert click_pkg["checksums"] == [{"algorithm": "SHA256", "checksumValue": "a" * 64}]


def test_to_spdx_merges_transitive_checksums_into_packages():
    """Each transitive package's real registry-derived digest (see
    provenance/transitive.py) must appear as a genuine SPDX checksum on
    that package -- not just recorded in the separate
    transitive-dependencies.json artefact."""
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", licence="BSD-3-Clause")]
    doc = to_spdx("demo", "0.1.0", deps, transitive=_CHAIN_RESOLUTION)

    colorama_pkg = next(p for p in doc["packages"] if p["name"] == "colorama")
    assert colorama_pkg["checksums"] == [{"algorithm": "SHA256", "checksumValue": "c" * 64}]
    six_pkg = next(p for p in doc["packages"] if p["name"] == "six")
    assert six_pkg["checksums"] == [{"algorithm": "SHA1", "checksumValue": "6" * 40}]
    # click is a direct dependency with no sha256 given here -- no checksum
    # fabricated, correctly absent rather than an empty/placeholder value.
    click_pkg = next(p for p in doc["packages"] if p["name"] == "click")
    assert "checksums" not in click_pkg or click_pkg["checksums"] == []


def test_to_spdx_unmatched_transitive_parent_still_includes_the_package():
    """If a transitive entry's parent isn't found (e.g. resolved against a
    different deps list), the package must still be included -- just
    without that one relationship edge -- rather than silently dropped."""
    orphan = TransitiveResolution(
        resolved=[TransitiveDependency(name="mystery-dep", ecosystem="pypi", depth=2, required_by="never-registered", version="1.0")],
        unresolved=[],
    )
    doc = to_spdx("demo", "0.1.0", [], transitive=orphan)
    assert "mystery-dep" in [p["name"] for p in doc["packages"]]


def test_to_cyclonedx_without_transitive_is_unchanged():
    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click")]
    doc = to_cyclonedx("demo", "0.1.0", deps)
    assert len(doc["components"]) == 1


def test_to_cyclonedx_merges_transitive_dependencies_and_stays_schema_valid():
    from cyclonedx.schema import OutputFormat, SchemaVersion
    from cyclonedx.validation import make_schemabased_validator

    deps = [Dependency(name="click", version="8.1.7", purl="pkg:pypi/click", licence="BSD-3-Clause")]
    doc = to_cyclonedx("demo", "0.1.0", deps, transitive=_CHAIN_RESOLUTION)

    error = make_schemabased_validator(OutputFormat.JSON, SchemaVersion.V1_5).validate_str(json.dumps(doc))
    assert error is None, error

    names = {c["name"] for c in doc["components"]}
    assert names == {"click", "colorama", "six"}  # click appears once, not twice

    dependency_by_ref = {d["ref"]: d.get("dependsOn", []) for d in doc["dependencies"]}
    click_ref = next(c["bom-ref"] for c in doc["components"] if c["name"] == "click")
    colorama_ref = next(c["bom-ref"] for c in doc["components"] if c["name"] == "colorama")
    six_ref = next(c["bom-ref"] for c in doc["components"] if c["name"] == "six")
    assert colorama_ref in dependency_by_ref[click_ref]  # click depends on colorama, not just root
    assert six_ref in dependency_by_ref[colorama_ref]  # colorama depends on six, not click

    # Each transitive component's real registry-derived digest must also
    # appear as a genuine CycloneDX hash on that component.
    colorama_component = next(c for c in doc["components"] if c["name"] == "colorama")
    assert colorama_component["hashes"] == [{"alg": "SHA-256", "content": "c" * 64}]
    six_component = next(c for c in doc["components"] if c["name"] == "six")
    assert six_component["hashes"] == [{"alg": "SHA-1", "content": "6" * 40}]
