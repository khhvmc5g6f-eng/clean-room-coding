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
from cleanroom import benchmark as benchmark_module
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
from cleanroom.legal import remediation as remediation_module
from cleanroom.licence import discovery as licence_discovery
from cleanroom.licence import policy as licence_policy
from cleanroom import maturity
from cleanroom.orchestration import heartbeat as heartbeat_module
from cleanroom.orchestration.agents import AgentRegistry
from cleanroom.project import Project
from cleanroom.provenance import intoto as intoto_module
from cleanroom.provenance import sbom as sbom_module
from cleanroom.provenance import transitive as transitive_module
from cleanroom.report import (
    build_certificate,
    release_allowed,
    render_final_report,
    render_html_report,
    save_certificate,
)
from cleanroom.sanitisation import scanner as sanitisation_scanner
from cleanroom.sanitisation.differential import DifferentialEntry, SanitisationReport
from cleanroom import schema_registry
from cleanroom.schema_registry import schema_dir
from cleanroom.similarity import engine as similarity_engine
from cleanroom.specification.behavioral import BehavioralSuite
from cleanroom.specification.graph import RequirementGraph
from cleanroom.util import hash_tree, sha256_json, utc_now_iso
from cleanroom.zones import (
    AgentZoneScope,
    PathGuard,
    ZoneAccessDenied,
    check_agent_zone_consistency,
    create_zones,
    run_pathguard_self_test,
)


class Ctx:
    def __init__(
        self, project_root: Path, config_path: Path | None, json_output: bool, quiet: bool, verbose: bool,
        agent_id: str | None = None,
    ):
        self.project_root = project_root
        self.config_path = config_path
        self.json_output = json_output
        self.quiet = quiet
        self.verbose = verbose
        self.agent_id = agent_id

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
            return Project.discover(self.project_root, explicit_config_path=self.config_path)
        except CleanRoomError as e:
            raise click.ClickException(str(e)) from e

    def fail(self, error: CleanRoomError) -> None:
        self.emit({"error": str(error), "exit_code": int(error.exit_code)})
        sys.exit(int(error.exit_code))

    def enforce_zone_access(self, project: Project, path: Path) -> None:
        """Part V-VII: the real per-invocation `PathGuard` gate the rest of
        this file's docstrings say doesn't exist yet -- it now does, but
        only opt-in via `--agent-id`, and only for the commands that call
        this. Without `--agent-id` this is a no-op (existing behaviour is
        unchanged); the caller is responsible for calling this before it
        actually reads `path`, not after."""
        if self.agent_id is None:
            return
        registry = AgentRegistry(project.root / "evidence")
        record = next((a for a in registry.all() if a.agent_id == self.agent_id), None)
        if record is None:
            raise click.ClickException(f"No agent registered with id '{self.agent_id}' (register one with 'cleanroom build' first).")
        scope = AgentZoneScope(
            agent_id=record.agent_id, role=record.role,
            permitted_zones=frozenset(record.permitted_zones),
            prohibited_paths=tuple(Path(p) for p in record.prohibited_paths),
        )
        guard = PathGuard(scope, project.zone_r, project.zone_h, project.zone_i)
        try:
            guard.check(path)
        except ZoneAccessDenied as e:
            self.fail(ContaminationFailure(f"PathGuard denied agent '{self.agent_id}' access to {path}: {e}"))


pass_ctx = click.make_pass_decorator(Ctx)


@click.group()
@click.option("--project", "project_path", type=click.Path(path_type=Path), default=Path("."), help="Project root (default: current directory).")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), default=None, help="Explicit .cleanroom.yml path (overrides discovery).")
@click.option("--json", "json_output", is_flag=True, default=False, help="Emit machine-readable JSON instead of human text.")
@click.option("--quiet", is_flag=True, default=False, help="Suppress non-essential output.")
@click.option("--verbose", is_flag=True, default=False, help="Verbose diagnostic output.")
@click.option(
    "--agent-id", "agent_id", default=None,
    help="A 'cleanroom build'-registered agent id this invocation is acting on behalf of. When given, commands that read Zone R/H/I gate that read through a real per-invocation PathGuard.check() against that agent's actual registered scope (Part V-VII) -- omit it and behaviour is exactly as before (no gating). This is how an orchestration harness that knows which agent it just spawned gets real enforcement, not just the isolation self-test.",
)
@click.version_option(__version__, prog_name="cleanroom")
@click.pass_context
def main(click_ctx: click.Context, project_path: Path, config_path: Path | None, json_output: bool, quiet: bool, verbose: bool, agent_id: str | None) -> None:
    """Clean Room Coding: reproducible, auditable clean-room reimplementation tooling."""
    click_ctx.obj = Ctx(project_root=project_path, config_path=config_path, json_output=json_output, quiet=quiet, verbose=verbose, agent_id=agent_id)


# --------------------------------------------------------------------------- init

