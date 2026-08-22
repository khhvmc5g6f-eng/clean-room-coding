"""The `cleanroom` CLI. See docs/quickstart.md.

Every command supports --json for machine-readable output (CI/CD, Part
III) and returns one of the documented exit codes (Part LXXXIV,
src/cleanroom/exit_codes.py).
"""

from __future__ import annotations

import json as jsonlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import yaml

from cleanroom import __version__
from cleanroom.config import default_config, load_config
from cleanroom.contamination import Contamination
from cleanroom.evidence import Actor
from cleanroom.exit_codes import (
    CleanRoomError,
    ContaminationFailure,
    ExitCode,
    LegalRed,
    LicenceFailure,
    PolicyFailure,
)
from cleanroom.handoff import manifest as handoff_manifest
from cleanroom.jurisdiction import resolver as jurisdiction_resolver
from cleanroom.legal import engine as legal_engine
from cleanroom.legal import panels as legal_panels
from cleanroom.licence import discovery as licence_discovery
from cleanroom.licence import policy as licence_policy
from cleanroom.orchestration.agents import AgentRegistry
from cleanroom.project import Project
from cleanroom.provenance import sbom as sbom_module
from cleanroom.report import build_certificate, release_allowed, render_final_report, save_certificate
from cleanroom.sanitisation import scanner as sanitisation_scanner
from cleanroom.schema_registry import schema_dir
from cleanroom.specification.behavioral import BehavioralSuite
from cleanroom.specification.graph import RequirementGraph
from cleanroom.util import hash_tree, sha256_json
from cleanroom.zones import create_zones, run_isolation_test


class Ctx:
    def __init__(self, project_root: Path, json_output: bool, quiet: bool, verbose: bool):
        self.project_root = project_root
        self.json_output = json_output
        self.quiet = quiet
        self.verbose = verbose

    def echo(self, message: str, **kwargs: Any) -> None:
        if not self.quiet and not self.json_output:
            click.echo(message, **kwargs)

    def emit(self, data: dict[str, Any], human: str | None = None) -> None:
        if self.json_output:
            click.echo(jsonlib.dumps(data, indent=2, sort_keys=True, default=str))
        elif not self.quiet:
            click.echo(human if human is not None else jsonlib.dumps(data, indent=2, sort_keys=True, default=str))

    def load_project(self) -> Project:
        try:
            return Project.discover(self.project_root)
        except CleanRoomError as e:
            raise click.ClickException(str(e)) from e

    def fail(self, error: CleanRoomError) -> None:
        self.emit({"error": str(error), "exit_code": int(error.exit_code)})
        sys.exit(int(error.exit_code))


pass_ctx = click.make_pass_decorator(Ctx)


@click.group()
@click.option("--project", "project_path", type=click.Path(path_type=Path), default=Path("."), help="Project root (default: current directory).")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None, help="Explicit .cleanroom.yml path (overrides discovery).")
@click.option("--json", "json_output", is_flag=True, default=False, help="Emit machine-readable JSON instead of human text.")
@click.option("--quiet", is_flag=True, default=False, help="Suppress non-essential output.")
@click.option("--verbose", is_flag=True, default=False, help="Verbose diagnostic output.")
@click.version_option(__version__, prog_name="cleanroom")
@click.pass_context
def main(click_ctx: click.Context, project_path: Path, config_path: Path | None, json_output: bool, quiet: bool, verbose: bool) -> None:
    """Clean Room Coding: reproducible, auditable clean-room reimplementation tooling."""
    click_ctx.obj = Ctx(project_root=project_path, json_output=json_output, quiet=quiet, verbose=verbose)


# --------------------------------------------------------------------------- init

@main.command()
@click.option("--name", prompt="Project name", help="Human-readable project name.")
@click.option("--id", "project_id", default=None, help="Machine identifier (default: derived from --name).")
@click.option("--force", is_flag=True, default=False, help="Overwrite an existing .cleanroom.yml.")
@pass_ctx
def init(ctx: Ctx, name: str, project_id: str | None, force: bool) -> None:
    """Create a new Clean Room Coding project in the current/target directory."""
    root = ctx.project_root
    root.mkdir(parents=True, exist_ok=True)
    config_file = root / ".cleanroom.yml"
    if config_file.exists() and not force:
        raise click.ClickException(f"{config_file} already exists. Use --force to overwrite.")

    pid = project_id or re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-") or "project"
    data = default_config(name, pid)
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)

    create_zones(
        root,
        root / data["zones"]["reference_path"],
        root / data["zones"]["handoff_path"],
        root / data["zones"]["implementation_path"],
    )
    project = Project.discover(root)
    project.evidence.append(
        actor=Actor(type="human", id="cli-user", role="initiator"),
        action="cleanroom init",
        result="success",
        detail=f"Created project '{name}' ({pid})",
    )
    ctx.emit(
        {"project": pid, "config": str(config_file), "zones": data["zones"]},
        human=(
            f"Project created.\n\n"
            f"Reference Zone:       {data['zones']['reference_path']}\n"
            f"Handoff Zone:         {data['zones']['handoff_path']}\n"
            f"Implementation Zone:  {data['zones']['implementation_path']}\n"
            f"Evidence Ledger:      enabled ({root / 'evidence'})\n"
        ),
    )


