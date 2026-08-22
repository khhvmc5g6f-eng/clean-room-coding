import os
from pathlib import Path

from cleanroom.util import canonical_json, hash_tree, is_safe_regular_file, sha256_bytes, sha256_json


def test_canonical_json_is_key_order_independent():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_sha256_json_deterministic():
    obj = {"x": [1, 2, 3], "y": "z"}
    assert sha256_json(obj) == sha256_json(dict(reversed(list(obj.items()))))


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_symlink_escaping_root_is_unsafe(tmp_path: Path):
    root = tmp_path / "zone-h"
    root.mkdir()
    outside = tmp_path / "zone-r"
    outside.mkdir()
    (outside / "secret.py").write_text("reference source", encoding="utf-8")
    escape = root / "notes.py"
    escape.symlink_to(outside / "secret.py")

    safe, reason = is_safe_regular_file(escape, root)
    assert safe is False
    assert "outside" in reason


def test_symlink_within_root_is_safe(tmp_path: Path):
    root = tmp_path / "zone-h"
    root.mkdir()
    (root / "real.py").write_text("spec", encoding="utf-8")
    link = root / "alias.py"
    link.symlink_to(root / "real.py")
    safe, _ = is_safe_regular_file(link, root)
    assert safe is True


def test_non_regular_file_is_unsafe(tmp_path: Path):
    root = tmp_path / "zone-r"
    root.mkdir()
    fifo_path = root / "LICENSE"
    os.mkfifo(fifo_path)
    safe, reason = is_safe_regular_file(fifo_path, root)
    assert safe is False
    assert "not a regular file" in reason


def test_hash_tree_skips_and_reports_unsafe_symlink(tmp_path: Path):
    root = tmp_path / "zone-h"
    root.mkdir()
    outside = tmp_path / "zone-r"
    outside.mkdir()
    (outside / "secret.py").write_text("reference source", encoding="utf-8")
    (root / "spec.md").write_text("GIVEN/WHEN/THEN", encoding="utf-8")
    (root / "leak.py").symlink_to(outside / "secret.py")

    result, skipped = hash_tree(root)
    assert "spec.md" in result
    assert "leak.py" not in result
    assert len(skipped) == 1
    assert "leak.py" in skipped[0]
