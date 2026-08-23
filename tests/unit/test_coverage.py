from pathlib import Path

from cleanroom.coverage import check_coverage, extract_usage_facts


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# The motivating real-world bug (see coverage.py's module docstring): a
# Meshtastic-style clean-room migration deliberately scoped its
# reimplementation down to "only what the app's screens actually use",
# which silently dropped the enum-name -> numeric-id conversion for the
# LoRa region field. `setConfig` is called with a raw `cfg.region` in the
# Zone I implementation instead of the legacy code's `REGION_MAP[cfg.region]`
# lookup -- garbage written to real hardware, caught by nothing until a
# manual audit read the code by hand.
LEGACY_MESHTASTIC_USAGE = """
// Legacy app screen: reads the LoRa settings form and pushes them to the device.
const REGION_MAP = { EU_868: 1, US_915: 2 };
const MODEM_PRESET_MAP = { LONG_FAST: 0, SHORT_FAST: 1 };

function applyLoraSettings(cfg) {
  device.setConfig({
    lora: {
      region: REGION_MAP[cfg.region],
      modemPreset: MODEM_PRESET_MAP[cfg.modemPreset],
      txPower: cfg.txPower,
    },
  });
}
"""

ZONE_I_MISSING_CONVERSION = """
// Zone I reimplementation, scoped down to "only what the screens use".
function applyLoraSettings(cfg) {
  device.setConfig({
    lora: {
      region: cfg.region,
      txPower: cfg.txPower,
    },
  });
}
"""

ZONE_I_MATCHING = """
const REGION_MAP = { EU_868: 1, US_915: 2 };
const MODEM_PRESET_MAP = { LONG_FAST: 0, SHORT_FAST: 1 };

function applyLoraSettings(cfg) {
  device.setConfig({
    lora: {
      region: REGION_MAP[cfg.region],
      modemPreset: MODEM_PRESET_MAP[cfg.modemPreset],
      txPower: cfg.txPower,
    },
  });
}
"""


def test_extract_usage_facts_finds_named_fields_and_ignores_comments(tmp_path: Path):
    _write(tmp_path / "legacy.js", LEGACY_MESHTASTIC_USAGE)
    facts = extract_usage_facts(tmp_path)
    names = {f.name for f in facts}
    assert {"region", "modemPreset", "txPower", "EU_868", "US_915", "LONG_FAST", "SHORT_FAST"} <= names
    # The comment line ("Legacy app screen: reads...") must not be
    # mistaken for an `identifier: value` usage fact just because it
    # contains a colon.
    assert "screen" not in names


def test_missing_field_is_flagged_as_a_regression(tmp_path: Path):
    """The real motivating bug, reproduced in miniature: a field the legacy
    code referenced (modemPreset) is completely absent from Zone I."""
    legacy = tmp_path / "legacy"
    zone_i = tmp_path / "zone_i"
    _write(legacy / "settings.js", LEGACY_MESHTASTIC_USAGE)
    _write(zone_i / "settings.js", ZONE_I_MISSING_CONVERSION)

    result = check_coverage(legacy, zone_i)
    assert result["overall_status"] == "checked"

    by_name = {f["name"]: f for f in result["findings"]}
    assert by_name["modemPreset"]["status"] == "missing"
    assert by_name["modemPreset"]["confidence"] == "CONFIRMED"
    assert by_name["modemPreset"]["requires_review"] is True
    # The enum values behind the dropped field are gone too.
    assert by_name["LONG_FAST"]["status"] == "missing"
    assert by_name["SHORT_FAST"]["status"] == "missing"


def test_dropped_conversion_is_flagged_as_a_plausible_divergence(tmp_path: Path):
    """The literal motivating bug shape: 'region' is still referenced in
    both legacy and Zone I, but Zone I dropped the REGION_MAP lookup the
    legacy code always applied -- this must surface as a PLAUSIBLE,
    human-review finding, never a silent pass and never an auto-fail."""
    legacy = tmp_path / "legacy"
    zone_i = tmp_path / "zone_i"
    _write(legacy / "settings.js", LEGACY_MESHTASTIC_USAGE)
    _write(zone_i / "settings.js", ZONE_I_MISSING_CONVERSION)

    result = check_coverage(legacy, zone_i)
    by_name = {f["name"]: f for f in result["findings"]}

    region_finding = by_name["region"]
    assert region_finding["status"] == "divergent"
    assert region_finding["confidence"] == "PLAUSIBLE"
    assert region_finding["requires_review"] is True
    assert "REGION_MAP" in region_finding["legacy_locations"][0]["value_expr"]
    assert region_finding["zone_i_locations"][0]["value_expr"] == "cfg.region"

    # txPower has no conversion in either side -- must not be flagged.
    assert by_name["txPower"]["status"] == "present"
    assert by_name["txPower"]["requires_review"] is False


def test_matching_implementation_reports_no_regressions_or_divergences(tmp_path: Path):
    """No false positives: when Zone I keeps every field AND every
    conversion the legacy code applied, nothing should require review."""
    legacy = tmp_path / "legacy"
    zone_i = tmp_path / "zone_i"
    _write(legacy / "settings.js", LEGACY_MESHTASTIC_USAGE)
    _write(zone_i / "settings.js", ZONE_I_MATCHING)

    result = check_coverage(legacy, zone_i)
    assert result["overall_status"] == "checked"
    statuses = {f["name"]: f["status"] for f in result["findings"]}
    assert statuses["region"] == "present"
    assert statuses["modemPreset"] == "present"
    assert statuses["txPower"] == "present"
    assert not any(f["requires_review"] for f in result["findings"])


def test_empty_legacy_usage_is_insufficient_evidence_not_a_clean_pass(tmp_path: Path):
    """An extractor that finds nothing to check must say so explicitly --
    never silently report zero findings as if that meant 'verified clean'
    (AGENTS.md item c)."""
    legacy = tmp_path / "legacy"
    zone_i = tmp_path / "zone_i"
    _write(legacy / "notes.md", "Some free-form notes, no code here.\n")
    _write(zone_i / "settings.js", ZONE_I_MATCHING)

    result = check_coverage(legacy, zone_i)
    assert result["overall_status"] == "insufficient_evidence"
    assert result["findings"] == []


def test_every_finding_carries_its_limitations_and_method_disclosure(tmp_path: Path):
    """The tool must never present this as a semantic guarantee -- every
    result carries the bounded 'method' and 'limitations' text regardless
    of what it found."""
    legacy = tmp_path / "legacy"
    zone_i = tmp_path / "zone_i"
    _write(legacy / "settings.js", LEGACY_MESHTASTIC_USAGE)
    _write(zone_i / "settings.js", ZONE_I_MATCHING)

    result = check_coverage(legacy, zone_i)
    assert result["limitations"]
    assert "AST" in result["method"] or "semantic" in result["method"]
