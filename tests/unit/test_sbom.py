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
