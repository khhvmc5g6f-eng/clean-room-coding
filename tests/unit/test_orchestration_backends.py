from unittest.mock import MagicMock, patch

import pytest

from cleanroom.orchestration.backends import FakeBackend


def test_fake_backend_returns_configured_responses_in_order():
    backend = FakeBackend(["first", "second"])
    assert backend.complete(system="s1", prompt="p1") == "first"
    assert backend.complete(system="s2", prompt="p2") == "second"
    assert backend.calls == [("s1", "p1"), ("s2", "p2")]


def test_fake_backend_raises_rather_than_looping_when_exhausted():
    backend = FakeBackend(["only-one"])
    backend.complete(system="s", prompt="p")
    with pytest.raises(RuntimeError, match="no more configured responses"):
        backend.complete(system="s", prompt="p2")


def test_anthropic_backend_raises_a_clear_error_without_the_optional_dependency(monkeypatch):
    """Real behaviour when 'anthropic' isn't installed -- never silently
    falls back to a fake/simulated response."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no module named anthropic")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from cleanroom.orchestration.backends import AnthropicBackend

    with pytest.raises(RuntimeError, match="cleanroom\\[orchestrate\\]"):
        AnthropicBackend()


def test_anthropic_backend_raises_a_clean_error_instead_of_a_raw_traceback_with_no_credentials():
    """Reproduced directly against the real installed SDK with
    ANTHROPIC_API_KEY unset: the SDK's client construction succeeds, but
    `messages.create()` raises a bare TypeError (not an AnthropicError
    subclass) from its own pre-flight auth check deep inside header
    building -- confirmed by direct reproduction, not assumed. complete()
    must convert this into a clean RuntimeError, never let it propagate
    as a raw traceback through harness.py/cli.py."""
    from cleanroom.orchestration.backends import AnthropicBackend

    backend = AnthropicBackend()  # construction succeeds even with no key
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        backend.complete(system="s", prompt="p")


def test_anthropic_backend_wraps_a_real_api_error_cleanly():
    import anthropic

    from cleanroom.orchestration.backends import AnthropicBackend

    mock_client = MagicMock()
    mock_response = MagicMock(status_code=401, headers={})
    mock_client.messages.create.side_effect = anthropic.AuthenticationError(
        "invalid x-api-key", response=mock_response, body=None,
    )
    with patch("anthropic.Anthropic", return_value=mock_client):
        backend = AnthropicBackend()
        with pytest.raises(RuntimeError, match="Anthropic API call failed"):
            backend.complete(system="s", prompt="p")


def test_anthropic_backend_parses_the_real_sdk_response_shape():
    """Verified directly against the installed `anthropic` 1.0.0 SDK's
    real Message/TextBlock shape (content is a list of blocks, each with
    a `.type` and, for text blocks, a `.text`) -- not a guess. Mocks only
    the network call itself, exercising this class's own real parsing
    logic (joining every text block, in order, ignoring anything else)."""
    from cleanroom.orchestration.backends import AnthropicBackend

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "the model's real answer"
    non_text_block = MagicMock()
    non_text_block.type = "thinking"  # must be skipped, not concatenated in
    mock_message = MagicMock()
    mock_message.content = [non_text_block, text_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("anthropic.Anthropic", return_value=mock_client):
        backend = AnthropicBackend(model="claude-sonnet-5")
        result = backend.complete(system="you are a reviewer", prompt="review this")

    assert result == "the model's real answer"
    mock_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5", max_tokens=8192, system="you are a reviewer",
        messages=[{"role": "user", "content": "review this"}],
    )