# --------------------------------------------------------------------------- doctor

@main.command()
@pass_ctx
def doctor(ctx: Ctx) -> None:
    """Check the local installation: schemas, policy/jurisdiction packs, git."""
    checks: dict[str, Any] = {}
    try:
        checks["schemas"] = {"status": "ok", "path": str(schema_dir())}
    except FileNotFoundError as e:
        checks["schemas"] = {"status": "fail", "detail": str(e)}

    try:
        packs = licence_policy.available_packs()
        checks["licence_policy_packs"] = {"status": "ok" if packs else "fail", "packs": packs}
    except FileNotFoundError as e:
        checks["licence_policy_packs"] = {"status": "fail", "detail": str(e)}

    juris_packs = jurisdiction_resolver.available_packs()
    checks["jurisdiction_packs"] = {"status": "ok" if juris_packs else "fail", "packs": juris_packs}

    checks["git"] = {"status": "ok" if shutil.which("git") else "fail"}
    checks["gpg"] = {"status": "ok" if shutil.which("gpg") else "warn (optional, needed for handoff signing)"}

    try:
        Project.discover(ctx.project_root)
        checks["project_config"] = {"status": "ok"}
    except CleanRoomError as e:
        checks["project_config"] = {"status": "warn", "detail": str(e)}

    failed = [k for k, v in checks.items() if v["status"] == "fail"]
    ctx.emit({"checks": checks, "ok": not failed}, human="\n".join(f"{k}: {v['status']}" for k, v in checks.items()))
    if failed:
        sys.exit(int(ExitCode.CONFIGURATION_ERROR))


# --------------------------------------------------------------------------- intake

@main.command()
@click.option("--source", required=True, help="Description or URL of the reference material.")
@click.option("--access-authority", type=click.Choice(["public", "licensed", "contractual", "unknown"]), default="unknown")
@click.option("--reverse-engineering-restricted/--no-reverse-engineering-restricted", default=False)
@click.option("--confidential/--not-confidential", default=False)
@click.option("--notes", default="")
@pass_ctx
def intake(ctx: Ctx, source: str, access_authority: str, reverse_engineering_restricted: bool, confidential: bool, notes: str) -> None:
    """Part IX: record the intake authority check before any analysis begins."""
    project = ctx.load_project()
    report_path = project.root / "ACCESS_AND_AUTHORITY_REPORT.md"
    existing = report_path.read_text(encoding="utf-8") if report_path.is_file() else "# Access and Authority Report\n\n"
    entry = (
        f"\n## {source}\n\n"
        f"- Access authority: **{access_authority}**\n"
        f"- Reverse-engineering restricted by terms: {reverse_engineering_restricted}\n"
        f"- Confidentiality obligations apply: {confidential}\n"
        f"- Notes: {notes or '(none)'}\n"
    )
    report_path.write_text(existing + entry, encoding="utf-8")
    project.evidence.append(
        actor=Actor(type="human", id="cli-user", role="intake-reviewer"),
        action="cleanroom intake",
        zone="R",
        result="success" if access_authority != "unknown" else "denied",
        detail=f"source={source} access_authority={access_authority}",
    )
    if access_authority == "unknown":
        ctx.echo("WARNING: access_authority is 'unknown'. Do not proceed to analysis until this is resolved (Part IX).")
    ctx.emit({"report": str(report_path), "access_authority": access_authority})


# --------------------------------------------------------------------------- inspect

