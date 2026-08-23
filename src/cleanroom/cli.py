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
from cleanroom import coverage as coverage_module
from cleanroom.evidence import Actor
from cleanroom.exit_codes import (
    CleanRoomError,
    ContaminationFailure,
    ExitCode,
    LegalRed,
    LicenceFailure,
    ManualReviewRequired,
    PolicyFailure,
)
from cleanroom import gate as gate_module
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
from cleanroom import reference_diff as reference_diff_module
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
        """Part V-VII: the real per-invocation `PathGuard` gate. Historically
        this was a no-op unless the caller opted in with `--agent-id` --
        which meant an orchestrator that simply forgot the flag got silent,
        unrestricted access with no warning, on a tool whose entire value
        proposition is provable separation. That footgun is now closed: once
        this PROJECT has at least one registered Zone-I (implementation)
        agent -- i.e. `cleanroom build`/`cleanroom implement` has run at
        least once, per `AgentRegistry.has_registered_implementation_agent`
        -- every zone-scoped command REQUIRES a valid `--agent-id` and fails
        closed if it's omitted. A project with no implementation agent yet
        (initial `init`/`recruit`/pre-build analysis, before any
        Reference/Implementation separation exists to protect) keeps
        behaving exactly as before: `--agent-id` is optional and omitting it
        is a no-op. The caller is responsible for calling this before it
        actually reads `path`, not after."""
        registry = AgentRegistry(project.root / "evidence")
        if self.agent_id is None:
            if registry.has_registered_implementation_agent():
                raise click.ClickException(
                    "--agent-id is required: this project has at least one registered "
                    "implementation agent (via 'cleanroom build'), so zone-scoped commands "
                    "no longer run ungated. Pass the global --agent-id <id> of the agent this "
                    "invocation is acting on behalf of (see 'cleanroom status' or the evidence "
                    "ledger's agents.json for registered agent ids)."
                )
            return
        record = next((a for a in registry.all() if a.agent_id == self.agent_id), None)
        if record is None:
            raise click.ClickException(f"No agent registered with id '{self.agent_id}' (register one with 'cleanroom build' or 'cleanroom recruit' first).")
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
    help="A 'cleanroom build'/'cleanroom recruit'-registered agent id this invocation is acting on behalf of. When given, commands that read Zone R/H/I gate that read through a real per-invocation PathGuard.check() against that agent's actual registered scope (Part V-VII). Once this project has at least one registered implementation agent (i.e. 'cleanroom build' has run at least once), --agent-id becomes REQUIRED for every zone-scoped command (inspect/licence/similarity/sanitise/diff-reference) -- omitting it then fails closed with a clear error, rather than silently running ungated. Before any implementation agent has been registered for this project (initial init/recruit/pre-build analysis), --agent-id remains optional and omitting it behaves exactly as before (no gating). This is how an orchestration harness that knows which agent it just spawned gets real enforcement, not just the isolation self-test.",
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
    ctx.enforce_zone_access(project, path)
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


# --------------------------------------------------------------------------- gate

