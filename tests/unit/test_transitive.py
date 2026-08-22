from cleanroom.provenance import transitive
from cleanroom.provenance.sbom import Dependency


def test_resolve_transitive_walks_dependency_graph(monkeypatch):
    """Fake registry: root -> {a, b}, a -> {c}, b -> {}, c -> {} -- confirms
    breadth-first walking, depth tracking, and dedup (nothing queried
    twice even though it's only reachable one way here)."""
    fake_pypi = {
        "root": ("1.0", ["a", "b"], "MIT", None),
        "a": ("2.0", ["c"], "Apache-2.0", None),
        "b": ("3.0", [], None, None),
        "c": ("4.0", [], "BSD-3-Clause", "sha256:" + "c" * 64),
    }
    monkeypatch.setattr(transitive, "_pypi_lookup", lambda name, version: fake_pypi.get(name))

    deps = [Dependency(name="root", version="1.0", purl="pkg:pypi/root")]
    result = transitive.resolve_transitive(deps)

    names_by_depth = {d.name: d.depth for d in result.resolved}
    assert names_by_depth == {"root": 1, "a": 2, "b": 2, "c": 3}
    assert not result.unresolved
    c_entry = next(d for d in result.resolved if d.name == "c")
    assert c_entry.required_by == "a"
    assert c_entry.licence == "BSD-3-Clause"
    assert c_entry.digest == "sha256:" + "c" * 64


def test_resolve_transitive_dedups_diamond_dependency(monkeypatch):
    """root -> {a, b}, both a and b depend on shared -- shared must only
    be resolved (and its registry queried) once."""
    call_count = {"shared": 0}
    fake_pypi = {
        "root": ("1.0", ["a", "b"], None, None),
        "a": ("1.0", ["shared"], None, None),
        "b": ("1.0", ["shared"], None, None),
    }

    def lookup(name, version):
        if name == "shared":
            call_count["shared"] += 1
            return ("9.0", [], None, None)
        return fake_pypi.get(name)

    monkeypatch.setattr(transitive, "_pypi_lookup", lookup)
    deps = [Dependency(name="root", version="1.0", purl="pkg:pypi/root")]
    result = transitive.resolve_transitive(deps)

    assert call_count["shared"] == 1
    assert sum(1 for d in result.resolved if d.name == "shared") == 1


def test_resolve_transitive_records_failed_lookup_as_unresolved_not_dropped(monkeypatch):
    monkeypatch.setattr(transitive, "_pypi_lookup", lambda name, version: None)
    deps = [Dependency(name="does-not-exist", version=None, purl="pkg:pypi/does-not-exist")]
    result = transitive.resolve_transitive(deps)

    assert result.resolved == []
    assert result.unresolved == [{"name": "does-not-exist", "ecosystem": "pypi", "reason": "registry lookup failed (network error, unknown package, or rate limit)"}]


def test_resolve_transitive_stops_at_max_depth_and_records_why(monkeypatch):
    # An unbroken chain a1 -> a2 -> a3 -> ... ; max_depth=2 should resolve
    # depth 1 and 2 but flag depth 3 as exceeding the cap rather than
    # silently truncating the queue.
    def lookup(name, version):
        n = int(name[1:])
        return (str(n), [f"a{n + 1}"], None, None)

    monkeypatch.setattr(transitive, "_pypi_lookup", lookup)
    deps = [Dependency(name="a1", version=None, purl="pkg:pypi/a1")]
    result = transitive.resolve_transitive(deps, max_depth=2)

    resolved_names = {d.name for d in result.resolved}
    assert resolved_names == {"a1", "a2"}
    assert any(u["name"] == "a3" and "max resolution depth" in u["reason"] for u in result.unresolved)


def test_npm_lookup_uses_dist_tags_latest_when_no_version_pinned(monkeypatch):
    fake_registry_response = {
        "dist-tags": {"latest": "2.0.0"},
        "versions": {
            "2.0.0": {"license": "MIT", "dependencies": {"leftpad": "^1.0.0"}},
            "1.0.0": {"license": "MIT", "dependencies": {}},
        },
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_registry_response)
    result = transitive._npm_lookup("some-package", None)
    assert result == ("2.0.0", ["leftpad"], "MIT", None)