@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False)
@pass_ctx
def inspect(ctx: Ctx, path: Path | None) -> None:
    """A deterministic first look at reference material: file counts, sizes,
    extension histogram and content hashes -- before the deeper `licence`
    scan or any LLM-driven `analyse`. Never opens/reads file content beyond
    what's needed to hash and size it."""
    project = ctx.load_project()
    target = path or project.zone_r
    tree = hash_tree(target)
    extensions: dict[str, int] = {}
    total_bytes = 0
    for rel in tree:
        ext = Path(rel).suffix or "(none)"
        extensions[ext] = extensions.get(ext, 0) + 1
        full = target / rel
        if full.is_file():
            total_bytes += full.stat().st_size

    summary = {
        "path": str(target),
        "file_count": len(tree),
        "total_bytes": total_bytes,
        "extensions": dict(sorted(extensions.items(), key=lambda kv: -kv[1])),
        "tree_hash": sha256_json(tree),
    }
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-inspect"),
        action="cleanroom inspect",
        zone="R" if target == project.zone_r else "none",
        result="success",
        detail=f"{summary['file_count']} file(s), {summary['total_bytes']} bytes under {target}",
    )
    ctx.emit(
        summary,
        human=(
            f"{summary['file_count']} file(s), {summary['total_bytes']} bytes under {target}\n"
            f"Extensions: {summary['extensions']}\n"
            f"Tree hash: {summary['tree_hash']}"
        ),
    )


# --------------------------------------------------------------------------- licence

@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False)
@pass_ctx
def licence(ctx: Ctx, path: Path | None) -> None:
    """Part X-XI: deterministic licence discovery and policy evaluation."""
    project = ctx.load_project()
    target = path or project.zone_r
    findings = licence_discovery.discover(target)
    allowed = project.config.data.get("dependency_policy", {}).get("allowed_licences", [])
    denied = project.config.data.get("dependency_policy", {}).get("denied_licences", [])
    unknown_action = project.config.data.get("dependency_policy", {}).get("unknown_licence_action", "block")

    results = []
    blocking = False
    for finding in findings:
        policy_result = licence_policy.evaluate(finding.concluded, allowed=allowed, denied=denied)
        is_blocking = licence_policy.is_blocking(policy_result["status"], unknown_action)
        blocking = blocking or is_blocking
        d = finding.to_dict()
        d["policy_result"] = policy_result
        results.append(d)

    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-licence-discovery"),
        action="cleanroom licence",
        zone="R",
        result="success",
        detail=f"{len(results)} location(s) scanned under {target}",
    )
    ctx.emit(
        {"scanned": str(target), "findings": results, "blocking": blocking},
        human="\n".join(f"{r['path']}: concluded={r['concluded']} status={r['policy_result']['status']}" for r in results) or "(no licence evidence found)",
    )
    if blocking:
        ctx.fail(LicenceFailure("One or more licence findings are denied or unresolved under project policy."))


# --------------------------------------------------------------------------- jurisdiction

@main.command()
@pass_ctx
def jurisdiction(ctx: Ctx) -> None:
    """Parts XII-XIV: resolve applicable jurisdictions -- never a single assumed one."""
    project = ctx.load_project()
    j = project.config.data["jurisdiction"]
    matrix = jurisdiction_resolver.build_matrix(
        project_id=project.config.project_id,
        required_markets=j["required_markets"],
        informational_markets=j.get("informational_markets", []),
    )
    out_path = project.root / "JURISDICTION_MATRIX.json"
    out_path.write_text(jsonlib.dumps(matrix, indent=2, sort_keys=True), encoding="utf-8")
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-jurisdiction-resolver"),
        action="cleanroom jurisdiction",
        result="success",
        detail=f"panels_convened={matrix['legal_panels_convened']}",
    )
    ctx.emit(matrix, human=f"Jurisdiction matrix written to {out_path}\nPanels convened: {matrix['legal_panels_convened']}")


# --------------------------------------------------------------------------- analyse

@main.command()
@pass_ctx
def analyse(ctx: Ctx) -> None:
    """Part XV: emit the source-analysis-panel task prompts (Zone R access, partitioned by role)."""
    project = ctx.load_project()
    roles = [
        "Product Analyst", "Functional Analyst", "UI Analyst", "UX Analyst", "Accessibility Analyst",
        "API Analyst", "Protocol Analyst", "Data Analyst", "Database Analyst", "Security Analyst",
        "Configuration Analyst", "Performance Analyst", "Platform Analyst", "Integration Analyst",
        "File Format Analyst", "Authentication Analyst", "Administration Analyst", "Testing Analyst",
        "Infrastructure Analyst",
    ]
    out_dir = project.root / "evidence" / "analysis-tasks"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for role in roles:
        slug = role.lower().replace(" ", "-")
        path = out_dir / f"{slug}.md"
        path.write_text(
            f"# {role} task\n\n"
            f"Scope: analyse Zone R ({project.zone_r}) strictly within your specialism.\n\n"
            "For every finding, classify it as one of:\n"
            "- OBSERVABLE REQUIREMENT (behaviour a user/caller can observe) -- eligible for handoff.\n"
            "- SOURCE IMPLEMENTATION DETAIL (internal structure/algorithm/naming) -- excluded from handoff (Part XVI).\n\n"
            "Do not report 'tell us everything' style findings; stay within this role's partition.\n"
            "Write findings as requirement.schema.json nodes for 'cleanroom specify add-requirement'.\n",
            encoding="utf-8",
        )
        written.append(str(path))
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-cli"),
        action="cleanroom analyse",
        zone="R",
        result="success",
        detail=f"{len(written)} analyst task file(s) written",
    )
    ctx.emit({"tasks_written": written})


