from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_readiness_summary(
    *,
    readiness_scan: dict[str, Any],
    validation_report: dict[str, Any],
    llm_recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
    dependency_graph: dict[str, Any],
    access_plan: dict[str, Any],
    generated_files: list[str],
    repair_plan: dict[str, Any] | None = None,
    smoke_test: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repair_plan = repair_plan or {}
    smoke_test = smoke_test or {}
    blocking = _blocking_items(readiness_scan, validation_report)
    needs_refactor = _refactor_items(readiness_scan, llm_recommendations)
    runtime_risks = _runtime_risks(validation_report, access_plan, readiness_scan, smoke_test)
    required_inputs = _required_inputs(llm_recommendations, mcp_defaults)
    score = _score_breakdown(readiness_scan, validation_report, dependency_graph, access_plan)
    decision = _conversion_decision(blocking, needs_refactor, validation_report)

    return {
        "decision": decision,
        "score": score,
        "blocking": blocking,
        "needs_refactor": needs_refactor,
        "runtime_risks": runtime_risks,
        "notebook_only_cells": _notebook_only_cells(readiness_scan),
        "dps_ready_cells": _dps_ready_cells(readiness_scan),
        "required_inputs": required_inputs,
        "dependency_summary": dependency_graph.get("summary", {}),
        "access_strategy": {
            "chosen_strategy": access_plan.get("chosen_strategy", ""),
            "reasoning": access_plan.get("reasoning", ""),
            "required_dependencies": access_plan.get("required_dependencies", []),
            "warnings": access_plan.get("warnings", []),
        },
        "validation": {
            "ogc_ready": validation_report.get("ogc_ready"),
            "maap_dps_ready": validation_report.get("maap_dps_ready"),
            "cwl_valid": validation_report.get("cwl_valid"),
            "ogc_application_package_valid": validation_report.get(
                "ogc_application_package_valid"
            ),
        },
        "autofix": {
            "safe_autofix_count": len(repair_plan.get("safe_autofixes", [])),
            "review_required_count": len(repair_plan.get("requires_user_review", [])),
            "science_review_count": len(repair_plan.get("science_review_required", [])),
        },
        "next_commands": _next_commands(validation_report),
        "generated_files": generated_files,
    }


def write_readiness_summary(summary: dict[str, Any], output_dir: str | Path) -> list[str]:
    path = Path(output_dir)
    json_path = path / "readiness_summary.json"
    md_path = path / "readiness_summary.md"
    start_path = path / "START_HERE.md"
    checklist_path = path / "dps_conversion_checklist.md"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    md = render_readiness_summary_markdown(summary)
    md_path.write_text(md, encoding="utf-8")
    start_path.write_text(render_start_here(summary), encoding="utf-8")
    checklist_path.write_text(render_dps_checklist(summary), encoding="utf-8")
    return [
        json_path.name,
        md_path.name,
        start_path.name,
        checklist_path.name,
    ]


def render_readiness_summary_markdown(summary: dict[str, Any]) -> str:
    score = summary.get("score", {})
    lines = [
        "# Readiness Summary",
        "",
        f"- DPS conversion decision: **{summary.get('decision', {}).get('status', 'unknown')}**",
        f"- Reason: {summary.get('decision', {}).get('reason', '')}",
        f"- Readiness score: **{score.get('total', 0)} / 100**",
        f"- OGC ready: `{summary.get('validation', {}).get('ogc_ready')}`",
        f"- MAAP DPS ready: `{summary.get('validation', {}).get('maap_dps_ready')}`",
        f"- CWL valid: `{summary.get('validation', {}).get('cwl_valid')}`",
        f"- OGC Application Package valid: `{summary.get('validation', {}).get('ogc_application_package_valid')}`",
        "",
        "## Score Breakdown",
        "",
    ]
    for item in score.get("breakdown", []):
        sign = "+" if item.get("points", 0) >= 0 else ""
        lines.append(f"- {sign}{item.get('points', 0)}: {item.get('reason', '')}")
    _section(lines, "Blocking Issues", summary.get("blocking", []))
    _section(lines, "Needs Refactor", summary.get("needs_refactor", []))
    _section(lines, "Runtime Risks", summary.get("runtime_risks", []))
    _section(lines, "DPS-Ready Cells / Blocks", summary.get("dps_ready_cells", []))
    _section(lines, "Notebook-Only Cells", summary.get("notebook_only_cells", []))
    lines.extend(["", "## Required Inputs", ""])
    inputs = summary.get("required_inputs", [])
    if inputs:
        lines.append("| Name | Default | Source | User action |")
        lines.append("| --- | --- | --- | --- |")
        for item in inputs:
            lines.append(
                "| `{name}` | `{default}` | {source} | {action} |".format(
                    name=item.get("name", ""),
                    default=item.get("suggested_default", ""),
                    source=item.get("source", ""),
                    action=item.get("user_action", ""),
                )
            )
    else:
        lines.append("No required inputs were detected.")
    lines.extend(["", "## Suggested Access Strategy", ""])
    strategy = summary.get("access_strategy", {})
    lines.append(f"- Strategy: `{strategy.get('chosen_strategy', '')}`")
    lines.append(f"- Reason: {strategy.get('reasoning', '')}")
    if strategy.get("warnings"):
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in strategy["warnings"])
    _section(lines, "Next Commands", summary.get("next_commands", []), code=True)
    return "\n".join(lines) + "\n"


