from pathlib import Path

from cleanroom.evidence import Actor, EvidenceLedger


def test_ledger_chains_hashes(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "evidence")
    e1 = ledger.append(actor=Actor(type="human", id="u1"), action="a")
    e2 = ledger.append(actor=Actor(type="tool", id="t1"), action="b")
    assert e2["previous_hash"] == e1["event_hash"]
    assert e1["sequence"] == 0
    assert e2["sequence"] == 1
    assert ledger.verify_chain() == []


def test_ledger_detects_tampering(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "evidence")
    ledger.append(actor=Actor(type="human", id="u1"), action="a")
    ledger.append(actor=Actor(type="tool", id="t1"), action="b")

    # Hand-edit the first event without recomputing its hash.
    lines = ledger.ledger_path.read_text(encoding="utf-8").splitlines()
    import json

    first = json.loads(lines[0])
    first["detail"] = "tampered"
    lines[0] = json.dumps(first)
    ledger.ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = ledger.verify_chain()
    assert problems  # tampering must be detected


def test_ledger_survives_truncated_trailing_line(tmp_path: Path):
    """Simulates a process killed mid-write: verify_chain and append must
    degrade gracefully (report a problem / treat as incomplete write),
    never raise json.JSONDecodeError."""
    ledger = EvidenceLedger(tmp_path / "evidence")
    ledger.append(actor=Actor(type="human", id="u1"), action="a")
    with open(ledger.ledger_path, "a", encoding="utf-8") as f:
        f.write('{"event_id": "half-written", "sequence": 1, "actor": {"typ')  # no trailing newline, truncated

    problems = ledger.verify_chain()  # must not raise
    assert any("incomplete" in p for p in problems)

    # A fresh ledger instance (simulating the next CLI invocation) must
    # still be able to append after an interrupted write.
    fresh = EvidenceLedger(tmp_path / "evidence")
    event = fresh.append(actor=Actor(type="tool", id="t1"), action="b")
    assert event["sequence"] == 1  # the truncated line didn't count as a real event


def test_read_all_never_raises_on_corrupt_middle_line(tmp_path: Path):
    ledger = EvidenceLedger(tmp_path / "evidence")
    ledger.append(actor=Actor(type="human", id="u1"), action="a")
    ledger.append(actor=Actor(type="tool", id="t1"), action="b")
    lines = ledger.ledger_path.read_text(encoding="utf-8").splitlines()
    lines[0] = "{not valid json"
    ledger.ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    events = ledger.read_all()  # must not raise
    assert len(events) == 1  # only the still-parseable second line survives