# --------------------------------------------------------------------------- specify

@main.group()
def specify() -> None:
    """Part XVIII-XIX: manage the requirement graph and behavioural tests."""


@specify.command("add-requirement")
@click.option("--id", "req_id", required=True)
@click.option("--kind", type=click.Choice(["requirement", "feature", "screen", "api", "acceptance_test", "implementation", "verification"]), required=True)
@click.option("--statement", required=True)
@click.option("--classification", type=click.Choice(["observable_requirement", "source_implementation_detail"]), required=True)
@click.option("--contamination", type=click.Choice([c.value for c in Contamination]), default="C0")
@pass_ctx
def add_requirement(ctx: Ctx, req_id: str, kind: str, statement: str, classification: str, contamination: str) -> None:
    project = ctx.load_project()
    graph_path = project.root / "requirements.json"
    graph = RequirementGraph.load(graph_path)
    graph.add({
        "id": req_id, "kind": kind, "statement": statement,
        "classification": classification, "contamination_level": contamination,
        "status": "proposed",
    })
    graph.save(graph_path)
    project.evidence.append(actor=Actor(type="human", id="cli-user"), action="specify add-requirement", detail=req_id)
    ctx.emit({"id": req_id, "saved_to": str(graph_path)})


@specify.command("report")
@pass_ctx
def specify_report(ctx: Ctx) -> None:
    project = ctx.load_project()
    graph = RequirementGraph.load(project.root / "requirements.json")
    ctx.emit(graph.traceability_report())


@specify.command("add-behavioral")
@click.option("--given", required=True)
@click.option("--when", required=True)
@click.option("--then", required=True)
@click.option("--requirement", "requirement_ids", multiple=True, required=True)
@pass_ctx
def add_behavioral(ctx: Ctx, given: str, when: str, then: str, requirement_ids: tuple[str, ...]) -> None:
    project = ctx.load_project()
    path = project.root / "behavioral_tests.json"
    suite = BehavioralSuite.load(path)
    test_id = suite.next_id()
    suite.add({"id": test_id, "given": given, "when": when, "then": then, "requirement_ids": list(requirement_ids), "result": "not_tested"})
    suite.save(path)
    ctx.emit({"id": test_id, "saved_to": str(path)})


# --------------------------------------------------------------------------- sanitise

@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@pass_ctx
def sanitise(ctx: Ctx, path: Path) -> None:
    """Parts XX-XXI: scan a candidate handoff document; block on secrets/verbatim overlap."""
    project = ctx.load_project()
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = sanitisation_scanner.scan(text)
    blocked = sanitisation_scanner.is_handoff_blocked(findings)
    report = {
        "source_document": str(path),
        "findings": [f.to_dict() for f in findings],
        "blocked": blocked,
    }
    report_path = project.root / "evidence" / "sanitisation-reports" / f"{path.name}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(jsonlib.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-sanitisation-scanner"),
        action="cleanroom sanitise",
        result="denied" if blocked else "success",
        detail=str(path),
    )
    ctx.emit(report)
    if blocked:
        ctx.fail(ContaminationFailure(f"{path} contains blocking sanitisation findings; see {report_path}"))


# --------------------------------------------------------------------------- handoff

