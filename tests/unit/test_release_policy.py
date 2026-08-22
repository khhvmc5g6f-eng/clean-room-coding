from cleanroom.report import release_allowed


def _base_kwargs(**overrides):
    kwargs = dict(
        technical_gate=True, provenance_gate=True, contamination_gate=True,
        global_decision="GREEN_WITH_CONDITIONS",
        require_technical_gate=True, require_provenance_gate=True, require_contamination_gate=True,
        block_on_red_required_jurisdiction=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_all_gates_pass_allows_release():
    allowed, reasons = release_allowed(**_base_kwargs())
    assert allowed is True
    assert reasons == []


def test_red_jurisdiction_blocks_even_with_all_technical_gates_green():
    allowed, reasons = release_allowed(**_base_kwargs(global_decision="RED"))
    assert allowed is False
    assert any("RED" in r for r in reasons)


def test_failed_technical_gate_blocks():
    allowed, reasons = release_allowed(**_base_kwargs(technical_gate=False))
    assert allowed is False


def test_optional_gate_can_be_disabled():
    allowed, reasons = release_allowed(**_base_kwargs(provenance_gate=False, require_provenance_gate=False))
    assert allowed is True
