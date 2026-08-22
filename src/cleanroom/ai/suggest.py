"""Optional AI-model suggestion (`cleanroom ai-suggest`).

When ripping/reimplementing a licensed product, the design brief asks that
the user be explicitly offered the choice of adding AI/ML capability, and
that suggestions distinguish embeddable/standalone models (no server
needed -- ONNX/GGUF/TFLite/CoreML, runnable in-process or on-device) from
models that require a dedicated inference server (typically large
transformer checkpoints with no embeddable-format artefact).

This module only queries the public Hugging Face Hub API (via the
`huggingface_hub` package, an optional `ai` extra -- `pip install
'cleanroom[ai]'`) and returns structured facts. It never recommends a
specific model as "the" answer, and it never fabricates a licence or
deployment-shape conclusion when the Hub's own metadata doesn't say --
`licence` and `deployment_shape` are `None`/`"unknown"` rather than guessed,
matching every other engine in this project (Part LXVIII: no invented
completeness).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

EMBEDDABLE_LIBRARIES = {"onnx", "ggml", "gguf", "tflite", "coreml", "llama.cpp", "candle", "mlx"}
EMBEDDABLE_FILE_SUFFIXES = (".onnx", ".gguf", ".ggml", ".tflite", ".mlmodel", ".ort", ".mlpackage")
TYPICALLY_HEAVY_PIPELINE_TAGS = {
    "text-generation", "image-to-text", "text-to-image", "text-to-video",
    "text-to-speech", "automatic-speech-recognition", "video-generation",
    "any-to-any", "image-to-video",
}


@dataclass
class ModelSuggestion:
    model_id: str
    pipeline_tag: str | None
    library_name: str | None
    downloads: int | None
    likes: int | None
    licence: str | None
    deployment_shape: str  # "embeddable" | "server_required" | "unknown"
    deployment_shape_reason: str
    url: str
    licence_policy_status: str | None = None  # filled in by evaluate_against_policy()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_licence(tags: list[str]) -> str | None:
    for tag in tags or []:
        if tag.startswith("license:"):
            return tag.split(":", 1)[1]
    return None


def _classify_deployment_shape(library_name: str | None, sibling_filenames: list[str], pipeline_tag: str | None) -> tuple[str, str]:
    if library_name and library_name.lower() in EMBEDDABLE_LIBRARIES:
        return "embeddable", f"library_name '{library_name}' is a known embeddable-inference format"
    if any(name.lower().endswith(EMBEDDABLE_FILE_SUFFIXES) for name in sibling_filenames):
        matched = next(n for n in sibling_filenames if n.lower().endswith(EMBEDDABLE_FILE_SUFFIXES))
        return "embeddable", f"repository includes an embeddable-format file ({matched})"
    if pipeline_tag in TYPICALLY_HEAVY_PIPELINE_TAGS:
        return "server_required", f"pipeline_tag '{pipeline_tag}' is typically a large-model task with no embeddable artefact found"
    return "unknown", "no embeddable-format file found and pipeline_tag isn't in the known-heavy list -- not enough evidence to classify"


def search_models(capability: str, *, limit: int = 10) -> list[ModelSuggestion]:
    """Queries the public Hugging Face Hub for models matching a free-text
    capability description (e.g. "text classification", "speech to text").
    Raises ImportError if the 'ai' extra isn't installed, and re-raises any
    network/API error from huggingface_hub rather than silently returning
    an empty/misleading result."""
    try:
        from huggingface_hub import HfApi
    except ImportError as e:
        raise ImportError("cleanroom ai-suggest requires the 'ai' extra: pip install 'cleanroom[ai]'") from e

    api = HfApi()
    models = api.list_models(
        search=capability,
        sort="downloads",
        limit=limit,
        expand=["pipeline_tag", "library_name", "tags", "downloads", "likes", "siblings"],
    )

    suggestions = []
    for m in models:
        sibling_names = [s.rfilename for s in (m.siblings or [])]
        shape, reason = _classify_deployment_shape(m.library_name, sibling_names, m.pipeline_tag)
        suggestions.append(
            ModelSuggestion(
                model_id=m.id,
                pipeline_tag=m.pipeline_tag,
                library_name=m.library_name,
                downloads=getattr(m, "downloads", None),
                likes=getattr(m, "likes", None),
                licence=_extract_licence(m.tags or []),
                deployment_shape=shape,
                deployment_shape_reason=reason,
                url=f"https://huggingface.co/{m.id}",
            )
        )
    return suggestions


def evaluate_against_policy(suggestions: list[ModelSuggestion], *, allowed: list[str], denied: list[str]) -> list[ModelSuggestion]:
    """Cross-checks each suggestion's Hub licence tag against the project's
    OWN dependency_policy (the same allow/deny lists `cleanroom licence`
    uses) -- reuses the existing licence policy engine rather than
    inventing a parallel one."""
    from cleanroom.licence.policy import evaluate

    for s in suggestions:
        result = evaluate(_normalise_hub_licence(s.licence), allowed=allowed, denied=denied)
        s.licence_policy_status = result["status"]
    return suggestions


_HUB_LICENCE_TO_SPDX = {
    "mit": "MIT", "apache-2.0": "Apache-2.0", "bsd-3-clause": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause", "isc": "ISC", "gpl-3.0": "GPL-3.0-only",
    "gpl-2.0": "GPL-2.0-only", "lgpl-3.0": "LGPL-3.0-only", "lgpl-2.1": "LGPL-2.1-only",
    "agpl-3.0": "AGPL-3.0-only", "mpl-2.0": "MPL-2.0", "cc0-1.0": "CC0-1.0",
    "unlicense": "Unlicense", "cc-by-4.0": "CC-BY-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0", "wtfpl": "WTFPL", "ofl-1.1": "OFL-1.1",
    # Deliberately NOT mapped: "openrail", "creativeml-openrail-m", "llama2",
    # "llama3", "gemma", "bigscience-openrail-m", "bigscience-bloom-rail-1.0"
    # and similar model-specific "Responsible AI License" (RAIL) tags. These
    # carry real use-restrictions (e.g. field-of-use limits) with no SPDX
    # equivalent -- forcing one onto the closest-sounding permissive/
    # copyleft SPDX id would fabricate a conclusion this project's own
    # policy engine could then wrongly report as "allowed". Correctly
    # falling through to `None` -> policy status "unknown" here is the
    # honest behaviour, not a gap to fill.
}


def _normalise_hub_licence(hub_licence: str | None) -> str | None:
    if hub_licence is None:
        return None
    return _HUB_LICENCE_TO_SPDX.get(hub_licence.lower())