@main.command()
@click.option("--name", prompt="Project name", help="Human-readable project name.")
@click.option("--id", "project_id", default=None, help="Machine identifier (default: derived from --name).")
@click.option(
    "--target-language",
    prompt="Target implementation language (e.g. 'same-as-reference', 'python', 'dart', 'typescript', 'rust')",
    default="same-as-reference",
    help=(
        "The reimplementation is never a mechanical translation of the reference's source "
        "(that would defeat clean-room independence) -- so the target language is a free "
        "choice for the implementation team, not something inherited from Zone R. Record it "
        "up front so the answer is explicit rather than assumed."
    ),
)
@click.option("--force", is_flag=True, default=False, help="Overwrite an existing .cleanroom.yml.")
@pass_ctx
def init(ctx: Ctx, name: str, project_id: str | None, target_language: str, force: bool) -> None:
    """Create a new Clean Room Coding project in the current/target directory."""
    root = ctx.project_root
    root.mkdir(parents=True, exist_ok=True)
    config_file = root / ".cleanroom.yml"
    if config_file.exists() and not force:
        raise click.ClickException(f"{config_file} already exists. Use --force to overwrite.")

    pid = project_id or re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-") or "project"
    data = default_config(name, pid, target_language=target_language)
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
        detail=f"Created project '{name}' ({pid}), target_language={target_language}",
    )
    ctx.emit(
        {"project": pid, "config": str(config_file), "zones": data["zones"], "target_language": target_language},
        human=(
            f"Project created.\n\n"
            f"Reference Zone:       {data['zones']['reference_path']}\n"
            f"Handoff Zone:         {data['zones']['handoff_path']}\n"
            f"Implementation Zone:  {data['zones']['implementation_path']}\n"
            f"Target language:      {target_language}\n"
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
    ctx.enforce_zone_access(project, target)
    tree, skipped = hash_tree(target)
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
        "skipped": skipped,
    }
    if skipped:
        ctx.echo(f"WARNING: {len(skipped)} path(s) skipped as unsafe (symlink escaping root, or not a regular file) -- see 'skipped' in output.")
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-inspect"),
        action="cleanroom inspect",
        zone="R" if target == project.zone_r else "none",
        result="success",
        detail=f"{summary['file_count']} file(s), {summary['total_bytes']} bytes under {target}, {len(skipped)} skipped",
    )
    ctx.emit(
        summary,
        human=(
            f"{summary['file_count']} file(s), {summary['total_bytes']} bytes under {target}\n"
            f"Extensions: {summary['extensions']}\n"
            f"Tree hash: {summary['tree_hash']}"
            + (f"\nSkipped: {skipped}" if skipped else "")
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
    ctx.enforce_zone_access(project, target)
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
        result="denied" if blocking else "success",
        detail=f"{len(results)} location(s) scanned under {target}, blocking={blocking}",
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
    """Parts XX-XXI: scan a candidate handoff document; block on secrets/
    verbatim overlap. Persists a real SanitisationReport (the raw-analysis/
    sanitised-specification differential -- what would be removed, and
    why) rather than just the raw finding list."""
    project = ctx.load_project()
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = sanitisation_scanner.scan(text)
    blocked = sanitisation_scanner.is_handoff_blocked(findings)
    differential_report = SanitisationReport(
        source_document=str(path),
        raw_analysis_ref=str(path),
        findings=findings,
        entries=[
            DifferentialEntry(
                raw_excerpt=f.excerpt,
                sanitised_excerpt=None,
                action="removed",
                reason=f.detail,
            )
            for f in findings
            if f.severity == "blocking"
        ],
    )
    report_path = project.root / "evidence" / "sanitisation-reports" / f"{path.name}.json"
    differential_report.save(report_path)
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-sanitisation-scanner"),
        action="cleanroom sanitise",
        result="denied" if blocked else "success",
        detail=str(path),
    )
    ctx.emit(differential_report.to_dict())
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
        project.evidence.append(
            actor=Actor(type="human" if signer else "tool", id=signer or "cleanroom-cli"),
            action="cleanroom handoff",
            zone="H",
            result="denied",
            detail=str(e),
        )
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


# --------------------------------------------------------------------------- ai-suggest

@main.command(name="ai-suggest")
@click.option("--want-ai/--no-ai", "want_ai", default=None, help="Skip the interactive yes/no prompt.")
@click.option("--capability", default=None, help="Free-text AI capability to search for, e.g. 'text classification'.")
@click.option("--embeddable-only", is_flag=True, default=False, help="Only show models that don't require a dedicated inference server.")
@click.option("--limit", default=10, help="Max models to return.")
@pass_ctx
def ai_suggest(ctx: Ctx, want_ai: bool | None, capability: str | None, embeddable_only: bool, limit: int) -> None:
    """Before implementing, ask explicitly whether AI/ML capability should
    be added -- and if so, search the real Hugging Face Hub for candidate
    models, distinguishing embeddable/standalone models (ONNX/GGUF/TFLite/
    CoreML -- no server needed) from ones that require a dedicated
    inference server, and cross-checking each model's licence against this
    project's own dependency_policy. Never recommends a single "the"
    model -- this is a structured shortlist for a human decision."""
    project = ctx.load_project()
    if want_ai is None:
        want_ai = click.confirm("Do you want to add AI/ML capability to this reimplementation?", default=False)

    if not want_ai:
        project.evidence.append(actor=Actor(type="human", id="cli-user"), action="cleanroom ai-suggest", detail="declined")
        ctx.emit({"ai_requested": False})
        return

    if not capability:
        capability = click.prompt("Describe the desired AI capability (e.g. 'text classification', 'speech to text', 'code similarity')")

    try:
        from cleanroom.ai.suggest import evaluate_against_policy, search_models
        suggestions = search_models(capability, limit=limit)
    except ImportError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:  # network/Hub API failure -- a real external-system boundary
        raise click.ClickException(f"Hugging Face Hub search failed: {e}") from e

    allowed = project.config.data.get("dependency_policy", {}).get("allowed_licences", [])
    denied = project.config.data.get("dependency_policy", {}).get("denied_licences", [])
    suggestions = evaluate_against_policy(suggestions, allowed=allowed, denied=denied)
    if embeddable_only:
        suggestions = [s for s in suggestions if s.deployment_shape == "embeddable"]

    out_path = project.root / "evidence" / "ai-model-suggestions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [s.to_dict() for s in suggestions]
    out_path.write_text(jsonlib.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-ai-suggest"), action="cleanroom ai-suggest",
        detail=f"capability={capability!r}, {len(suggestions)} suggestion(s)",
    )
    ctx.emit(
        {"ai_requested": True, "capability": capability, "suggestions": payload, "saved_to": str(out_path)},
        human="\n".join(
            f"{s['model_id']} [{s['deployment_shape']}] licence={s['licence']} policy={s['licence_policy_status']} -- {s['url']}"
            for s in payload
        ) or "(no models found)",
    )


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


# --------------------------------------------------------------------------- heartbeat

_HEARTBEAT_TERMINAL_STATUSES = {"COMPLETE", "TERMINATED", "FAILED"}


@main.command()
@click.argument("agent_id")
@click.option("--action-signature", required=True, help="Short string identifying the kind of action just taken (e.g. 'edit:src/foo.py', 'run-tests'). The same signature repeated across ticks is what LOOPING detects.")
@click.option("--files-modified", type=int, default=0, help="Number of files this tick actually modified. Zero across several ticks is what STALLED detects.")
@click.option("--test-result", type=click.Choice(["pass", "fail"]), default=None)
@click.option("--repeat-threshold", type=int, default=3)
@pass_ctx
def heartbeat(ctx: Ctx, agent_id: str, action_signature: str, files_modified: int, test_result: str | None, repeat_threshold: int) -> None:
    """Part XXVIII: record one observation tick for a registered agent and
    diagnose ACTIVE/STALLED/LOOPING from its real tick history. This CLI is
    stateless/one-shot -- whatever is actually orchestrating multiple
    agents over time (a script, CI, another harness) should call this once
    per meaningful action/tick so a stalled or looping agent is caught
    deterministically rather than silently running forever."""
    project = ctx.load_project()
    registry = AgentRegistry(project.root / "evidence")
    agents_by_id = {a.agent_id: a for a in registry.all()}
    if agent_id not in agents_by_id:
        raise click.ClickException(f"No agent registered with id {agent_id}. Register one first with 'cleanroom build'.")

    evidence_dir = project.root / "evidence"
    heartbeat_module.append_tick(
        evidence_dir, agent_id,
        heartbeat_module.Tick(action_signature=action_signature, files_modified=files_modified, test_result=test_result),
    )
    ticks = heartbeat_module.load_ticks(evidence_dir, agent_id)
    status = heartbeat_module.diagnose(ticks, repeat_threshold=repeat_threshold)
    recommended_action = heartbeat_module.recommend_action(status)

    # diagnose() only ever returns ACTIVE/STALLED/LOOPING from the tick
    # history alone -- it has no visibility into explicit statuses a human
    # or the harness set for reasons outside this observation log (an
    # explicit BLOCKED/WAITING dependency wait, or a terminal COMPLETE/
    # TERMINATED/FAILED). Only overwrite the registry when the diagnosis
    # actually found a problem, and never resurrect an agent already in a
    # terminal state.
    if status in ("STALLED", "LOOPING") and agents_by_id[agent_id].status not in _HEARTBEAT_TERMINAL_STATUSES:
        registry.set_status(agent_id, status)

    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-heartbeat"), action="cleanroom heartbeat",
        result="success", detail=f"agent={agent_id} status={status} tick_count={len(ticks)}",
    )
    ctx.emit({"agent_id": agent_id, "status": status, "recommended_action": recommended_action, "tick_count": len(ticks)})


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
        if float_epsilon <= 0:
            raise click.ClickException("--float-epsilon must be a positive number.")
        float_re = re.compile(r"-?\d+\.\d+")

        def round_floats(lines: list[str]) -> list[str]:
            return [float_re.sub(lambda m: f"{round(float(m.group(0)) / float_epsilon) * float_epsilon:.6g}", ln) for ln in lines]

        a_lines, b_lines = round_floats(a_lines), round_floats(b_lines)

    equivalent = a_lines == b_lines
    diff_count = sum(1 for x, y in zip(a_lines, b_lines) if x != y) + abs(len(a_lines) - len(b_lines))
    ctx.emit({"equivalent": equivalent, "differing_lines": diff_count, "reference_line_count": len(a_lines), "implementation_line_count": len(b_lines)})
    if not equivalent:
        sys.exit(int(ExitCode.TEST_FAILURE))