@main.command()
@click.option("--specification-version", required=True)
@click.option("--decision", type=click.Choice(["pass", "fail"]), required=True)
@click.option("--reviewer", required=True, help="The human making this call. Never a tool/agent id -- the automated signal below is evidence for them, not itself an actor.")
@click.option("--notes", required=True)
@click.option(
    "--acknowledge-automated-signal/--no-acknowledge-automated-signal", default=None,
    help="Required (interactively prompted if omitted, in a terminal) to record --decision pass when the automated sufficiency/cleanliness signal reads 'insufficient'.",
)
@pass_ctx
def gate(
    ctx: Ctx, specification_version: str, decision: str, reviewer: str, notes: str,
    acknowledge_automated_signal: bool | None,
) -> None:
    """Part XCIV: the Clean-Room Gate -- a recorded, evidence-backed PASS/FAIL
    decision on whether the specification is sufficient for independent
    implementation and free of restricted material. `cleanroom handoff`
    refuses to build a manifest for a specification version without a
    matching PASS recorded here. The automated signal is real, derived
    evidence (requirement-graph coverage + sanitisation-report cleanliness)
    -- never itself the decision; the human --decision is authoritative,
    and overriding an 'insufficient' signal to PASS requires an explicit
    acknowledgement, recorded as such rather than conflated with a
    genuinely sufficient specification. See references/clean-room-gate.md.

    Also surfaces (never blocks on) whether 'cleanroom coverage' -- the
    capability-regression check for whether Zone I still references
    everything the pre-migration code actually used -- has been run for
    this project. Deliberately advisory, not folded into
    automated_signal/GATE_DECISIONS.json's schema: unlike the requirement-
    graph/sanitisation checks, coverage needs a legacy-usage-code path
    this command has no way to discover on its own, and a real project
    may legitimately have no pre-migration usage code to compare against
    (e.g. a from-scratch clean-room build). Making it mandatory here
    would either force an irrelevant flag on every gate call or require
    guessing a path -- both worse than an honest, always-visible nudge."""
    project = ctx.load_project()
    graph = RequirementGraph.load(project.root / "requirements.json")
    signal = gate_module.compute_signal(graph, project.root / "evidence" / "sanitisation-reports")

    coverage_path = project.root / "evidence" / "coverage-findings.json"
    if coverage_path.is_file():
        coverage_findings = jsonlib.loads(coverage_path.read_text(encoding="utf-8"))
        coverage_advisory = {
            "run": True,
            "open_review_required": sum(1 for f in coverage_findings if f.get("requires_review")),
        }
    else:
        coverage_advisory = {"run": False, "open_review_required": None}
    if not ctx.json_output:
        if not coverage_advisory["run"]:
            click.echo(
                "\nNote: 'cleanroom coverage' has not been run for this project -- it checks whether the Zone I "
                "implementation still references every field/usage the pre-migration code actually used (a real "
                "prior bug class; see 'cleanroom coverage --help'). Not required to gate, but recommended "
                "before release."
            )
        elif coverage_advisory["open_review_required"]:
            click.echo(
                f"\nNote: 'cleanroom coverage' has {coverage_advisory['open_review_required']} open "
                "review-required finding(s) in evidence/coverage-findings.json -- not required to gate, but "
                "recommended to resolve or explicitly accept before release."
            )

    overriding = decision == "pass" and signal["automated_signal"] == "insufficient"
    if overriding:
        if acknowledge_automated_signal is None and not ctx.json_output:
            click.echo(f"\nAutomated signal reads INSUFFICIENT for specification version {specification_version}:")
            click.echo(f"  handoff-eligible requirement nodes: {signal['sufficiency']['handoff_eligible_nodes']}")
            if signal["blocking_sanitisation_reports"]:
                click.echo(f"  blocking sanitisation reports: {', '.join(signal['blocking_sanitisation_reports'])}")
            try:
                acknowledge_automated_signal = click.confirm(
                    "\nRecord a PASS decision anyway? This is saved as an explicit override, not a clean pass.",
                    default=False,
                )
            except click.Abort:
                acknowledge_automated_signal = False
        if not acknowledge_automated_signal:
            raise click.ClickException(
                "Automated signal is insufficient (see above) and --decision is 'pass' -- resolve the gap in "
                "the specification, pass --decision fail instead, or pass --acknowledge-automated-signal to "
                "record an explicit human override."
            )

    decisions_path = project.root / gate_module.DECISIONS_FILENAME
    decisions = gate_module.load_decisions(decisions_path)
    record = gate_module.build_decision(
        project_id=project.config.project_id, specification_version=specification_version,
        decision=decision, reviewer=reviewer, notes=notes, signal=signal, sequence=len(decisions) + 1,
    )
    decisions.append(record)
    gate_module.save_decisions(decisions_path, decisions)

    project.evidence.append(
        actor=Actor(type="human", id=reviewer, role="clean-room-gate-reviewer"),
        action="cleanroom gate",
        result="success" if decision == "pass" else "denied",
        detail=(
            f"specification_version={specification_version} decision={decision} "
            f"automated_signal={signal['automated_signal']} overrode={record['overrode_automated_signal']}"
        ),
    )
    ctx.emit({**record, "saved_to": str(decisions_path), "coverage_advisory": coverage_advisory})
    if decision == "fail":
        ctx.fail(PolicyFailure(
            f"Clean-Room Gate FAIL recorded for specification version {specification_version} ({decisions_path}) -- "
            "return the findings to Team A and re-run analyse/specify/sanitise before gating this version again."
        ))


# --------------------------------------------------------------------------- handoff

