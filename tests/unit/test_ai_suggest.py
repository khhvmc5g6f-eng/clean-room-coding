from types import SimpleNamespace
from unittest.mock import patch

from cleanroom.ai.suggest import (
    _classify_deployment_shape,
    _extract_licence,
    _normalise_hub_licence,
    evaluate_against_policy,
    search_models,
)


def test_extract_licence_from_tags():
    assert _extract_licence(["transformers", "license:mit", "pytorch"]) == "mit"
    assert _extract_licence(["transformers"]) is None


def test_classify_embeddable_by_library_name():
    shape, reason = _classify_deployment_shape("onnx", [], "text-classification")
    assert shape == "embeddable"


def test_classify_embeddable_by_file_extension():
    shape, reason = _classify_deployment_shape("transformers", ["model.gguf", "config.json"], "text-generation")
    assert shape == "embeddable"
    assert "gguf" in reason


def test_classify_server_required_for_heavy_pipeline_with_no_embeddable_file():
    shape, reason = _classify_deployment_shape("transformers", ["pytorch_model.bin", "config.json"], "text-generation")
    assert shape == "server_required"


def test_classify_unknown_when_evidence_insufficient():
    shape, reason = _classify_deployment_shape("transformers", ["pytorch_model.bin"], "text-classification")
    assert shape == "unknown"
    assert "not enough evidence" in reason


def test_normalise_hub_licence_maps_known_ids():
    assert _normalise_hub_licence("mit") == "MIT"
    assert _normalise_hub_licence("apache-2.0") == "Apache-2.0"
    assert _normalise_hub_licence("cc-by-nc-4.0") is None  # unmapped -- must not guess
    assert _normalise_hub_licence(None) is None


def test_search_models_maps_hub_response(monkeypatch):
    fake_model = SimpleNamespace(
        id="org/some-model",
        pipeline_tag="text-classification",
        library_name="transformers",
        downloads=1000,
        likes=42,
        tags=["transformers", "license:mit"],
        siblings=[SimpleNamespace(rfilename="model.safetensors"), SimpleNamespace(rfilename="config.json")],
    )

    class FakeApi:
        def list_models(self, **kwargs):
            return [fake_model]

    with patch("huggingface_hub.HfApi", return_value=FakeApi()):
        suggestions = search_models("classification", limit=1)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.model_id == "org/some-model"
    assert s.licence == "mit"
    assert s.url == "https://huggingface.co/org/some-model"
    assert s.deployment_shape == "unknown"  # no embeddable file, pipeline_tag not in heavy list


def test_evaluate_against_policy_never_fabricates_status_for_unmapped_licence():
    fake_model = SimpleNamespace(
        id="org/model", pipeline_tag="text-classification", library_name="transformers",
        downloads=1, likes=1, tags=["license:cc-by-nc-4.0"], siblings=[],
    )

    class FakeApi:
        def list_models(self, **kwargs):
            return [fake_model]

    with patch("huggingface_hub.HfApi", return_value=FakeApi()):
        suggestions = search_models("x", limit=1)

    evaluate_against_policy(suggestions, allowed=["MIT"], denied=[])
    assert suggestions[0].licence_policy_status == "unknown"  # cc-by-nc-4.0 has no SPDX mapping here