# --------------------------------------------------------------------------- similarity

@main.command()
@click.argument("reference_path", type=click.Path(exists=True, path_type=Path))
@click.argument("implementation_path", type=click.Path(exists=True, path_type=Path))
@click.option("--negative-control", "negative_controls", multiple=True, type=click.Path(exists=True, path_type=Path), help="An unrelated project in the same language, for background scoring (Part XXXVI). Repeatable.")
@click.option("--max-comparisons", type=int, default=2000, help="Cap on all-pairs fallback comparisons when files don't match by name.")
@pass_ctx
def similarity(ctx: Ctx, reference_path: Path, implementation_path: Path, negative_controls: tuple[Path, ...], max_comparisons: int) -> None:
    """Parts XXXIV-XXXVI: lexical + structural similarity across two source
    trees, with negative-control background scoring. Never auto-classifies
    above 'suspicious' -- REQUIRED/CONSTRAINED/MATERIAL need human review."""
    project = ctx.load_project()
    ctx.enforce_zone_access(project, reference_path)
    ctx.enforce_zone_access(project, implementation_path)
    thresholds = project.config.data.get("similarity", {})
    result = similarity_engine.compare_trees(
        reference_path, implementation_path,
        lexical_threshold=thresholds.get("lexical_threshold", 0.15),
        structural_threshold=thresholds.get("structural_threshold", 0.15),
        negative_control_roots=list(negative_controls),
        max_comparisons=max_comparisons,
    )
    out_path = project.root / "evidence" / "similarity-findings.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(jsonlib.dumps(result["findings"], indent=2, sort_keys=True), encoding="utf-8")

    suspicious = [f for f in result["findings"] if f["classification"] in ("suspicious", "material")]
    if result["comparisons_skipped"]:
        ctx.echo(f"WARNING: {result['comparisons_skipped']} comparison(s) skipped (max_comparisons={max_comparisons}); not silently complete.")
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-similarity-engine"),
        action="cleanroom similarity",
        result="success" if not suspicious else "failure",
        detail=f"{result['comparisons_run']} comparison(s), {len(suspicious)} suspicious/material",
    )
    ctx.emit({**result, "saved_to": str(out_path)})
    if suspicious:
        sys.exit(int(ExitCode.SIMILARITY_FAILURE))