@main.command()
@click.option("--specification-version", required=True)
@click.option("--all-c0", is_flag=True, default=False, help="Classify every file currently in Zone H as C0 (only use once sanitisation is complete).")
@click.option("--signer", default=None)
@click.option(
    "--format", "output_format", type=click.Choice(["markdown", "facts-json", "both"]), default="markdown",
    help=(
        "Which handoff document(s) to produce. 'markdown' (default, unchanged behaviour): only the free-form "
        "CLEAN_ROOM_HANDOFF.md. 'facts-json': in place of the Markdown doc, validate --facts-file against "
        "schemas/handoff-facts.schema.json and write it into Zone H as CLEAN_ROOM_HANDOFF_FACTS.json -- for the "
        "common 'wire-format facts' case (protocol/schema clean-room work) where a handoff should mechanically "
        "provably contain ONLY bare facts (field names/numbers/types), not prose or structure leaked from the "
        "reference. This does not replace the free-form option for clean-room work that genuinely needs prose; "
        "it is an additional, stricter option. 'both' writes both documents. Requires --facts-file when the "
        "chosen format includes facts-json."
    ),
)
@click.option(
    "--facts-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
    help="Path to a candidate facts-only handoff document (JSON) to validate against schemas/handoff-facts.schema.json. Required when --format is 'facts-json' or 'both'.",
)
@pass_ctx
def handoff(ctx: Ctx, specification_version: str, all_c0: bool, signer: str | None, output_format: str, facts_file: Path | None) -> None:
    """Parts XXIV-XXV, XCIV: build the immutable, hashed HANDOFF_MANIFEST.json
    -- refuses to run without a PASS Clean-Room Gate decision already
    recorded for this exact specification version (see 'cleanroom gate')."""
    if output_format in ("facts-json", "both") and facts_file is None:
        raise click.ClickException(f"--format {output_format} requires --facts-file <path to a candidate facts document>.")

    facts_data: dict[str, Any] | None = None
    if facts_file is not None:
        try:
            facts_data = jsonlib.loads(facts_file.read_text(encoding="utf-8"))
        except jsonlib.JSONDecodeError as e:
            raise click.ClickException(f"--facts-file {facts_file} is not valid JSON: {e}") from e
        facts_errors = handoff_manifest.validate_facts_document(facts_data)
        if facts_errors:
            raise click.ClickException(
                f"--facts-file {facts_file} does not conform to schemas/handoff-facts.schema.json "
                f"({len(facts_errors)} problem(s)):\n" + "\n".join(f"  - {e}" for e in facts_errors)
            )

    project = ctx.load_project()
    decisions = gate_module.load_decisions(project.root / gate_module.DECISIONS_FILENAME)
    latest = gate_module.latest_decision(decisions, specification_version)
    if latest is None or latest["decision"] != "pass":
        state = "no Clean-Room Gate decision recorded" if latest is None else f"latest Clean-Room Gate decision is '{latest['decision']}'"
        project.evidence.append(
            actor=Actor(type="tool", id="cleanroom-cli"),
            action="cleanroom handoff",
            zone="H",
            result="denied",
            detail=f"specification_version={specification_version}: {state}",
        )
        ctx.fail(PolicyFailure(
            f"Refusing to build a handoff manifest for specification version {specification_version}: {state}. "
            f"Run 'cleanroom gate --specification-version {specification_version} --decision pass ...' first."
        ))
        return
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

    # facts_data was already validated above (fail-fast, before touching
    # Zone H) -- writing it here just persists the already-conforming
    # document so its hash can be recorded in the manifest.
    facts_document_ref: dict[str, str] | None = None
    if facts_data is not None:
        from cleanroom.util import sha256_file
        facts_path = handoff_manifest.write_facts_doc(facts_data, project.zone_h)
        facts_document_ref = {
            "path": facts_path.relative_to(project.zone_h).as_posix(),
            "sha256": sha256_file(facts_path),
        }

    try:
        m = handoff_manifest.build_manifest(
            project_id=project.config.project_id,
            specification_version=specification_version,
            zone_h=project.zone_h,
            file_contamination=file_contamination,
            sanitisation_report_hash=sanitisation_reports_hash,
            signer=signer,
            facts_document=facts_document_ref,
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
    doc_path = handoff_manifest.write_handoff_doc(m, project.zone_h) if output_format in ("markdown", "both") else None
    project.evidence.append(
        actor=Actor(type="human" if signer else "tool", id=signer or "cleanroom-cli"),
        action="cleanroom handoff",
        zone="H",
        result="success",
        outputs=[{"path": str(manifest_path), "sha256": m["manifest_hash"]}],
        detail=f"{len(m['files'])} file(s) in handoff bundle, format={output_format}"
        + (f", facts_document={facts_document_ref['path']}" if facts_document_ref else ""),
    )
    ctx.emit({
        "manifest": str(manifest_path),
        "doc": str(doc_path) if doc_path else None,
        "facts_doc": str(project.zone_h / handoff_manifest.FACTS_DOC_FILENAME) if facts_document_ref else None,
        "manifest_hash": m["manifest_hash"],
    })


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
@click.option("--tool", "tools", multiple=True, help="A tool/capability this agent has access to (e.g. 'pytest', 'ast-grep'). Repeatable. Purely a record of what this agent instance was actually equipped with -- registering a tool here does not itself grant zone access or any runtime permission.")
@click.option("--model-provider", default=None)
@click.option("--model-id", default=None)
@click.option(
    "--acknowledge-open-concerns/--no-acknowledge-open-concerns", "acknowledge_open_concerns", default=None,
    help="Skip the interactive panel for open AMBER/RED remediation concerns (for CI/non-interactive use). "
    "--acknowledge-open-concerns proceeds despite them; --no-acknowledge-open-concerns refuses without prompting.",
)
@pass_ctx
def build(
    ctx: Ctx, role: str, tools: tuple[str, ...], model_provider: str | None, model_id: str | None,
    acknowledge_open_concerns: bool | None,
) -> None:
    """Part XXVI: register a fresh, source-blind implementation agent scoped
    to Zone H + Zone I only. Before doing so, re-derives REMEDIATION_TASKS.json
    from whatever legal/similarity findings currently exist (see
    'cleanroom remediate') -- an AMBER or RED concern is never silently
    left behind for the implementation team to discover on its own; it is
    always passed over as a real, assigned task before this command lets
    implementation start. A BLOCKING concern (a RED legal finding, or a
    material similarity finding) refuses to proceed without an explicit
    human decision, interactively or via --acknowledge-open-concerns; a
    review_required concern (AMBER/UNKNOWN, or a suspicious similarity
    finding) is surfaced but never blocks on its own, matching how every
    other gate in this project treats AMBER."""
    project = ctx.load_project()

    tasks_path = project.root / "REMEDIATION_TASKS.json"
    existing_tasks = jsonlib.loads(tasks_path.read_text(encoding="utf-8")) if tasks_path.is_file() else []
    tasks = _reconcile_and_sync_remediation(project, existing_tasks)
    open_blocking = remediation_module.open_blocking_tasks(tasks)
    open_review_required = [t for t in tasks if t["status"] == "open" and t["severity"] == "review_required"]

    if open_blocking or open_review_required:
        if acknowledge_open_concerns is None and not ctx.json_output:
            click.echo(f"\n{len(open_blocking)} BLOCKING and {len(open_review_required)} review-required concern(s) are open:")
            for task in open_blocking + open_review_required:
                click.echo(f"  [{task['severity']}] {task['id']}: {task['description']}")
            try:
                acknowledge_open_concerns = click.confirm(
                    "\nThese remain assigned to the implementation team (REMEDIATION_TASKS.json) and blocking ones "
                    "will still block 'cleanroom release' until resolved or overridden. Proceed with registering "
                    "this implementation agent anyway?",
                    default=False,
                )
            except click.Abort:
                # No interactive terminal to answer from (e.g. stdin closed
                # in a script/CI context that forgot --acknowledge-open-concerns)
                # -- fail closed with a clear message, never a raw traceback.
                acknowledge_open_concerns = False
        if open_blocking and not acknowledge_open_concerns:
            raise click.ClickException(
                f"{len(open_blocking)} blocking remediation concern(s) are open (see {tasks_path}) -- resolve "
                "them, obtain an override via 'cleanroom remediate --override', or pass "
                "--acknowledge-open-concerns to proceed anyway."
            )

    registry = AgentRegistry(project.root / "evidence")
    record = registry.register(
        role=role,
        permitted_zones=["H", "I"],
        prohibited_paths=[str(project.zone_r)],
        tools=list(tools),
        model_provider=model_provider,
        model_id=model_id,
        supplied_documents=[str(p) for p in project.zone_h.rglob("*") if p.is_file()],
    )
    project.evidence.append(
        actor=Actor(type="agent", id=record.agent_id, role=role, model_provider=model_provider, model_id=model_id),
        action="cleanroom build (agent registered)",
        zone="I",
        detail=(
            f"open_blocking_concerns={len(open_blocking)} open_review_required_concerns={len(open_review_required)} "
            f"acknowledged={bool(acknowledge_open_concerns)}"
        ) if (open_blocking or open_review_required) else None,
        result="success",
    )
    ctx.emit({
        **record.to_dict(),
        "open_remediation_concerns": {"blocking": len(open_blocking), "review_required": len(open_review_required)},
    })


# --------------------------------------------------------------------------- implement

@main.command()
@click.option("--backend", type=click.Choice(["anthropic"]), default="anthropic", help="Which real LLM backend actually writes the implementation.")
@click.option("--model-id", default=None, help="Overrides the implementation team's default model (orchestration/backends.py::DEFAULT_IMPLEMENTATION_MODEL).")
@pass_ctx
def implement(ctx: Ctx, backend: str, model_id: str | None) -> None:
    """Real Part XXVI: the actual "hand it over to the team to do the
    build out" step. Requires the global --agent-id (an implementation
    agent already registered via `cleanroom build`, so it has already
    been through that command's remediation panel) and, for the
    'anthropic' backend, a real ANTHROPIC_API_KEY in the environment.
    Sends the registered agent Zone H's real sanitised documents and the
    requirement graph's real handoff-eligible statements -- NEVER
    anything from Zone R -- and writes whatever files a real model
    returns into Zone I. Source-blind by construction: the model is
    given nothing from the reference zone to have read in the first
    place, not merely blocked from re-reading it. Real, cost-incurring
    LLM API calls; never invoked implicitly by any other command."""
    if ctx.agent_id is None:
        raise click.ClickException("The global --agent-id is required (register an implementation agent first with 'cleanroom build').")
    project = ctx.load_project()
    registry = AgentRegistry(project.root / "evidence")
    record = next((a for a in registry.all() if a.agent_id == ctx.agent_id), None)
    if record is None:
        raise click.ClickException(f"No agent registered with id '{ctx.agent_id}' (register one with 'cleanroom build').")
    if "I" not in record.permitted_zones:
        raise click.ClickException(f"Agent '{ctx.agent_id}' (role={record.role}) is not Zone-I-scoped -- register an implementation agent with 'cleanroom build' first.")

    if backend == "anthropic":
        from cleanroom.orchestration.backends import DEFAULT_IMPLEMENTATION_MODEL, AnthropicBackend
        try:
            agent_backend = AnthropicBackend(model=model_id or DEFAULT_IMPLEMENTATION_MODEL)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
        actual_model_provider = "anthropic"
    else:  # pragma: no cover -- click.Choice already restricts this
        raise click.ClickException(f"Unknown backend '{backend}'.")

    from cleanroom.orchestration.harness import HarnessError, run_implementation
    try:
        result = run_implementation(project, agent_backend, agent_id=ctx.agent_id)
    except (HarnessError, RuntimeError) as e:
        raise click.ClickException(str(e)) from e

    # Record the model that ACTUALLY did the work (agent_backend.model,
    # resolved above from --model-id or the role's real default) --
    # never `record.model_provider`/`record.model_id`, which reflect
    # whatever (if anything) `cleanroom build` happened to be given and
    # can be None even though a real model just wrote real code.
    project.evidence.append(
        actor=Actor(type="agent", id=ctx.agent_id, role=record.role, model_provider=actual_model_provider, model_id=agent_backend.model),
        action="cleanroom implement", zone="I", result="success",
        detail=f"files_written={result['files_written']}",
    )
    ctx.emit({**result, "model_provider": actual_model_provider, "model_id": agent_backend.model})


# --------------------------------------------------------------------------- recruit

@main.command()
@click.option("--role", required=True, help="e.g. 'Analyst', 'Reference Reviewer'.")
@click.option("--tool", "tools", multiple=True, help="A tool/capability this agent has access to. Repeatable. Purely a record of what this agent instance was actually equipped with -- registering a tool here does not itself grant zone access or any runtime permission.")
@click.option("--model-provider", default=None)
@click.option("--model-id", default=None)
@pass_ctx
def recruit(ctx: Ctx, role: str, tools: tuple[str, ...], model_provider: str | None, model_id: str | None) -> None:
    """Part VII/XXVI: register a fresh Reference-zone (Zone R only) agent --
    the counterpart to `cleanroom build`'s Zone H+I implementation agents.
    Before this command existed, `build` was the ONLY CLI path into
    `AgentRegistry`, so a Reference-side agent (an analyst reviewing Zone R
    material) could only be registered by calling `AgentRegistry` directly
    in Python -- there was no `cleanroom` command for the reference-side
    team at all. This closes that asymmetry."""
    project = ctx.load_project()
    registry = AgentRegistry(project.root / "evidence")
    record = registry.register(
        role=role,
        permitted_zones=["R"],
        prohibited_paths=[str(project.zone_h), str(project.zone_i)],
        tools=list(tools),
        model_provider=model_provider,
        model_id=model_id,
    )
    project.evidence.append(
        actor=Actor(type="agent", id=record.agent_id, role=role, model_provider=model_provider, model_id=model_id),
        action="cleanroom recruit (agent registered)",
        zone="R",
        result="success",
    )
    ctx.emit(record.to_dict())


# --------------------------------------------------------------------------- diff-reference

@main.command(name="diff-reference")
@click.option(
    "--check-zone-i-refs/--no-check-zone-i-refs", "check_zone_i_refs", default=True,
    help=(
        "Also search Zone H/I for files whose filename stem matches a changed reference file, as a "
        "best-effort (filename-only, no language parsing) signal of which handoff/implementation "
        "artifacts might now be stale relative to the updated reference. On by default; disable for a "
        "pure file-diff with no Zone H/I filesystem walk."
    ),
)
@click.option("--clone-timeout", type=int, default=300, help="Seconds allowed for the read-only re-clone of the reference source.")
@pass_ctx
def diff_reference(ctx: Ctx, check_zone_i_refs: bool, clone_timeout: int) -> None:
    """Re-fetch the SAME registered Zone R reference source and diff it
    against what was actually recruited into zone-r/ -- new/modified/deleted
    files, and (best-effort) which Zone H/I artifacts might now be stale.

    This closes a real gap: checking whether a recruited reference has newer
    upstream commits previously meant a human/agent manually re-cloning the
    source and hand-diffing it against zone-r/, with no evidence trail.
    'Same registered reference source' means the recruited checkout's own
    git 'origin' remote (see reference_diff.py's module docstring for why
    that, not a separate manifest, is the source of truth) -- a Zone R
    checkout that isn't a git clone with an origin remote is not supported,
    per the never-fabricate-a-conclusion rule (AGENTS.md item c): this
    refuses to guess an upstream rather than diffing against one.

    This is inherently a Zone-R-capable operation -- it reads the full
    content of zone-r/ to compute the baseline side of the diff -- so it is
    gated by the exact same opt-in `--agent-id` PathGuard check as
    `cleanroom inspect`/`licence`/`similarity`/`sanitise`; an agent not
    scoped for Zone R gets ZoneAccessDenied here exactly as it would from
    `cleanroom inspect zone-r`. The re-fetch itself never touches zone-r/ in
    place (no `git fetch`/`pull` against the recruited checkout) -- it
    clones into a throwaway temp directory that is removed before this
    command returns, so a recruited project's own files/state are
    unmodified by running this."""
    project = ctx.load_project()
    ctx.enforce_zone_access(project, project.zone_r)
    try:
        result = reference_diff_module.diff_reference(
            project.zone_r,
            zone_h=project.zone_h if check_zone_i_refs else None,
            zone_i=project.zone_i if check_zone_i_refs else None,
            clone_timeout=clone_timeout,
        )
    except reference_diff_module.ReferenceDiffError as e:
        raise click.ClickException(str(e)) from e

    stale = result["possibly_stale_refs"]
    changed_count = len(result["new_files"]) + len(result["modified_files"]) + len(result["deleted_files"])
    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-diff-reference"),
        action="cleanroom diff-reference",
        zone="R",
        result="success",
        detail=(
            f"source={result['reference_source']} baseline={result['baseline_commit']} "
            f"latest={result['latest_commit']} up_to_date={result['up_to_date']} "
            f"new={len(result['new_files'])} modified={len(result['modified_files'])} "
            f"deleted={len(result['deleted_files'])} "
            f"possibly_stale_zone_h={len(stale['zone_h'])} possibly_stale_zone_i={len(stale['zone_i'])}"
        ),
    )
    human_lines = [
        f"Reference source: {result['reference_source']}",
        f"Baseline commit:  {result['baseline_commit']}",
        f"Latest commit:    {result['latest_commit']}",
    ]
    if result["up_to_date"]:
        human_lines.append("Up to date -- no changes upstream since this reference was recruited.")
    else:
        human_lines.append(
            f"{changed_count} file(s) changed: {len(result['new_files'])} new, "
            f"{len(result['modified_files'])} modified, {len(result['deleted_files'])} deleted."
        )
        if stale["zone_h"] or stale["zone_i"]:
            human_lines.append(
                "Possibly-stale artifacts (filename match only, not authoritative): "
                f"{len(stale['zone_h'])} in Zone H, {len(stale['zone_i'])} in Zone I -- see 'possibly_stale_refs'."
            )
    ctx.emit(result, human="\n".join(human_lines))


