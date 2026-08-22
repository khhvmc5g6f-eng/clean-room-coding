import json
from pathlib import Path

from cleanroom.provenance.sbom import Dependency, discover_dependencies, to_cyclonedx, to_spdx


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
