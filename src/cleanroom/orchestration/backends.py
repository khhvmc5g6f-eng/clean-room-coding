"""Part LXV, made real: a pluggable LLM backend interface for
`orchestration/harness.py`. "Provider-agnostic" has been a design
principle stated in this codebase's docstrings since early on -- this
module is what makes it a real interface instead of just a comment.
Adding a new provider means implementing `AgentBackend`'s one method,
never touching `harness.py`'s own orchestration logic.
"""

from __future__ import annotations

from typing import Protocol


class AgentBackend(Protocol):
    """One LLM completion call: a system prompt and a user prompt in, a
    text response out. No streaming, no tool-use loop -- `harness.py`'s
    own multi-step structure (build a prompt, call a backend, parse the
    response, merge it back through the existing deterministic
    machinery) is the actual orchestration; a backend only answers "what
    does *a* model say to this one question."""

    def complete(self, *, system: str, prompt: str) -> str: ...


class AnthropicBackend:
    """Real calls to the Anthropic Messages API via the official
    `anthropic` Python SDK -- an optional dependency (`pip install
    cleanroom[orchestrate]`), imported lazily so the base `cleanroom`
    install never requires it or an API key. Reads `ANTHROPIC_API_KEY`
    from the environment exactly as the SDK's own client does by default;
    this class never accepts, stores, or logs a raw key string itself."""

    def __init__(self, *, model: str = "claude-sonnet-5", max_tokens: int = 8192) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "The 'anthropic' package is required for AnthropicBackend -- install it with "
                "'pip install cleanroom[orchestrate]' (or 'pip install anthropic' directly), and set "
                "the ANTHROPIC_API_KEY environment variable."
            ) from e
        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, *, system: str, prompt: str) -> str:
        import anthropic

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AnthropicError as e:
            # A real API-level failure (bad/missing key, rate limit,
            # network error, etc.) -- never let it surface as a raw
            # traceback through harness.py/cli.py.
            raise RuntimeError(f"Anthropic API call failed: {e}") from e
        except TypeError as e:
            # The SDK raises a bare TypeError (not an AnthropicError
            # subclass) for its own pre-flight "could not resolve
            # authentication method" check -- confirmed by direct
            # reproduction (no ANTHROPIC_API_KEY set), not a guess.
            if "authentication method" in str(e):
                raise RuntimeError(
                    "Anthropic API call failed: no credentials found. Set the ANTHROPIC_API_KEY "
                    "environment variable (or one of the SDK's other supported auth methods)."
                ) from e
            raise
        return "".join(block.text for block in response.content if block.type == "text")


class FakeBackend:
    """A deterministic test double -- NEVER a real LLM response, used
    only to prove `harness.py`'s own orchestration logic (registration,
    prompt routing, response parsing, merging back through
    `legal_panels.merge_panel_answers`, writing build output) is correct
    independent of any real model call. Records every (system, prompt)
    pair it was asked, in order, and returns the next configured response
    from a fixed list -- raises if asked for more completions than were
    configured, rather than silently looping or fabricating a plausible-
    looking answer."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if not self._responses:
            raise RuntimeError(f"FakeBackend has no more configured responses (received {len(self.calls)} call(s)).")
        return self._responses.pop(0)