# --------------------------------------------------------------------------- exclude-source / check-url

@main.command(name="exclude-source")
@click.argument("pattern")
@click.option("--note", default=None, help="Optional human-readable note recorded alongside this pattern (e.g. 'known fork on GitLab').")
@pass_ctx
def exclude_source(ctx: Ctx, pattern: str, note: str | None) -> None:
    """Part XCV: manually add a URL/pattern to this project's web-lookup
    exclusion list -- for a known mirror, fork, or rehost of the recruited
    Zone R reference that the automatic owner/repo heuristic (derived from
    Zone R's own git 'origin' remote, see webguard.py) doesn't identify on
    its own. PATTERN is matched later as a plain case-insensitive substring
    of any URL an orchestrating harness checks with `cleanroom check-url` /
    `webguard.check_url_against_exclusions` -- give it something specific
    (a host name, or a distinctive path fragment), not something so broad
    it would block unrelated documentation lookups."""
    project = ctx.load_project()
    from cleanroom.webguard import ExclusionStore
    store = ExclusionStore(project.root / "evidence")
    entry = store.add(pattern, note=note)
    project.evidence.append(
        actor=Actor(type="human", id="cleanroom-cli-user"),
        action="cleanroom exclude-source",
        zone="none",
        result="success",
        detail=f"pattern={entry.pattern}" + (f" note={note}" if note else ""),
    )
    ctx.emit(entry.to_dict(), human=f"Added manual exclusion: {entry.pattern}")


