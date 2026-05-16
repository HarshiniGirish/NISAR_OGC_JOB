from __future__ import annotations

from pathlib import Path

from maap_package_service.analysis import AnalysisReport


def write_analysis_report(report: AnalysisReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def render_markdown_report(report: AnalysisReport) -> str:
    lines = [
        f"# Analysis Report: {Path(report.artifact).name}",
        "",
        f"- Artifact type: `{report.artifact_type}`",
        f"- Blocking findings: `{report.has_blocking_findings()}`",
        "",
        "## Imports",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report.imports)
    lines.extend(["", "## Dependencies", ""])
    lines.extend(f"- `{item}`" for item in report.dependencies)
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No findings.")
    for finding in report.findings:
        lines.extend(
            [
                f"### {finding.severity.upper()}: {finding.rule}",
                "",
                finding.message,
                "",
                f"Remediation: {finding.remediation}",
                "",
            ]
        )
    return "\n".join(lines)
