"""PDF rendering of the final report -- `cleanroom report --pdf`.

Uses fpdf2 (pure-Python, no system Cairo/Pango dependency, unlike
weasyprint) so `pip install cleanroom[pdf]` stays lightweight and doesn't
risk a fragile CI install. Colour is used the same way as the HTML report:
supplementary to the printed decision-state text, never the only signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from fpdf import FPDF
    from fpdf.fonts import FontFace
except ImportError as e:  # pragma: no cover - exercised only when [pdf] extra isn't installed
    raise ImportError(
        "PDF report generation requires the 'pdf' extra: pip install 'cleanroom[pdf]'"
    ) from e

_DECISION_RGB = {
    "RED": (192, 57, 43),
    "AMBER": (184, 134, 11),
    "UNKNOWN": (127, 140, 141),
    "GREEN_WITH_CONDITIONS": (47, 133, 90),
    "GREEN": (30, 125, 50),
}

# fpdf2's core fonts (Helvetica, Courier) only support Latin-1. Any of the
# text rendered here can be ordinary human-entered project metadata or
# LLM-authored legal/similarity finding text -- neither is guaranteed
# ASCII (an em dash or curly quote from either source previously crashed
# `cleanroom report --pdf` outright with FPDFUnicodeEncodingException,
# confirmed via a regression test with a real em dash in a project name).
# Common punctuation is downgraded to a readable ASCII equivalent first;
# anything else outside Latin-1 (e.g. non-Latin scripts) falls back to
# best-effort transliteration so the report renders instead of crashing.
_UNICODE_DOWNGRADES = {
    "—": "--", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "•": "-",
    " ": " ",
}


def _safe_text(value: Any) -> str:
    text = str(value)
    for char, replacement in _UNICODE_DOWNGRADES.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", "replace").decode("latin-1")


class _ReportPDF(FPDF):
    def cell(self, w=None, h=None, text: str = "", *args: Any, **kwargs: Any):
        return super().cell(w, h, _safe_text(text), *args, **kwargs)

    def multi_cell(self, w: float, h: float | None = None, text: str = "", *args: Any, **kwargs: Any):
        return super().multi_cell(w, h, _safe_text(text), *args, **kwargs)

    def header(self) -> None:
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "Clean Room Coding -- Final Report", ln=True)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(90, 90, 90)
        self.cell(0, 6, self._subtitle, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _section_title(pdf: _ReportPDF, title: str) -> None:
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, title, ln=True)
    pdf.set_font("Helvetica", "", 10)


def _chip(pdf: _ReportPDF, label: str) -> None:
    pdf.set_x(pdf.l_margin)
    r, g, b = _DECISION_RGB.get(label, (127, 140, 141))
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 10)
    width = pdf.get_string_width(label) + 6
    pdf.cell(width, 7, label, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    # fpdf2's table() API falls back to whatever fill colour is currently
    # set on the document for any cell whose own style doesn't specify
    # one -- confirmed by direct reproduction: without this reset, the
    # jurisdiction table rendered further down the page inherited this
    # chip's colour across every cell in every row, not just the styled
    # Decision cell.
    pdf.set_fill_color(255, 255, 255)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(9)


def _bullet(pdf: _ReportPDF, text: str) -> None:
    # fpdf2's multi_cell does not reset x back to the left margin by
    # default -- without this, x drifts toward the page's right edge after
    # each call until a subsequent call has zero width left and raises
    # FPDFException("Not enough horizontal space..."). Reproduced and
    # confirmed empirically before this fix.
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, f"- {text}")


def render_pdf_report(certificate: dict[str, Any], path: Path) -> Path:
    pdf = _ReportPDF()
    pdf._subtitle = (
        f"{certificate['project']} v{certificate['version']} -- clean-room level "
        f"{certificate['clean_room_level']} -- generated {certificate['generated_utc']}"
    )
    pdf.add_page()

    _section_title(pdf, "Global decision")
    _chip(pdf, certificate["global_decision"])
    pdf.ln(2)

    summary = certificate.get("project_summary") or {}
    _section_title(pdf, "What it started with")
    _bullet(pdf, f"Reference: {summary.get('reference_summary', '(not recorded)')}")
    _bullet(pdf, f"Intended output licence: {summary.get('intended_output_licence', '(not recorded)')}")
    _bullet(pdf, f"Distribution model: {', '.join(summary.get('distribution_model', [])) or '(not recorded)'}")
    _bullet(pdf, f"Target markets: {', '.join(summary.get('target_markets', [])) or '(not recorded)'}")
    pdf.ln(2)

    _section_title(pdf, "What it did")
    phases = certificate.get("phases_completed") or []
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 6, ", ".join(phases) if phases else "(none recorded)")
    pdf.ln(2)

    _section_title(pdf, "Functional coverage & testing")
    _bullet(pdf, f"Requirement traceability: {certificate['requirement_traceability_percent']}%")
    _bullet(pdf, f"Tests: {certificate['tests']}")
    _bullet(pdf, f"Provenance status: {certificate['provenance_status']}")
    _bullet(pdf, f"Similarity result: {certificate['similarity_result']}")
    pdf.ln(2)

    remediation = certificate.get("remediation") or {}
    _section_title(pdf, "Remediation (findings sent back to be recoded)")
    _bullet(pdf, f"Open, blocking release: {remediation.get('open_blocking', 0)}")
    _bullet(pdf, f"Open, review required: {remediation.get('open_review_required', 0)}")
    _bullet(pdf, f"Resolved by re-scan (actually fixed): {remediation.get('resolved_by_rescan', 0)}")
    _bullet(pdf, f"Resolved by human override (risk accepted): {remediation.get('resolved_by_override', 0)}")
    pdf.ln(2)

    _section_title(pdf, "Jurisdictions")
    pdf.set_font("Helvetica", "", 9)
    # fpdf2's built-in table API (not manual per-cell cell() calls) so a
    # page break mid-table repeats the header row automatically instead of
    # silently splitting a row across pages with no header on the new page.
    with pdf.table(
        col_widths=(60, 60, 40),
        text_align=("LEFT", "CENTER", "CENTER"),
        headings_style=FontFace(emphasis="BOLD"),
    ) as table:
        header_row = table.row()
        header_row.cell("Jurisdiction")
        header_row.cell("Decision")
        header_row.cell("Required market")
        for j in certificate["jurisdictions"]:
            row = table.row()
            row.cell(_safe_text(str(j["jurisdiction"])))
            r, g, b = _DECISION_RGB.get(j["decision_state"], (127, 140, 141))
            row.cell(_safe_text(j["decision_state"]), style=FontFace(color=(255, 255, 255), fill_color=(r, g, b)))
            row.cell("Yes" if j.get("required_market") else "No")
    pdf.ln(4)

    _section_title(pdf, "Outstanding issues")
    issues = certificate.get("outstanding_issues") or []
    if issues:
        for issue in issues:
            _bullet(pdf, issue)
    else:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, "None recorded.")
    pdf.ln(2)

    _section_title(pdf, "Evidence bundle")
    pdf.set_font("Courier", "", 8)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, certificate["evidence_bundle_hash"])
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, certificate["evidence_bundle_location"])
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 5, certificate["disclaimer"])

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path