@main.command(name="check-url")
@click.argument("url")
@pass_ctx
def check_url(ctx: Ctx, url: str) -> None:
    """Part XCV: check URL against this project's web-lookup exclusion list
    (the recruited Zone R reference's own git origin, normalised into
    owner/repo + known-mirror variants, plus any `cleanroom exclude-source`
    additions) and report whether it should be blocked.

    This command is the CLI entry point an orchestrating harness is
    expected to call -- or the equivalent direct call to
    `cleanroom.webguard.check_url_against_exclusions` from Python -- BEFORE
    it lets an implementation-zone agent's web-fetch/web-search tool
    actually hit URL. See docs/web-lookup-guard.md for the full
    integration contract, including what to do on a blocked result. This
    command only decides; it has no ability to itself stop a fetch
    happening in some other process -- that boundary is deliberate, not an
    oversight (AGENTS.md item c: don't overclaim what a check function can
    enforce)."""
    project = ctx.load_project()
    from cleanroom.webguard import check_url_against_exclusions
    result = check_url_against_exclusions(url, project)
    human = (
        f"BLOCKED: {result['reason']}" if result["blocked"] else "ALLOWED: no exclusion match."
    )
    ctx.emit(result, human=human)
    if result["blocked"]:
        # Nonzero exit so a harness/CI script can gate on this directly
        # (`cleanroom check-url ... || refuse-the-fetch`) without parsing
        # --json output just to decide whether to proceed.
        sys.exit(int(ExitCode.POLICY_FAILURE))


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
        raise click.ClickException(f"No agent registered with id {agent_id}. Register one first with 'cleanroom build' or 'cleanroom recruit'.")

    evidence_dir = project.root / "evidence"
    heartbeat_module.append_tick(
        evidence_dir, agent_id,
        heartbeat_module.Tick(action_signature=action_signature, files_modified=files_modified, test_result=test_result, timestamp=utc_now_iso()),
    )
    ticks = heartbeat_module.load_ticks(evidence_dir, agent_id)
    status = heartbeat_module.diagnose(ticks, repeat_threshold=repeat_threshold)
    recommended_action = heartbeat_module.recommend_action(status)
    efficiency = heartbeat_module.efficiency_summary(ticks)

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
    ctx.emit({"agent_id": agent_id, "status": status, "recommended_action": recommended_action, "tick_count": len(ticks), "efficiency": efficiency})


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


