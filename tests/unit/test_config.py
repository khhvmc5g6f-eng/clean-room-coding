from pathlib import Path

import pytest
import yaml

from cleanroom.config import ConfigurationError, default_config, load_config


def test_default_config_validates(tmp_path: Path):
    data = default_config("Demo", "demo")
    path = tmp_path / ".cleanroom.yml"
    with open(path, "w") as f:
        yaml.safe_dump(data, f)
    config = load_config(path)
    assert config.project_id == "demo"


def test_malformed_config_rejected(tmp_path: Path):
    path = tmp_path / ".cleanroom.yml"
    with open(path, "w") as f:
        yaml.safe_dump({"schema_version": "1.0.0", "project": {"name": "x"}}, f)  # missing required fields
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_missing_config_file_rejected(tmp_path: Path):
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "nonexistent.yml")


def test_zone_path_resolution(tmp_path: Path):
    data = default_config("Demo", "demo")
    path = tmp_path / ".cleanroom.yml"
    with open(path, "w") as f:
        yaml.safe_dump(data, f)
    config = load_config(path)
    assert config.zone_path("R") == tmp_path / "zone-r"


def test_explicit_config_path_overrides_discovery(tmp_path: Path):
    from cleanroom.config import find_config

    # A .cleanroom.yml that discovery WOULD find if not overridden.
    (tmp_path / ".cleanroom.yml").write_text("schema_version: '1.0.0'", encoding="utf-8")
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    explicit = other_dir / "custom.yml"
    explicit.write_text("schema_version: '1.0.0'", encoding="utf-8")

    found = find_config(tmp_path, explicit_path=explicit)
    assert found == explicit


def test_explicit_config_path_must_exist(tmp_path: Path):
    from cleanroom.config import find_config

    with pytest.raises(ConfigurationError):
        find_config(tmp_path, explicit_path=tmp_path / "nonexistent.yml")