# --------------------------------------------------------------------------- provenance

@main.command()
@click.option(
    "--resolve-transitive", is_flag=True, default=False,
    help="Also resolve the real transitive dependency graph via PyPI/npm registry metadata (read-only network calls; never installs anything). Opt-in: off by default so this command stays offline unless asked.",
)
@pass_ctx
def provenance(ctx: Ctx, resolve_transitive: bool) -> None:
    """Parts XXXVII-XXXVIII: generate SPDX + CycloneDX SBOMs for Zone I."""
    project = ctx.load_project()
    deps = sbom_module.discover_dependencies(project.zone_i)
    out_dir = project.root / "evidence" / "sbom"

    result: dict[str, Any] = {"dependencies": len(deps)}
    detail = f"{len(deps)} declared dependencies"
    resolution = None
    if resolve_transitive:
        resolution = transitive_module.resolve_transitive(deps)
        transitive_path = out_dir / "transitive-dependencies.json"
        transitive_path.parent.mkdir(parents=True, exist_ok=True)
        transitive_path.write_text(jsonlib.dumps(resolution.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        result["transitive"] = {
            "resolved": len(resolution.resolved), "unresolved": len(resolution.unresolved),
            "path": str(transitive_path),
        }
        detail += f", {len(resolution.resolved)} transitive resolved, {len(resolution.unresolved)} unresolved"

    # When --resolve-transitive was requested, the SPDX/CycloneDX
    # documents include those resolved dependencies too (each nested
    # under its real parent, not flattened under the root) -- otherwise
    # they stay direct-deps-only, exactly as before this flag existed.
    spdx_doc = sbom_module.to_spdx(project.config.project_id, "0.0.0", deps, transitive=resolution)
    cdx_doc = sbom_module.to_cyclonedx(project.config.project_id, "0.0.0", deps, transitive=resolution)
    sbom_module.save(spdx_doc, out_dir / "sbom.spdx.json")
    sbom_module.save(cdx_doc, out_dir / "sbom.cyclonedx.json")
    result["spdx"] = str(out_dir / "sbom.spdx.json")
    result["cyclonedx"] = str(out_dir / "sbom.cyclonedx.json")

    project.evidence.append(actor=Actor(type="tool", id="cleanroom-sbom"), action="cleanroom provenance", zone="I", result="success", detail=detail)
    ctx.emit(result)


# --------------------------------------------------------------------------- audit

@main.command()
@pass_ctx
def audit(ctx: Ctx) -> None:
    """Combined technical audit: PathGuard self-test, agent/zone consistency,
    ledger integrity, and Zone H licence policy (Zone H must be C0-only AND
    every concluded licence there must be allowed by THIS project's actual
    policy, not a hardcoded list)."""
    project = ctx.load_project()
    isolation_ok, isolation_detail = run_pathguard_self_test(project.zone_r, project.zone_h, project.zone_i)
    ledger_problems = project.evidence.verify_chain()

    registry = AgentRegistry(project.root / "evidence")
    zone_consistency_problems = check_agent_zone_consistency(
        [a.to_dict() for a in registry.all()], project.evidence.read_all()
    )

    findings = licence_discovery.discover(project.zone_h)
    allowed = project.config.data.get("dependency_policy", {}).get("allowed_licences", [])
    denied = project.config.data.get("dependency_policy", {}).get("denied_licences", [])
    unknown_action = project.config.data.get("dependency_policy", {}).get("unknown_licence_action", "block")
    zone_h_results = []
    licence_blocking = False
    for finding in findings:
        policy_result = licence_policy.evaluate(finding.concluded, allowed=allowed, denied=denied)
        licence_blocking = licence_blocking or licence_policy.is_blocking(policy_result["status"], unknown_action)
        d = finding.to_dict()
        d["policy_result"] = policy_result
        zone_h_results.append(d)

    _, zone_h_skipped = hash_tree(project.zone_h)

    ok = isolation_ok and not ledger_problems and not zone_consistency_problems and not licence_blocking and not zone_h_skipped
    result = {
        "pathguard_self_test": {"passed": isolation_ok, "detail": isolation_detail},
        "agent_zone_consistency": {"ok": not zone_consistency_problems, "problems": zone_consistency_problems},
        "evidence_chain_intact": not ledger_problems,
        "evidence_chain_problems": ledger_problems,
        "zone_h_licence_findings": zone_h_results,
        "zone_h_licence_blocking": licence_blocking,
        "zone_h_unsafe_paths_skipped": zone_h_skipped,
    }
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-audit"), action="cleanroom audit", result="success" if ok else "failure")
    ctx.emit(result)
    if not isolation_ok or zone_h_skipped:
        sys.exit(int(ExitCode.CONTAMINATION_FAILURE))
    if licence_blocking:
        sys.exit(int(ExitCode.LICENCE_FAILURE))
    if ledger_problems or zone_consistency_problems:
        sys.exit(int(ExitCode.GENERAL_FAILURE))


# --------------------------------------------------------------------------- legal

@main.command()
@click.option("--access-authority", type=click.Choice(["public", "licensed", "contractual", "unknown"]), default="unknown")
@pass_ctx
def legal(ctx: Ctx, access_authority: str) -> None:
    """Part XLIV: run the heuristic legal issue engine. NOT LEGAL ADVICE."""
    project = ctx.load_project()
    licence_findings = [f.to_dict() for f in licence_discovery.discover(project.zone_r)]
    isolation_ok, _ = run_pathguard_self_test(project.zone_r, project.zone_h, project.zone_i)

    similarity_path = project.root / "evidence" / "similarity-findings.json"
    similarity_findings = jsonlib.loads(similarity_path.read_text(encoding="utf-8")) if similarity_path.is_file() else None

    graph = RequirementGraph.load(project.root / "requirements.json")
    requirement_classifications: dict[str, int] | None = None
    if graph.nodes:
        requirement_classifications = {}
        for node in graph.nodes.values():
            classification = node["classification"]
            requirement_classifications[classification] = requirement_classifications.get(classification, 0) + 1

    sanitise_events = [e for e in project.evidence.read_all() if e["action"] == "cleanroom sanitise"]
    sanitisation_blocked = any(e["result"] == "denied" for e in sanitise_events) if sanitise_events else None

    j = project.config.data["jurisdiction"]
    markets = j["required_markets"] + [m for m in j.get("informational_markets", []) if m not in j["required_markets"]]
    findings: list[dict[str, Any]] = []
    for market in markets or ["unspecified"]:
        pack_id = jurisdiction_resolver.COUNTRY_TO_PACK.get(market.lower())
        pack = jurisdiction_resolver.load_pack(pack_id) if pack_id else None
        bundle = legal_engine.CaseBundle(
            access_authority=access_authority,
            licence_findings=licence_findings,
            sanitisation_blocked=sanitisation_blocked,
            isolation_test_passed=isolation_ok,
            similarity_findings=similarity_findings,
            output_distribution_model=project.config.data.get("implementation", {}).get("distribution_model"),
            reference_licence_ids=[f.get("concluded") for f in licence_findings if f.get("concluded")],
            requirement_classifications=requirement_classifications,
            interoperability_permitted_acts=pack.get("interoperability_permitted_acts") if pack else None,
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


# --------------------------------------------------------------------------- judge-adjudicate

@main.command(name="judge-adjudicate")
@click.argument("pack_id")
@click.argument("answer_file", type=click.Path(exists=True, path_type=Path))
@click.option("--panel-member", "panel_member_id", required=True, help="Identifies this specific panel member's answer (e.g. 'member-1'), distinct from other members reviewing the same pack -- required so a second submission is recorded as an ADDITIONAL panel member's view, not silently overwriting the first.")
@click.option("--model-provider", default=None)
@click.option("--model-id", default=None)
@pass_ctx
def judge_adjudicate(ctx: Ctx, pack_id: str, answer_file: Path, panel_member_id: str, model_provider: str | None, model_id: str | None) -> None:
    """Parts XLV-LI, LIV: ingest one judicial-review panel member's completed
    answer to 'cleanroom judge's prompts for PACK_ID, and merge it back into
    the matching legal-finding records. ANSWER_FILE is a JSON list of
    {issue, decision_state, for_release_argument, against_release_argument,
    adjudication} objects, one per issue the panel member adjudicated.

    Supports panel_size > 1 (Part LIV, provider diversity): call this once
    per independent panel member reviewing the same pack, each with its own
    --panel-member id. Every finding's top-level decision_state (and the
    other panel-facing fields) always reflects the worst-wins aggregate
    across every panel member recorded so far for that finding -- a single
    dissenting RED/AMBER member is never smoothed over by others' more
    favourable view."""
    project = ctx.load_project()
    findings_path = project.root / "evidence" / "legal-findings.json"
    if not findings_path.is_file():
        raise click.ClickException("Run 'cleanroom legal' first.")
    findings = jsonlib.loads(findings_path.read_text(encoding="utf-8"))
    answers = jsonlib.loads(answer_file.read_text(encoding="utf-8"))

    markets_for_pack = {
        market for market, mapped_pack_id in jurisdiction_resolver.COUNTRY_TO_PACK.items() if mapped_pack_id == pack_id
    }
    if not markets_for_pack:
        raise click.ClickException(f"'{pack_id}' is not a known jurisdiction pack id (see jurisdiction/resolver.py's COUNTRY_TO_PACK).")

    now = utc_now_iso()
    updated_issues: list[str] = []
    for answer in answers:
        matched = False
        for finding in findings:
            if finding["issue"] != answer["issue"] or (finding.get("jurisdiction") or "").lower() not in markets_for_pack:
                continue
            matched = True
            entry = {
                "panel_member_id": panel_member_id,
                "decision_state": answer["decision_state"],
                "reviewer": f"simulated-{pack_id}-judicial-panel",
                "submitted_utc": now,
            }
            for key in ("for_release_argument", "against_release_argument", "adjudication"):
                if answer.get(key):
                    entry[key] = answer[key]
            if model_provider:
                entry["model_provider"] = model_provider
            if model_id:
                entry["model_id"] = model_id
            finding.setdefault("panel_adjudications", [])
            finding["panel_adjudications"] = [
                a for a in finding["panel_adjudications"] if a.get("panel_member_id") != panel_member_id
            ] + [entry]

            worst_state = legal_panels.aggregate_panel_decision(finding["panel_adjudications"])
            worst_entry = max(
                finding["panel_adjudications"],
                key=lambda a: legal_panels.DECISION_RANK.get(a["decision_state"], 2),
            )
            finding["decision_state"] = worst_state
            finding["reviewer"] = worst_entry["reviewer"]
            for key in ("for_release_argument", "against_release_argument", "adjudication"):
                if worst_entry.get(key):
                    finding[key] = worst_entry[key]
            updated_issues.append(answer["issue"])
        if not matched:
            raise click.ClickException(
                f"No legal finding matches issue '{answer['issue']}' for pack '{pack_id}' (checked markets {sorted(markets_for_pack)}) -- run 'cleanroom legal' with this project's actual configured markets first."
            )

    for finding in findings:
        errors = schema_registry.validate(finding, "legal-finding.schema.json")
        if errors:
            raise click.ClickException(f"Refusing to save: adjudicated finding fails schema validation: {errors}")

    findings_path.write_text(jsonlib.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")

    providers_config = project.config.data.get("providers", {})
    panel_size_required = providers_config.get("panel_size", 1)
    diversity_required = providers_config.get("panel_diversity_required", False)
    member_ids = {a["panel_member_id"] for f in findings for a in f.get("panel_adjudications", []) if f["issue"] in updated_issues}
    providers_seen = {
        a.get("model_provider") for f in findings for a in f.get("panel_adjudications", []) if f["issue"] in updated_issues
    } - {None}
    diversity_satisfied = (not diversity_required) or len(providers_seen) > 1

    project.evidence.append(
        actor=Actor(type="human", id=panel_member_id, role="judicial-panel-member", model_provider=model_provider, model_id=model_id),
        action="cleanroom judge-adjudicate", result="success",
        detail=f"pack={pack_id} panel_member={panel_member_id} issues={updated_issues}",
    )
    ctx.emit({
        "pack_id": pack_id, "panel_member_id": panel_member_id, "issues_updated": updated_issues,
        "panel_completeness": {
            "panel_size_required": panel_size_required, "panel_members_recorded": len(member_ids),
            "panel_size_satisfied": len(member_ids) >= panel_size_required,
            "diversity_required": diversity_required, "distinct_providers_recorded": sorted(p for p in providers_seen if p),
            "diversity_satisfied": diversity_satisfied,
        },
    })


# --------------------------------------------------------------------------- remediate

@main.command()
@click.option("--override", "override_id", default=None, help="Mark a specific open task resolved by human sign-off instead of a clean re-scan (Part LI).")
@click.option("--by", "override_by", default=None, help="Required with --override: who is accepting this residual risk.")
@click.option("--notes", "override_notes", default=None, help="Required with --override: why.")
@pass_ctx
def remediate(ctx: Ctx, override_id: str | None, override_by: str | None, override_notes: str | None) -> None:
    """Routes RED legal findings and suspicious/material similarity findings
    back to the implementation team as blocking requirement-graph nodes.
    Idempotent: re-running after a fix clears the task automatically; a
    fix that was never made stays open and blocks 'cleanroom release'."""
    project = ctx.load_project()
    tasks_path = project.root / "REMEDIATION_TASKS.json"
    existing_tasks = jsonlib.loads(tasks_path.read_text(encoding="utf-8")) if tasks_path.is_file() else []

    legal_path = project.root / "evidence" / "legal-findings.json"
    similarity_path = project.root / "evidence" / "similarity-findings.json"
    legal_findings = jsonlib.loads(legal_path.read_text(encoding="utf-8")) if legal_path.is_file() else []
    similarity_findings = jsonlib.loads(similarity_path.read_text(encoding="utf-8")) if similarity_path.is_file() else []

    if override_id:
        if not override_by or not override_notes:
            raise click.ClickException("--override requires both --by and --notes.")
        try:
            existing_tasks = remediation_module.apply_override(existing_tasks, override_id, by=override_by, notes=override_notes)
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    tasks = remediation_module.reconcile(existing_tasks, legal_findings, similarity_findings)
    tasks_path.write_text(jsonlib.dumps(tasks, indent=2, sort_keys=True), encoding="utf-8")

    graph_path = project.root / "requirements.json"
    graph = RequirementGraph.load(graph_path)
    for task in tasks:
        node_id = task["id"]
        if task["status"] == "open":
            graph.add({
                "id": node_id, "kind": "remediation",
                "statement": task["description"],
                "classification": "source_implementation_detail",
                "status": "blocked",
                "blocker": {
                    "reason": task["description"],
                    "responsible_component": task["assigned_to"],
                    "next_required_action": (
                        "Re-implement to address the finding, then re-run 'cleanroom legal'/'cleanroom similarity' "
                        "and 'cleanroom remediate' -- or obtain an explicit human override."
                    ),
                },
            })
        elif node_id in graph.nodes:
            graph.nodes[node_id]["status"] = "implemented"
            graph.nodes[node_id].pop("blocker", None)
    graph.save(graph_path)

    blocking_open = remediation_module.open_blocking_tasks(tasks)
    project.evidence.append(
        actor=Actor(type="human" if override_id else "tool", id=override_by or "cleanroom-remediate"),
        action="cleanroom remediate" + (f" --override {override_id}" if override_id else ""),
        result="denied" if blocking_open else "success",
        detail=f"{len(tasks)} task(s), {len(blocking_open)} open blocking",
    )
    ctx.emit({"tasks": tasks, "open_blocking": len(blocking_open), "saved_to": str(tasks_path)})
    if blocking_open and not override_id:
        ctx.fail(PolicyFailure(f"{len(blocking_open)} blocking remediation task(s) remain open; see {tasks_path}"))


# --------------------------------------------------------------------------- verify

@main.command()
@click.option(
    "--export-in-toto-links", is_flag=True, default=False,
    help="Also export every evidence-ledger event as an in-toto Link-predicate Statement to evidence/in-toto-links/. Structural mapping only, NOT a signed attestation, unless --signer is also given (see provenance/intoto.py).",
)
@click.option(
    "--signer", "gpg_key_id", default=None,
    help="GPG key id to really sign each exported in-toto Statement with (same mechanism as 'cleanroom handoff --signer'). Requires --export-in-toto-links. Never fabricates a signature if gpg or the key isn't available -- falls back to unsigned.",
)
@pass_ctx
def verify(ctx: Ctx, export_in_toto_links: bool, gpg_key_id: str | None) -> None:
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
    result: dict[str, Any] = {"ledger_intact": not ledger_problems, "ledger_problems": ledger_problems, "handoff_manifest_intact": not manifest_problems, "handoff_manifest_problems": manifest_problems}

    if export_in_toto_links:
        events = project.evidence.read_all()
        statements = intoto_module.export_ledger_to_link_statements(events, gpg_key_id=gpg_key_id)
        out_dir = project.root / "evidence" / "in-toto-links"
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for event, statement in zip(events, statements):
            action_slug = re.sub(r"[^A-Za-z0-9]+", "-", event["action"]).strip("-").lower()
            out_path = out_dir / f"{event['sequence']:06d}-{action_slug}.link.json"
            out_path.write_text(jsonlib.dumps(statement, indent=2, sort_keys=True), encoding="utf-8")
            written.append(str(out_path))
        signed_count = sum(1 for s in statements if not s["unsigned"])
        result["in_toto_links"] = {
            "count": len(written), "directory": str(out_dir),
            "signed_count": signed_count, "unsigned_count": len(statements) - signed_count,
        }

    ctx.emit(result)
    if not ok:
        sys.exit(int(ExitCode.GENERAL_FAILURE))


# --------------------------------------------------------------------------- report / release / status

_PHASE_LABELS = {
    "cleanroom init": "Init", "cleanroom intake": "Intake", "cleanroom inspect": "Inspect",
    "cleanroom licence": "Licence discovery", "cleanroom jurisdiction": "Jurisdiction resolution",
    "cleanroom analyse": "Analysis", "specify add-requirement": "Specification",
    "specify add-behavioral": "Specification", "cleanroom sanitise": "Sanitisation",
    "cleanroom handoff": "Handoff", "cleanroom architect": "Architecture",
    "cleanroom build (agent registered)": "Implementation build", "cleanroom test": "Testing",
    "cleanroom similarity": "Similarity analysis", "cleanroom provenance": "Provenance/SBOM",
    "cleanroom audit": "Audit", "cleanroom legal": "Legal triage", "cleanroom judge": "Judicial review prompts",
    "cleanroom remediate": "Remediation", "cleanroom report": "Reporting", "cleanroom release": "Release",
}


def _phases_completed(events: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for event in events:
        action = event.get("action", "")
        matched = next((label for prefix, label in _PHASE_LABELS.items() if action.startswith(prefix)), None)
        if matched and matched not in seen:
            seen.append(matched)
    return seen


@main.command()
@click.option("--version", "version", default="0.0.0")
@click.option("--html", "emit_html", is_flag=True, default=False, help="Also write CLEAN_ROOM_REPORT.html (colour-coded, self-contained).")
@click.option("--pdf", "emit_pdf", is_flag=True, default=False, help="Also write CLEAN_ROOM_REPORT.pdf (requires: pip install 'cleanroom[pdf]').")
@pass_ctx
def report(ctx: Ctx, version: str, emit_html: bool, emit_pdf: bool) -> None:
    """Part XCIII: assemble the final report -- what the project started
    with, what it did, functional/provenance/similarity status, remediation
    (findings sent back to the implementation team), jurisdictions, and the
    global decision. Writes CLEAN_ROOM_CERTIFICATE.json + CLEAN_ROOM_REPORT.md
    always; --html/--pdf add colour-coded renderings of the same data."""
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

    similarity_path = project.root / "evidence" / "similarity-findings.json"
    if similarity_path.is_file():
        sim_findings = jsonlib.loads(similarity_path.read_text(encoding="utf-8"))
        unresolved = [f for f in sim_findings if f["classification"] in ("suspicious", "material")]
        similarity_result = "material_findings_open" if unresolved else "no_material_findings"
    else:
        similarity_result = "not_run"

    tasks_path = project.root / "REMEDIATION_TASKS.json"
    tasks = jsonlib.loads(tasks_path.read_text(encoding="utf-8")) if tasks_path.is_file() else []
    remediation_summary = {
        "open_blocking": sum(1 for t in tasks if t["status"] == "open" and t["severity"] == "blocking"),
        "open_review_required": sum(1 for t in tasks if t["status"] == "open" and t["severity"] == "review_required"),
        "resolved_by_rescan": sum(1 for t in tasks if t["status"] == "resolved_by_rescan"),
        "resolved_by_override": sum(1 for t in tasks if t["status"] == "resolved_by_override"),
    }

    impl_config = project.config.data.get("implementation", {})
    ref_config = project.config.data.get("reference", {})
    ref_repos = [r.get("url", "") for r in ref_config.get("repositories", [])]
    project_summary = {
        "reference_summary": "; ".join(ref_repos) if ref_repos else "(not recorded in .cleanroom.yml reference.repositories)",
        "intended_output_licence": impl_config.get("output_licence", "(not recorded)"),
        "distribution_model": impl_config.get("distribution_model", []),
        "target_markets": sorted(set(required_markets) | set(project.config.data.get("jurisdiction", {}).get("informational_markets", []))),
    }

    outstanding = [b["statement"] for b in graph.blockers()]

    certificate = build_certificate(
        project=project.config.data["project"]["name"],
        version=version,
        reference=(ref_repos[0] if ref_repos else None),
        clean_room_level=project.config.clean_room_level,
        tests=tests_summary,
        requirement_traceability_percent=trace.get("completion_percent", 0.0),
        provenance_status="partial" if (project.root / "evidence" / "sbom").is_dir() else "unknown",
        similarity_result=similarity_result,
        jurisdictions=[{"jurisdiction": j, "decision_state": s, "required_market": j in required_markets} for j, s in jurisdiction_decisions.items()],
        global_decision=global_decision,
        outstanding_issues=outstanding,
        evidence_bundle_location=str(project.root / "evidence"),
        remediation=remediation_summary,
        project_summary=project_summary,
        phases_completed=_phases_completed(project.evidence.read_all()),
    )
    save_certificate(certificate, project.root / "CLEAN_ROOM_CERTIFICATE.json")
    report_text = render_final_report(certificate)
    (project.root / "CLEAN_ROOM_REPORT.md").write_text(report_text, encoding="utf-8")

    written = {"markdown": str(project.root / "CLEAN_ROOM_REPORT.md"), "certificate": str(project.root / "CLEAN_ROOM_CERTIFICATE.json")}
    if emit_html:
        html_path = project.root / "CLEAN_ROOM_REPORT.html"
        html_path.write_text(render_html_report(certificate), encoding="utf-8")
        written["html"] = str(html_path)
    if emit_pdf:
        try:
            from cleanroom.report_pdf import render_pdf_report
        except ImportError as e:
            raise click.ClickException(str(e)) from e
        pdf_path = render_pdf_report(certificate, project.root / "CLEAN_ROOM_REPORT.pdf")
        written["pdf"] = str(pdf_path)

    project.evidence.append(actor=Actor(type="tool", id="cleanroom-report"), action="cleanroom report", result="success", detail=f"outputs={list(written)}")
    ctx.emit({**certificate, "outputs": written}, human=report_text)


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

    isolation_ok, _ = run_pathguard_self_test(project.zone_r, project.zone_h, project.zone_i)
    ledger_ok = not project.evidence.verify_chain()
    tasks_path = project.root / "REMEDIATION_TASKS.json"
    tasks = jsonlib.loads(tasks_path.read_text(encoding="utf-8")) if tasks_path.is_file() else []
    open_blocking_remediation = len(remediation_module.open_blocking_tasks(tasks))

    allowed, reasons = release_allowed(
        technical_gate=certificate["tests"].get("fail", 0) == 0,
        provenance_gate=certificate["provenance_status"] != "unknown",
        contamination_gate=isolation_ok and ledger_ok,
        global_decision=certificate["global_decision"],
        require_technical_gate=policy["require_technical_gate"],
        require_provenance_gate=policy["require_provenance_gate"],
        require_contamination_gate=policy["require_contamination_gate"],
        block_on_red_required_jurisdiction=policy["block_on_red_required_jurisdiction"],
        open_blocking_remediation=open_blocking_remediation,
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
        "computed_maturity": maturity.compute_level(project),
        "zones": {"R": str(project.zone_r), "H": str(project.zone_h), "I": str(project.zone_i)},
        "requirement_traceability": graph.traceability_report(),
        "agents": [a.to_dict() for a in registry.all()],
        "orphaned_agents": [a.agent_id for a in registry.orphaned()],
        "ledger_events": len(project.evidence.read_all()),
    })


# --------------------------------------------------------------------------- benchmark

@main.command()
@click.option("--threshold", type=float, default=0.15, help="Structural-similarity classification threshold to benchmark against.")
@click.option("--markdown", "markdown_path", type=click.Path(path_type=Path), default=None, help="Also write a Markdown report to this path.")
@pass_ctx
def benchmark(ctx: Ctx, threshold: float, markdown_path: Path | None) -> None:
    """Parts LXXVI-LXXVII: measured precision/recall for the similarity
    engine against this project's own small, hand-built, synthetic
    ground-truth corpus (tests/fixtures/benchmark/). Does not operate on
    a .cleanroom.yml project -- this benchmarks the tool itself, like
    'cleanroom doctor'."""
    fixtures_dir = benchmark_module.default_fixtures_dir()
    if fixtures_dir is None:
        raise click.ClickException(
            "Could not find tests/fixtures/benchmark/ -- this command only works from a git checkout "
            "of the clean-room-coding repository, not a bare 'pip install cleanroom'."
        )
    report = benchmark_module.run_benchmark(fixtures_dir, threshold=threshold)
    if markdown_path:
        markdown_path.write_text(benchmark_module.render_markdown(report), encoding="utf-8")
        report["markdown_written_to"] = str(markdown_path)
    ctx.emit(report)


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
