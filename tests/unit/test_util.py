from cleanroom.util import canonical_json, sha256_bytes, sha256_json


def test_canonical_json_is_key_order_independent():
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_sha256_json_deterministic():
    obj = {"x": [1, 2, 3], "y": "z"}
    assert sha256_json(obj) == sha256_json(dict(reversed(list(obj.items()))))


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