def render_start_here(summary: dict[str, Any]) -> str:
    lines = [
        "# START HERE",
        "",
        "Open this file first. It summarizes whether this generated package is ready, what is blocking it, and what to run next.",
        "",
        f"**Decision:** {summary.get('decision', {}).get('status', 'unknown')}",
        f"**Reason:** {summary.get('decision', {}).get('reason', '')}",
        f"**Readiness score:** {summary.get('score', {}).get('total', 0)} / 100",
        "",
        "## Immediate Next Step",
        "",
    ]
    commands = summary.get("next_commands", [])
    if commands:
        lines.append("```bash")
        lines.append(commands[0])
        lines.append("```")
    else:
        lines.append("Review `readiness_summary.md`.")
    lines.extend(
        [
            "",
            "## Files to inspect",
            "",
            "- `readiness_summary.md`",
            "- `dps_conversion_checklist.md`",
            "- `ogc_validation_report.md`",
            "- `llm_repair_plan.md`",
            "- `safe_autofix_report.md`",
            "- `report.md`",
        ]
    )
    return "\n".join(lines) + "\n"


def render_dps_checklist(summary: dict[str, Any]) -> str:
    lines = ["# DPS Conversion Checklist", "", "## Required", ""]
    required = summary.get("blocking", []) + summary.get("needs_refactor", [])
    if required:
        lines.extend(f"- [ ] {item}" for item in required)
    else:
        lines.append("- [x] No blocking or required refactor items were detected.")
    lines.extend(["", "## Runtime risks to review", ""])
    risks = summary.get("runtime_risks", [])
    if risks:
        lines.extend(f"- [ ] {item}" for item in risks)
    else:
        lines.append("- [x] No runtime risks were detected.")
    lines.extend(["", "## Already OK", ""])
    validation = summary.get("validation", {})
    for name, value in validation.items():
        lines.append(f"- [{'x' if value else ' '}] {name.replace('_', ' ')}")
    return "\n".join(lines) + "\n"


def _section(lines: list[str], title: str, items: list[str], code: bool = False) -> None:
    lines.extend(["", f"## {title}", ""])
    if not items:
        lines.append("None.")
        return
    if code:
        for item in items:
            lines.append("```bash")
            lines.append(str(item))
            lines.append("```")
    else:
        lines.extend(f"- {item}" for item in items)


def _blocking_items(readiness_scan: dict[str, Any], validation_report: dict[str, Any]) -> list[str]:
    items = list(validation_report.get("blocking_issues", []))
    for unit in readiness_scan.get("units", []):
        if unit.get("classification") == "Blocking issue":
            items.append(f"{unit.get('name')}: {unit.get('reason')}")
    return sorted(set(items))


def _refactor_items(readiness_scan: dict[str, Any], llm_recommendations: dict[str, Any]) -> list[str]:
    items = []
    for unit in readiness_scan.get("units", []):
        for refactor in unit.get("suggested_refactors", []):
            items.append(refactor)
    items.extend(llm_recommendations.get("required_refactors", []))
    return sorted(set(items))