@main.command()
@click.option("--specification-version", required=True)
@click.option("--all-c0", is_flag=True, default=False, help="Classify every file currently in Zone H as C0 (only use once sanitisation is complete).")
@click.option("--signer", default=None)
@pass_ctx
def handoff(ctx: Ctx, specification_version: str, all_c0: bool, signer: str | None) -> None:
    """Parts XXIV-XXV: build the immutable, hashed HANDOFF_MANIFEST.json."""
    project = ctx.load_project()
    if not all_c0:
        raise click.ClickException("Pass --all-c0 once every file in Zone H has been sanitised and classified C0, or classify files individually via the Python API.")
    file_contamination = {
        p.relative_to(project.zone_h).as_posix(): "C0"
        for p in project.zone_h.rglob("*")
        if p.is_file() and p.name not in (handoff_manifest.MANIFEST_FILENAME, handoff_manifest.HANDOFF_DOC_FILENAME, ".gitkeep")
    }
    sanitisation_reports_hash = "0" * 64
    reports_dir = project.root / "evidence" / "sanitisation-reports"
    if reports_dir.is_dir():
        from cleanroom.util import sha256_json
        combined = sorted(p.name for p in reports_dir.glob("*.json"))
        sanitisation_reports_hash = sha256_json(combined)

    try:
        m = handoff_manifest.build_manifest(
            project_id=project.config.project_id,
            specification_version=specification_version,
            zone_h=project.zone_h,
            file_contamination=file_contamination,
            sanitisation_report_hash=sanitisation_reports_hash,
            signer=signer,
        )
    except ContaminationFailure as e:
        ctx.fail(e)
        return
    m = handoff_manifest.sign_manifest(m, gpg_key_id=signer)
    manifest_path = handoff_manifest.write_manifest(m, project.zone_h)
    doc_path = handoff_manifest.write_handoff_doc(m, project.zone_h)
    project.evidence.append(
        actor=Actor(type="human" if signer else "tool", id=signer or "cleanroom-cli"),
        action="cleanroom handoff",
        zone="H",
        result="success",
        outputs=[{"path": str(manifest_path), "sha256": m["manifest_hash"]}],
        detail=f"{len(m['files'])} file(s) in handoff bundle",
    )
    ctx.emit({"manifest": str(manifest_path), "doc": str(doc_path), "manifest_hash": m["manifest_hash"]})


# --------------------------------------------------------------------------- architect

@main.command()
@click.option("--title", required=True)
@click.option("--decision", required=True)
@click.option("--rationale", required=True)
@pass_ctx
def architect(ctx: Ctx, title: str, decision: str, rationale: str) -> None:
    """Part XXIX: record an Architecture Decision Record originating from the
    clean specification, not the reference implementation's internal design."""
    project = ctx.load_project()
    adr_dir = project.root / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md"))
    n = len(existing) + 1
    slug = re.sub(r"[^a-z0-9-]", "-", title.lower()).strip("-")
    path = adr_dir / f"{n:04d}-{slug}.md"
    path.write_text(
        f"# {n:04d}. {title}\n\n## Status\n\nAccepted\n\n## Decision\n\n{decision}\n\n"
        f"## Rationale\n\n{rationale}\n\n## Independence note\n\nThis decision was derived from "
        "the handoff specification and this project's own requirements (maintainability, "
        "security, scalability, testability, platform conventions), not from the reference "
        "implementation's internal architecture (Part XXIX).\n",
        encoding="utf-8",
    )
    project.evidence.append(actor=Actor(type="human", id="cli-user", role="architect"), action="cleanroom architect", zone="I", detail=str(path))
    ctx.emit({"adr": str(path)})


# --------------------------------------------------------------------------- build

@main.command()
@click.option("--role", required=True, help="e.g. 'Backend Team', 'Frontend Team'.")
@click.option("--model-provider", default=None)
@click.option("--model-id", default=None)
@pass_ctx
def build(ctx: Ctx, role: str, model_provider: str | None, model_id: str | None) -> None:
    """Part XXVI: register a fresh, source-blind implementation agent scoped to Zone H + Zone I only."""
    project = ctx.load_project()
    registry = AgentRegistry(project.root / "evidence")
    record = registry.register(
        role=role,
        permitted_zones=["H", "I"],
        prohibited_paths=[str(project.zone_r)],
        model_provider=model_provider,
        model_id=model_id,
        supplied_documents=[str(p) for p in project.zone_h.rglob("*") if p.is_file()],
    )
    project.evidence.append(
        actor=Actor(type="agent", id=record.agent_id, role=role, model_provider=model_provider, model_id=model_id),
        action="cleanroom build (agent registered)",
        zone="I",
        result="success",
    )
    ctx.emit(record.to_dict())


# --------------------------------------------------------------------------- test

@main.command()
@click.option("--pytest-args", default="", help="Extra arguments forwarded to pytest, if Zone I has a Python test suite.")
@pass_ctx
def test(ctx: Ctx, pytest_args: str) -> None:
    """Run the behavioural suite summary, and Zone I's own test suite if present."""
    project = ctx.load_project()
    suite = BehavioralSuite.load(project.root / "behavioral_tests.json")
    summary = suite.summary()

    pytest_result = None
    if (project.zone_i / "tests").is_dir() or list(project.zone_i.glob("test_*.py")):
        cmd = [sys.executable, "-m", "pytest", str(project.zone_i)] + (pytest_args.split() if pytest_args else [])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        pytest_result = {"returncode": proc.returncode, "stdout_tail": proc.stdout[-3000:], "stderr_tail": proc.stderr[-2000:]}

    project.evidence.append(actor=Actor(type="tool", id="cleanroom-test"), action="cleanroom test", zone="I", result="success")
    ctx.emit({"behavioral_summary": summary, "pytest": pytest_result})
    if pytest_result and pytest_result["returncode"] != 0:
        sys.exit(int(ExitCode.TEST_FAILURE))


