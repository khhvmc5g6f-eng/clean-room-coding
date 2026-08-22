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