def test_pypi_lookup_skips_extra_only_requirements(monkeypatch):
    fake_response = {
        "info": {
            "version": "1.2.3",
            "license": "MIT",
            "requires_dist": [
                "click>=8.0",
                "pytest ; extra == 'test'",
                "requests>=2.0",
            ],
        }
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_response)
    version, names, licence, digest = transitive._pypi_lookup("demo", None)
    assert version == "1.2.3"
    assert names == ["click", "requests"]
    assert licence == "MIT"
    assert digest is None


def test_pypi_lookup_extracts_real_sha256_digest_preferring_wheel(monkeypatch):
    fake_response = {
        "info": {"version": "1.2.3", "license": "MIT", "requires_dist": []},
        "urls": [
            {"packagetype": "sdist", "digests": {"sha256": "s" * 64}},
            {"packagetype": "bdist_wheel", "digests": {"sha256": "w" * 64}},
        ],
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_response)
    _, _, _, digest = transitive._pypi_lookup("demo", None)
    assert digest == "sha256:" + "w" * 64  # wheel preferred over sdist


def test_pypi_lookup_falls_back_to_sdist_digest_when_no_wheel(monkeypatch):
    fake_response = {
        "info": {"version": "1.2.3", "license": "MIT", "requires_dist": []},
        "urls": [{"packagetype": "sdist", "digests": {"sha256": "s" * 64}}],
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_response)
    _, _, _, digest = transitive._pypi_lookup("demo", None)
    assert digest == "sha256:" + "s" * 64


def test_npm_lookup_extracts_digest_from_sri_integrity_field(monkeypatch):
    import base64

    raw = b"\x01" * 64  # a fake sha512 digest's raw bytes
    integrity = "sha512-" + base64.b64encode(raw).decode("ascii")
    fake_registry_response = {
        "dist-tags": {"latest": "1.0.0"},
        "versions": {"1.0.0": {"dependencies": {}, "dist": {"integrity": integrity, "shasum": "deadbeef"}}},
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_registry_response)
    _, _, _, digest = transitive._npm_lookup("some-package", None)
    assert digest == "sha512:" + raw.hex()


def test_npm_lookup_falls_back_to_legacy_shasum_without_integrity(monkeypatch):
    fake_registry_response = {
        "dist-tags": {"latest": "1.0.0"},
        "versions": {"1.0.0": {"dependencies": {}, "dist": {"shasum": "deadbeefcafe"}}},
    }
    monkeypatch.setattr(transitive, "_http_get_json", lambda url: fake_registry_response)
    _, _, _, digest = transitive._npm_lookup("some-package", None)
    assert digest == "sha1:deadbeefcafe"


def test_npm_integrity_to_digest_returns_none_for_malformed_input():
    assert transitive._npm_integrity_to_digest(None) is None
    assert transitive._npm_integrity_to_digest("not-a-real-sri-string") is None


def test_resolve_transitive_reports_unsupported_ecosystem_honestly_not_as_a_pypi_404(monkeypatch):
    """A Cargo/Composer direct dependency has no registry lookup
    implemented in this module -- it must be recorded unresolved with an
    honest "not yet implemented for this ecosystem" reason, never silently
    routed through the PyPI lookup (which would misreport a real gap as an
    ordinary "package not found")."""
    def unexpected_pypi_lookup(name, version):
        raise AssertionError("must not attempt a PyPI lookup for a non-PyPI ecosystem")

    monkeypatch.setattr(transitive, "_pypi_lookup", unexpected_pypi_lookup)
    deps = [Dependency(name="serde", version="1.0", purl="pkg:cargo/serde")]
    result = transitive.resolve_transitive(deps)

    assert result.resolved == []
    assert result.unresolved == [{"name": "serde", "ecosystem": "cargo", "reason": "transitive resolution not yet implemented for the cargo ecosystem"}]