def _runtime_risks(
    validation_report: dict[str, Any],
    access_plan: dict[str, Any],
    readiness_scan: dict[str, Any],
    smoke_test: dict[str, Any],
) -> list[str]:
    risks = list(validation_report.get("warnings", []))
    risks.extend(access_plan.get("warnings", []))
    if smoke_test.get("status") == "failed":
        risks.append("Runtime smoke test failed; inspect runtime_smoke_test.md.")
    if any("getData" in str(unit) for unit in readiness_scan.get("units", [])):
        risks.append("MAAP getData/download paths may require credentials or staged inputs.")
    return sorted(set(risks))


def _notebook_only_cells(readiness_scan: dict[str, Any]) -> list[str]:
    return [
        f"{unit.get('name')}: {unit.get('reason')}"
        for unit in readiness_scan.get("units", [])
        if unit.get("classification") == "Notebook-only"
    ]


def _dps_ready_cells(readiness_scan: dict[str, Any]) -> list[str]:
    return [
        f"{unit.get('name')}: {unit.get('classification')} ({unit.get('dps_suitability_score', 0)})"
        for unit in readiness_scan.get("units", [])
        if unit.get("classification") in {"DPS-ready", "DPS-candidate-after-refactor"}
    ]


def _required_inputs(
    llm_recommendations: dict[str, Any], mcp_defaults: dict[str, Any]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in llm_recommendations.get("suggested_inputs", []):
        if item.get("name"):
            merged[item["name"]] = {
                "name": item["name"],
                "suggested_default": item.get("suggested_default", ""),
                "source": item.get("source", "LLM/static scan"),
                "user_action": "confirm or override",
            }
    for item in mcp_defaults.get("suggestions", []):
        name = item.get("parameter")
        if name:
            merged[name] = {
                "name": name,
                "suggested_default": item.get("suggested_value", ""),
                "source": item.get("source", ""),
                "user_action": "confirm or override" if item.get("user_can_override", True) else "fixed",
            }
    return [merged[key] for key in sorted(merged)]


def _score_breakdown(
    readiness_scan: dict[str, Any],
    validation_report: dict[str, Any],
    dependency_graph: dict[str, Any],
    access_plan: dict[str, Any],
) -> dict[str, Any]:
    breakdown: list[dict[str, Any]] = []
    def add(points: int, reason: str) -> None:
        breakdown.append({"points": points, "reason": reason})

    summary = readiness_scan.get("summary", {})
    add(min(25, int(summary.get("dps_ready_count", 0)) * 5), "DPS-ready cells/blocks detected")
    add(15 if access_plan.get("chosen_strategy") else 0, "Access strategy selected")
    add(15 if dependency_graph.get("summary", {}).get("unresolved_count", 0) == 0 else -10, "Dependencies resolved")
    add(15 if validation_report.get("cwl_valid") else -10, "CWL validation status")
    add(15 if validation_report.get("ogc_application_package_valid") else -10, "OGC Application Package validation status")
    add(15 if validation_report.get("maap_dps_ready") else -10, "MAAP DPS structural readiness")
    blocking_count = len(validation_report.get("blocking_issues", [])) + int(summary.get("blocking_count", 0))
    if blocking_count:
        add(-min(35, blocking_count * 10), "Blocking issues present")
    total = max(0, min(100, sum(item["points"] for item in breakdown)))
    return {"total": total, "breakdown": breakdown}


def _conversion_decision(
    blocking: list[str], needs_refactor: list[str], validation_report: dict[str, Any]
) -> dict[str, str]:
    if blocking:
        return {
            "status": "Yes, after blocking issues are fixed",
            "reason": f"{len(blocking)} blocking issue(s) must be resolved first.",
        }
    if needs_refactor:
        return {
            "status": "Yes, after refactor",
            "reason": f"{len(needs_refactor)} refactor item(s) should be reviewed.",
        }
    if validation_report.get("ogc_ready") and validation_report.get("maap_dps_ready"):
        return {
            "status": "Yes, structurally ready",
            "reason": "Package validates structurally; run a smoke test and review science outputs.",
        }
    return {
        "status": "Needs review",
        "reason": "Readiness is inconclusive; inspect validation and readiness reports.",
    }


def _next_commands(validation_report: dict[str, Any]) -> list[str]:
    if validation_report.get("ogc_ready") and validation_report.get("maap_dps_ready"):
        return [
            "python3 suggested_notebook_v2.py",
            "ap-validator --format json --detail all application-package.cwl",
        ]
    return [
        "cat readiness_summary.md",
        "cat dps_conversion_checklist.md",
    ]