# --------------------------------------------------------------------------- coverage

@main.command()
@click.argument("legacy_usage_path", type=click.Path(exists=True, path_type=Path))
@click.argument("implementation_path", type=click.Path(exists=True, path_type=Path))
@pass_ctx
def coverage(ctx: Ctx, legacy_usage_path: Path, implementation_path: Path) -> None:
    """Part XCVI: capability-regression coverage -- did the Zone I
    implementation keep referencing everything the pre-migration
    ("legacy") usage code actually referenced?

    Distinct from 'similarity' (suspicious COPYING between reference and
    implementation source text) and 'compare' (functional equivalence of
    two program outputs): this diffs a REQUIREMENT SURFACE. LEGACY_USAGE_PATH
    is the pre-migration application code that actually consumed the
    thing being reimplemented (e.g. every screen/module reading/writing a
    field from a schema being replaced); IMPLEMENTATION_PATH is the Zone I
    output.

    This is a real, useful, but bounded check: a grep/regex-based scan
    over 'identifier: value' usage shapes, not an AST or semantic
    analysis. It catches a named field/enum-value the legacy code
    referenced silently going missing from the implementation, and flags
    (for human review, never auto-failed) an implementation that appears
    to skip a value-conversion convention the legacy code consistently
    applied to an enum-like field -- the exact shape of a real prior bug
    where a clean-room migration's deliberate scoping-down silently
    dropped a region/modem-preset enum-name -> numeric-id conversion. See
    src/cleanroom/coverage.py's module docstring for what this does and
    does not catch."""
    project = ctx.load_project()
    ctx.enforce_zone_access(project, legacy_usage_path)
    ctx.enforce_zone_access(project, implementation_path)
    result = coverage_module.check_coverage(legacy_usage_path, implementation_path)

    out_path = project.root / "evidence" / "coverage-findings.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(jsonlib.dumps(result["findings"], indent=2, sort_keys=True), encoding="utf-8")

    needs_review = [f for f in result["findings"] if f["requires_review"]]
    missing = [f for f in needs_review if f["status"] == "missing"]
    divergent = [f for f in needs_review if f["status"] == "divergent"]

    if result["overall_status"] == "insufficient_evidence":
        ctx.echo(
            "WARNING: no 'identifier: value' usage facts were extracted from LEGACY_USAGE_PATH -- nothing was "
            "checked. This is NOT a clean result; it means the extractor found nothing in its narrow scope to "
            "cross-check (see 'limitations' in the JSON output)."
        )

    project.evidence.append(
        actor=Actor(type="tool", id="cleanroom-coverage-engine"),
        action="cleanroom coverage",
        result="success" if not needs_review else "failure",
        detail=(
            f"{result['distinct_fields_referenced_in_legacy']} distinct field(s) checked, "
            f"{len(missing)} missing, {len(divergent)} divergent, overall_status={result['overall_status']}"
        ),
    )
    ctx.emit({**result, "saved_to": str(out_path)})
    if needs_review:
        ctx.fail(ManualReviewRequired(
            f"{len(missing)} field(s)/usage(s) referenced in the legacy usage code were not found in the Zone I "
            f"implementation, and {len(divergent)} field(s) diverge from the legacy code's value-conversion "
            "convention -- see evidence/coverage-findings.json. These are flags for human review, not a "
            "confirmed defect (see 'limitations' in the JSON output); resolve or explicitly accept each before "
            "release."
        ))


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
            output_licence_id=project.config.data.get("implementation", {}).get("output_licence"),
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