# --------------------------------------------------------------------------- compare

@main.command()
@click.argument("reference_output", type=click.Path(exists=True, path_type=Path))
@click.argument("implementation_output", type=click.Path(exists=True, path_type=Path))
@click.option("--ignore-timestamps", is_flag=True, default=False)
@click.option("--ignore-ordering", is_flag=True, default=False)
@click.option("--float-epsilon", type=float, default=None)
@pass_ctx
def compare(ctx: Ctx, reference_output: Path, implementation_output: Path, ignore_timestamps: bool, ignore_ordering: bool, float_epsilon: float | None) -> None:
    """Part XXXI: the functional equivalence engine -- compare observable
    outputs (not code) under configurable tolerance rules."""
    a = reference_output.read_text(encoding="utf-8", errors="replace")
    b = implementation_output.read_text(encoding="utf-8", errors="replace")

    ts_re = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")
    if ignore_timestamps:
        a = ts_re.sub("<TIMESTAMP>", a)
        b = ts_re.sub("<TIMESTAMP>", b)

    a_lines, b_lines = a.splitlines(), b.splitlines()
    if ignore_ordering:
        a_lines, b_lines = sorted(a_lines), sorted(b_lines)

    if float_epsilon is not None:
        float_re = re.compile(r"-?\d+\.\d+")

        def round_floats(lines: list[str]) -> list[str]:
            return [float_re.sub(lambda m: f"{round(float(m.group(0)) / float_epsilon) * float_epsilon:.6g}", ln) for ln in lines]

        a_lines, b_lines = round_floats(a_lines), round_floats(b_lines)

    equivalent = a_lines == b_lines
    diff_count = sum(1 for x, y in zip(a_lines, b_lines) if x != y) + abs(len(a_lines) - len(b_lines))
    ctx.emit({"equivalent": equivalent, "differing_lines": diff_count, "reference_line_count": len(a_lines), "implementation_line_count": len(b_lines)})
    if not equivalent:
        sys.exit(int(ExitCode.TEST_FAILURE))


# --------------------------------------------------------------------------- provenance

@main.command()
@pass_ctx
def provenance(ctx: Ctx) -> None:
    """Parts XXXVII-XXXVIII: generate SPDX + CycloneDX SBOMs for Zone I."""
    project = ctx.load_project()
    deps = sbom_module.discover_dependencies(project.zone_i)
    spdx_doc = sbom_module.to_spdx(project.config.project_id, "0.0.0", deps)
    cdx_doc = sbom_module.to_cyclonedx(project.config.project_id, "0.0.0", deps)
    out_dir = project.root / "evidence" / "sbom"
    sbom_module.save(spdx_doc, out_dir / "sbom.spdx.json")
    sbom_module.save(cdx_doc, out_dir / "sbom.cyclonedx.json")
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-sbom"), action="cleanroom provenance", zone="I", result="success", detail=f"{len(deps)} declared dependencies")
    ctx.emit({"dependencies": len(deps), "spdx": str(out_dir / "sbom.spdx.json"), "cyclonedx": str(out_dir / "sbom.cyclonedx.json")})


# --------------------------------------------------------------------------- audit

@main.command()
@pass_ctx
def audit(ctx: Ctx) -> None:
    """Combined technical audit: isolation test, licence policy, ledger integrity."""
    project = ctx.load_project()
    isolation_ok, isolation_detail = run_isolation_test(project.zone_r, project.zone_h, project.zone_i)
    ledger_problems = project.evidence.verify_chain()

    findings = licence_discovery.discover(project.zone_h)
    non_c0 = [f for f in findings if f.concluded and f.concluded not in ("MIT", "Apache-2.0")]

    result = {
        "isolation_test": {"passed": isolation_ok, "detail": isolation_detail},
        "evidence_chain_intact": not ledger_problems,
        "evidence_chain_problems": ledger_problems,
        "zone_h_licence_findings": [f.to_dict() for f in findings],
    }
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-audit"), action="cleanroom audit", result="success" if isolation_ok and not ledger_problems else "failure")
    ctx.emit(result)
    if not isolation_ok:
        sys.exit(int(ExitCode.CONTAMINATION_FAILURE))
    if ledger_problems:
        sys.exit(int(ExitCode.GENERAL_FAILURE))


# --------------------------------------------------------------------------- legal

