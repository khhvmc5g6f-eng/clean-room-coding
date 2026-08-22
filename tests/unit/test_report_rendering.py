from pathlib import Path

from cleanroom.report import build_certificate, render_final_report, render_html_report
from cleanroom.report_pdf import render_pdf_report


def _sample_certificate() -> dict:
    return build_certificate(
        project="Demo", version="0.1.0", reference="https://example.com/upstream",
        clean_room_level="CR2", tests={"pass": 1, "fail": 0, "not_tested": 0},
        requirement_traceability_percent=50.0, provenance_status="partial",
        similarity_result="material_findings_open",
        jurisdictions=[
            {"jurisdiction": "gb", "decision_state": "AMBER", "required_market": True},
            {"jurisdiction": "us", "decision_state": "GREEN_WITH_CONDITIONS", "required_market": False},
        ],
        global_decision="AMBER",
        outstanding_issues=["Something is unresolved"],
        evidence_bundle_location="/tmp/evidence",
        remediation={"open_blocking": 1, "open_review_required": 2, "resolved_by_rescan": 3, "resolved_by_override": 0},
        project_summary={
            "reference_summary": "(not recorded in .cleanroom.yml reference.repositories)",  # deliberately long, no unusual spacing
            "intended_output_licence": "(not recorded)",
            "distribution_model": [],
            "target_markets": ["gb", "us"],
        },
        phases_completed=["Init", "Intake", "Licence discovery"],
    )


def test_html_report_contains_colour_chips_and_disclaimer():
    html = render_html_report(_sample_certificate())
    assert "AMBER" in html
    assert "chip" in html
    assert "Demo" in html
    assert "This certificate records process completion" in html
    assert "AI-generated heuristics" in html


def test_html_report_escapes_untrusted_text():
    cert = _sample_certificate()
    cert["outstanding_issues"] = ["<script>alert(1)</script>"]
    html = render_html_report(cert)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_markdown_report_has_all_sections():
    text = render_final_report(_sample_certificate())
    for heading in ["What it started with", "What it did", "Remediation", "Jurisdictions", "Global decision", "Outstanding issues"]:
        assert heading in text


def test_pdf_report_generates_valid_file(tmp_path: Path):
    """Regression test for the fpdf2 x-position drift bug: multi_cell does
    not reset x to the left margin by default, so without an explicit
    set_x() before each call, the second-or-later text block raises
    FPDFException('Not enough horizontal space...'). This exact
    certificate (with the same long, space-containing-but-narrow-wrapping
    strings that triggered it) must render without raising."""
    path = render_pdf_report(_sample_certificate(), tmp_path / "report.pdf")
    assert path.is_file()
    data = path.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 500


def test_pdf_report_handles_unicode_punctuation_without_crashing(tmp_path: Path):
    """Regression test: fpdf2's core fonts (Helvetica/Courier) only support
    Latin-1. An em dash, curly quotes, or an ellipsis in ordinary
    human-entered project metadata or LLM-authored finding text previously
    crashed `cleanroom report --pdf` outright with
    FPDFUnicodeEncodingException. Must render without raising."""
    cert = _sample_certificate()
    cert["project"] = "Demo — with an em dash and ‘curly quotes’"
    cert["outstanding_issues"] = ["contains an ellipsis… and a bullet •"]
    path = render_pdf_report(cert, tmp_path / "unicode-report.pdf")
    assert path.is_file()
    assert path.read_bytes()[:5] == b"%PDF-"