# --------------------------------------------------------------------------- council

@main.command()
@click.option("--backend", type=click.Choice(["anthropic"]), default="anthropic", help="Which real LLM backend answers the Council's prompts.")
@click.option("--model-provider", default="anthropic", help="Recorded on each panel_adjudication -- feeds providers.panel_diversity_required.")
@click.option("--model-id", default=None, help="Overrides the Council's default model (orchestration/backends.py::DEFAULT_COUNCIL_MODEL).")
@pass_ctx
def council(ctx: Ctx, backend: str, model_provider: str | None, model_id: str | None) -> None:
    """Real Parts XLV-LI: the first actual implementation of "whatever LLM
    orchestration the caller uses" that `cleanroom judge`'s own docstring
    has always deferred to. Requires the global --agent-id (a Council
    member registered via `cleanroom recruit`) and, for the 'anthropic'
    backend, a real ANTHROPIC_API_KEY in the environment. Builds the same
    applicant/challenger/judicial-review prompts `cleanroom judge`
    writes to disk for a human, sends each to a REAL model, and merges
    the parsed judicial review back into evidence/legal-findings.json --
    the same merge `cleanroom judge-adjudicate` performs from a
    hand-completed answer file. Real, cost-incurring LLM API calls; never
    invoked implicitly by any other command.

    *** SIMULATED ROLES, NOT REAL LAWYERS OR JUDGES *** -- see
    legal/panels.py. This does not change what these findings mean or
    how much weight they carry, only who answered the prompts."""
    if ctx.agent_id is None:
        raise click.ClickException("The global --agent-id is required (register a Council member first with 'cleanroom recruit').")
    project = ctx.load_project()
    registry = AgentRegistry(project.root / "evidence")
    record = next((a for a in registry.all() if a.agent_id == ctx.agent_id), None)
    if record is None:
        raise click.ClickException(f"No agent registered with id '{ctx.agent_id}' (register one with 'cleanroom recruit').")

    if backend == "anthropic":
        from cleanroom.orchestration.backends import DEFAULT_COUNCIL_MODEL, AnthropicBackend
        try:
            agent_backend = AnthropicBackend(model=model_id or DEFAULT_COUNCIL_MODEL)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
    else:  # pragma: no cover -- click.Choice already restricts this
        raise click.ClickException(f"Unknown backend '{backend}'.")

    # Record the model that ACTUALLY answered the prompts
    # (agent_backend.model, resolved above from --model-id or the
    # Council's real default) -- never the raw model_id CLI param, which
    # is None whenever a caller relies on the default despite a real
    # model having done the work.
    from cleanroom.orchestration.harness import HarnessError, run_council_review
    try:
        result = run_council_review(
            project, agent_backend, panel_member_id=ctx.agent_id, model_provider=model_provider, model_id=agent_backend.model,
        )
    except (HarnessError, RuntimeError) as e:
        raise click.ClickException(str(e)) from e

    failed_packs = [pack_id for pack_id, r in result["packs"].items() if "error" in r]
    project.evidence.append(
        actor=Actor(type="agent", id=ctx.agent_id, role=record.role, model_provider=model_provider, model_id=agent_backend.model),
        action="cleanroom council", result="denied" if failed_packs else "success",
        detail=f"packs={list(result['packs'].keys())} failed={failed_packs}",
    )
    ctx.emit({**result, "model_provider": model_provider, "model_id": agent_backend.model})
    if failed_packs:
        ctx.fail(PolicyFailure(f"The model's response could not be parsed/merged for pack(s): {failed_packs} -- see the emitted output for the raw response."))


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

    try:
        updated_issues = legal_panels.merge_panel_answers(
            findings, pack_id, panel_member_id, answers, model_provider=model_provider, model_id=model_id,
        )
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    findings_path.write_text(jsonlib.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")

    providers_config = project.config.data.get("providers", {})
    completeness = legal_panels.panel_completeness_for_call(
        findings, updated_issues,
        panel_size_required=providers_config.get("panel_size", 1),
        diversity_required=providers_config.get("panel_diversity_required", False),
    )

    project.evidence.append(
        actor=Actor(type="human", id=panel_member_id, role="judicial-panel-member", model_provider=model_provider, model_id=model_id),
        action="cleanroom judge-adjudicate", result="success",
        detail=f"pack={pack_id} panel_member={panel_member_id} issues={updated_issues}",
    )
    ctx.emit({
        "pack_id": pack_id, "panel_member_id": panel_member_id, "issues_updated": updated_issues,
        "panel_completeness": completeness,
    })


# --------------------------------------------------------------------------- remediate

def _load_legal_and_similarity_findings(project: Project) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    legal_path = project.root / "evidence" / "legal-findings.json"
    similarity_path = project.root / "evidence" / "similarity-findings.json"
    legal_findings = jsonlib.loads(legal_path.read_text(encoding="utf-8")) if legal_path.is_file() else []
    similarity_findings = jsonlib.loads(similarity_path.read_text(encoding="utf-8")) if similarity_path.is_file() else []
    return legal_findings, similarity_findings


def _reconcile_and_sync_remediation(project: Project, existing_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Re-derive REMEDIATION_TASKS.json from whatever legal/similarity
    findings currently exist and sync the requirement graph's blocked/
    remediation nodes to match -- the actual mechanism that passes a RED
    or AMBER concern to the implementation team (`assigned_to` on the
    task, a `blocked` node with `responsible_component` in the
    requirement graph). Shared by `remediate` (`existing_tasks` may
    already have a human override applied) and `build` (`existing_tasks`
    loaded fresh, no override path -- registering a new implementation
    agent is not itself a way to resolve an open concern)."""
    legal_findings, similarity_findings = _load_legal_and_similarity_findings(project)
    tasks = remediation_module.reconcile(existing_tasks, legal_findings, similarity_findings)
    tasks_path = project.root / "REMEDIATION_TASKS.json"
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
    return tasks


@main.command()
@click.option("--override", "override_id", default=None, help="Mark a specific open task resolved by human sign-off instead of a clean re-scan (Part LI).")
@click.option("--by", "override_by", default=None, help="Required with --override: who is accepting this residual risk.")
@click.option("--notes", "override_notes", default=None, help="Required with --override: why.")
@pass_ctx
def remediate(ctx: Ctx, override_id: str | None, override_by: str | None, override_notes: str | None) -> None:
    """Routes RED legal findings and suspicious/material similarity findings
    back to the implementation team as blocking requirement-graph nodes
    (AMBER/UNKNOWN and suspicious findings the same way, as non-blocking
    review_required tasks). Idempotent: re-running after a fix clears the
    task automatically; a fix that was never made stays open and blocks
    'cleanroom release' (and, for blocking tasks, 'cleanroom build' -- see
    that command)."""
    project = ctx.load_project()
    tasks_path = project.root / "REMEDIATION_TASKS.json"
    existing_tasks = jsonlib.loads(tasks_path.read_text(encoding="utf-8")) if tasks_path.is_file() else []

    if override_id:
        if not override_by or not override_notes:
            raise click.ClickException("--override requires both --by and --notes.")
        try:
            existing_tasks = remediation_module.apply_override(existing_tasks, override_id, by=override_by, notes=override_notes)
        except ValueError as e:
            raise click.ClickException(str(e)) from e

    tasks = _reconcile_and_sync_remediation(project, existing_tasks)

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

    coverage_path = project.root / "evidence" / "coverage-findings.json"
    if coverage_path.is_file():
        cov_findings = jsonlib.loads(coverage_path.read_text(encoding="utf-8"))
        capability_coverage_result = "findings_open" if any(f["requires_review"] for f in cov_findings) else "no_open_findings"
    else:
        capability_coverage_result = "not_run"

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
        capability_coverage_result=capability_coverage_result,
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

    findings_path = project.root / "evidence" / "legal-findings.json"
    findings = jsonlib.loads(findings_path.read_text(encoding="utf-8")) if findings_path.is_file() else []
    providers_config = project.config.data.get("providers", {})
    panel_diversity_gate, panel_diversity_reasons = legal_panels.panel_completeness_across_findings(
        findings,
        panel_size_required=providers_config.get("panel_size", 1),
        diversity_required=providers_config.get("panel_diversity_required", False),
    )

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
        panel_diversity_gate=panel_diversity_gate,
        require_panel_diversity_gate=policy.get("require_panel_diversity_gate", False),
        panel_diversity_reasons=panel_diversity_reasons,
    )
    human_signoff_required = project.config.data.get("approval_gates", {}).get("human_signoff_required_for_release", True)
    project.evidence.append(actor=Actor(type="tool", id="cleanroom-release"), action="cleanroom release", result="success" if allowed else "denied", detail="; ".join(reasons))
    ctx.emit({
        "release_allowed": allowed, "reasons": reasons, "human_signoff_still_required": human_signoff_required and allowed,
        "panel_diversity": {"satisfied": panel_diversity_gate, "reasons": panel_diversity_reasons, "enforced": policy.get("require_panel_diversity_gate", False)},
    })
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