@main.command()
@click.option("--access-authority", type=click.Choice(["public", "licensed", "contractual", "unknown"]), default="unknown")
@pass_ctx
def legal(ctx: Ctx, access_authority: str) -> None:
    """Part XLIV: run the heuristic legal issue engine. NOT LEGAL ADVICE."""
    project = ctx.load_project()
    licence_findings = [f.to_dict() for f in licence_discovery.discover(project.zone_r)]
    isolation_ok, _ = run_isolation_test(project.zone_r, project.zone_h, project.zone_i)
    j = project.config.data["jurisdiction"]
    markets = j["required_markets"] + [m for m in j.get("informational_markets", []) if m not in j["required_markets"]]
    findings: list[dict[str, Any]] = []
    for market in markets or ["unspecified"]:
        bundle = legal_engine.CaseBundle(
            access_authority=access_authority,
            licence_findings=licence_findings,
            isolation_test_passed=isolation_ok,
            output_distribution_model=project.config.data.get("implementation", {}).get("distribution_model"),
            reference_licence_ids=[f.get("concluded") for f in licence_findings if f.get("concluded")],
            jurisdiction=market,
        )
        findings.extend(legal_engine.run(bundle))
    out_path = project.root / "evidence" / "legal-findings.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(jsonlib.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    project.evidence.append(actor=Actor(type="tool", id="simulated-legal-issue-engine"), action="cleanroom legal", result="success", detail=str(out_path))
    ctx.emit({"findings": findings, "saved_to": str(out_path)})


# --------------------------------------------------------------------------- judge

@main.command()
@pass_ctx
def judge(ctx: Ctx) -> None:
    """Parts XLV-LI: build adversarial-counsel + judicial-review prompts for
    every convened jurisdiction panel. Output must be answered by an LLM
    (Claude Code or another harness) -- this command does not call one."""
    project = ctx.load_project()
    matrix_path = project.root / "JURISDICTION_MATRIX.json"
    findings_path = project.root / "evidence" / "legal-findings.json"
    if not matrix_path.is_file() or not findings_path.is_file():
        raise click.ClickException("Run 'cleanroom jurisdiction' and 'cleanroom legal' first.")
    matrix = jsonlib.loads(matrix_path.read_text(encoding="utf-8"))
    findings = jsonlib.loads(findings_path.read_text(encoding="utf-8"))

    out_dir = project.root / "evidence" / "judicial-review"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for pack_id in matrix["legal_panels_convened"]:
        pack = jurisdiction_resolver.load_pack(pack_id)
        if not pack:
            continue
        applicant = legal_panels.build_applicant_brief_prompt(pack, findings)
        challenger = legal_panels.build_challenger_brief_prompt(pack, findings)
        judicial = legal_panels.build_judicial_review_prompt(pack, applicant, challenger, findings)
        (out_dir / f"{pack_id}-applicant-prompt.md").write_text(applicant, encoding="utf-8")
        (out_dir / f"{pack_id}-challenger-prompt.md").write_text(challenger, encoding="utf-8")
        (out_dir / f"{pack_id}-judicial-prompt.md").write_text(judicial, encoding="utf-8")
        written[pack_id] = str(out_dir)

    project.evidence.append(actor=Actor(type="tool", id="cleanroom-judge"), action="cleanroom judge", result="success", detail=f"panels={list(written)}")
    ctx.emit({"prompts_written_for": written, "directory": str(out_dir)})


# --------------------------------------------------------------------------- verify

@main.command()
@pass_ctx
def verify(ctx: Ctx) -> None:
    """Re-derive every hash this project has produced and compare against
    what was recorded -- proves nothing was silently altered."""
    project = ctx.load_project()
    ledger_problems = project.evidence.verify_chain()
    manifest_path = project.zone_h / handoff_manifest.MANIFEST_FILENAME
    manifest_problems: list[str] = []
    if manifest_path.is_file():
        m = jsonlib.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_problems = handoff_manifest.verify_manifest(m, project.zone_h)
    ok = not ledger_problems and not manifest_problems
    ctx.emit({"ledger_intact": not ledger_problems, "ledger_problems": ledger_problems, "handoff_manifest_intact": not manifest_problems, "handoff_manifest_problems": manifest_problems})
    if not ok:
        sys.exit(int(ExitCode.GENERAL_FAILURE))


# --------------------------------------------------------------------------- report / release / status

