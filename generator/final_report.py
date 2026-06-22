from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_final_report(
    *,
    readiness_scan: dict[str, Any] | None = None,
    llm_recommendations: dict[str, Any] | None = None,
    mcp_defaults: dict[str, Any] | None = None,
    dependency_graph: dict[str, Any] | None = None,
    dataset_facts: dict[str, Any] | None = None,
    access_plan: dict[str, Any] | None = None,
    generated_files: list[str] | None = None,
    validation_report: dict[str, Any] | None = None,
    notebook_v2_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_report = validation_report or {}
    return {
        "summary": {
            "dps_suitability_score": (readiness_scan or {}).get("summary", {}).get(
                "dps_suitability_score"
            ),
            "recommended_entrypoint": (llm_recommendations or {}).get("recommended_entrypoint", ""),
            "ogc_ready": validation_report.get("ogc_ready"),
            "maap_dps_ready": validation_report.get("maap_dps_ready"),
            "cwl_valid": validation_report.get("cwl_valid"),
            "chosen_access_strategy": (access_plan or {}).get("chosen_strategy", ""),
        },
        "dps_readiness_scan": readiness_scan or {},
        "llm_recommendations": llm_recommendations or {},
        "mcp_default_suggestions": mcp_defaults or {},
        "dependency_graph": dependency_graph or {},
        "dataset_facts": dataset_facts or {},
        "access_plan": access_plan or {},
        "generated_package_files": generated_files or [],
        "ogc_validation": validation_report,
        "notebook_v2": notebook_v2_report or {},
        "next_steps": _next_steps(validation_report, llm_recommendations or {}),
    }


def write_final_report(report: dict[str, Any], output_dir: str | Path) -> str:
    path = Path(output_dir) / "final_readiness_report.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return path.name


def render_final_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Final OGCification Readiness Report",
        "",
        f"- DPS suitability score: `{summary.get('dps_suitability_score')}`",
        f"- Recommended entrypoint: `{summary.get('recommended_entrypoint', '')}`",
        f"- Chosen access strategy: `{summary.get('chosen_access_strategy', '')}`",
        f"- OGC ready: `{summary.get('ogc_ready')}`",
        f"- MAAP DPS ready: `{summary.get('maap_dps_ready')}`",
        f"- CWL valid: `{summary.get('cwl_valid')}`",
        "",
        "## Next Steps",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("next_steps", []))
    validation = report.get("ogc_validation", {})
    if validation.get("blocking_issues"):
        lines.extend(["", "## Blocking Issues", ""])
        lines.extend(f"- {item}" for item in validation["blocking_issues"])
    recommendations = report.get("llm_recommendations", {})
    if recommendations.get("required_refactors"):
        lines.extend(["", "## Required Refactors", ""])
        lines.extend(f"- {item}" for item in recommendations["required_refactors"])
    defaults = report.get("mcp_default_suggestions", {}).get("suggestions", [])
    if defaults:
        lines.extend(["", "## MCP Default Suggestions", ""])
        for item in defaults:
            lines.append(
                "- `{parameter}` = `{value}` ({source}, confidence: `{confidence}`)".format(
                    parameter=item.get("parameter"),
                    value=item.get("suggested_value"),
                    source=item.get("source"),
                    confidence=item.get("confidence"),
                )
            )
    return "\n".join(lines) + "\n"


def append_final_report_to_report_md(existing_report: str, final_report: dict[str, Any]) -> str:
    return existing_report.rstrip() + "\n\n" + render_final_report_markdown(final_report)


def _next_steps(validation_report: dict[str, Any], recommendations: dict[str, Any]) -> list[str]:
    steps = list(validation_report.get("next_actions", []))
    if recommendations.get("required_refactors"):
        steps.append("Apply recommended refactors and regenerate the package.")
    if not steps:
        steps.append("Review generated package files and run a representative MAAP/OGC smoke test.")
    return sorted(set(steps))