@main.command()
@click.option("--version", "version", default="0.0.0")
@pass_ctx
def report(ctx: Ctx, version: str) -> None:
    """Part XCIII: assemble the final report and CLEAN_ROOM_CERTIFICATE.json."""
    project = ctx.load_project()
    graph = RequirementGraph.load(project.root / "requirements.json")
    trace = graph.traceability_report()
    suite = BehavioralSuite.load(project.root / "behavioral_tests.json")
    tests_summary = suite.summary()

    findings_path = project.root / "evidence" / "legal-findings.json"
    legal_findings = jsonlib.loads(findings_path.read_text(encoding="utf-8")) if findings_path.is_file() else []
    by_jurisdiction: dict[str, list[dict[str, Any]]] = {}
    for f in legal_findings:
        by_jurisdiction.setdefault(f["jurisdiction"], []).append(f)
    jurisdiction_decisions = {j: legal_panels.aggregate_jurisdiction_decision(fs) for j, fs in by_jurisdiction.items()}
    required_markets = project.config.required_markets()
    global_decision = legal_panels.global_decision(jurisdiction_decisions, required_markets) if jurisdiction_decisions else "AMBER"

    certificate = build_certificate(
        project=project.config.data["project"]["name"],
        version=version,
        reference=None,
        clean_room_level=project.config.clean_room_level,
        tests=tests_summary,
        requirement_traceability_percent=trace.get("completion_percent", 0.0),
        provenance_status="partial" if (project.root / "evidence" / "sbom").is_dir() else "unknown",
        similarity_result="not_run",
        jurisdictions=[{"jurisdiction": j, "decision_state": s, "required_market": j in required_markets} for j, s in jurisdiction_decisions.items()],
        global_decision=global_decision,
        outstanding_issues=[b["statement"] for b in graph.blockers()],
        evidence_bundle_location=str(project.root / "evidence"),
    )
    save_certificate(certificate, project.root / "CLEAN_ROOM_CERTIFICATE.json")
    report_text = render_final_report(certificate)
    (project.root / "CLEAN_ROOM_REPORT.md").write_text(report_text, encoding="utf-8")
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-report"), action="cleanroom report", result="success")
    ctx.emit(certificate, human=report_text)


@main.command()
@pass_ctx
def release(ctx: Ctx) -> None:
    """Part LVI: the release policy engine. Exits LEGAL_RED / POLICY_FAILURE on block."""
    project = ctx.load_project()
    cert_path = project.root / "CLEAN_ROOM_CERTIFICATE.json"
    if not cert_path.is_file():
        raise click.ClickException("Run 'cleanroom report' first.")
    certificate = jsonlib.loads(cert_path.read_text(encoding="utf-8"))
    policy = project.config.data["release_policy"]

    isolation_ok, _ = run_isolation_test(project.zone_r, project.zone_h, project.zone_i)
    ledger_ok = not project.evidence.verify_chain()

    allowed, reasons = release_allowed(
        technical_gate=certificate["tests"].get("fail", 0) == 0,
        provenance_gate=certificate["provenance_status"] != "unknown",
        contamination_gate=isolation_ok and ledger_ok,
        global_decision=certificate["global_decision"],
        require_technical_gate=policy["require_technical_gate"],
        require_provenance_gate=policy["require_provenance_gate"],
        require_contamination_gate=policy["require_contamination_gate"],
        block_on_red_required_jurisdiction=policy["block_on_red_required_jurisdiction"],
    )
    human_signoff_required = project.config.data.get("approval_gates", {}).get("human_signoff_required_for_release", True)
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-release"), action="cleanroom release", result="success" if allowed else "denied", detail="; ".join(reasons))
    ctx.emit({"release_allowed": allowed, "reasons": reasons, "human_signoff_still_required": human_signoff_required and allowed})
    if not allowed:
        if certificate["global_decision"] == "RED":
            sys.exit(int(ExitCode.LEGAL_RED))
        sys.exit(int(ExitCode.POLICY_FAILURE))
    if human_signoff_required:
        sys.exit(int(ExitCode.MANUAL_REVIEW_REQUIRED))


@main.command()
@pass_ctx
def status(ctx: Ctx) -> None:
    """Project status summary: zones, agents, requirement traceability, ledger."""
    project = ctx.load_project()
    graph = RequirementGraph.load(project.root / "requirements.json")
    registry = AgentRegistry(project.root / "evidence")
    ctx.emit({
        "project": project.config.project_id,
        "clean_room_level": project.config.clean_room_level,
        "zones": {"R": str(project.zone_r), "H": str(project.zone_h), "I": str(project.zone_i)},
        "requirement_traceability": graph.traceability_report(),
        "agents": [a.to_dict() for a in registry.all()],
        "orphaned_agents": [a.agent_id for a in registry.orphaned()],
        "ledger_events": len(project.evidence.read_all()),
    })


def main_entry() -> None:
    try:
        main(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except CleanRoomError as e:
        click.echo(str(e), err=True)
        sys.exit(int(e.exit_code))


if __name__ == "__main__":
    main_entry()
