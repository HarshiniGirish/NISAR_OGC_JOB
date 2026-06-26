from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def run_runtime_smoke_test(package_dir: str | Path) -> dict[str, Any]:
    path = Path(package_dir)
    candidates = [
        script
        for script in path.glob("*.py")
        if script.name not in {"access_runtime.py", "register_dps.py", "publish_ogc.py"}
    ]
    if not candidates:
        return {"status": "skipped", "message": "No Python entrypoint found."}
    entrypoint = candidates[0]
    result = subprocess.run(
        ["python3", str(entrypoint.name)],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output_dir = path / "output"
    output_files = [str(item.relative_to(path)) for item in output_dir.rglob("*") if item.is_file()] if output_dir.exists() else []
    status = "passed" if result.returncode == 0 and output_files else "failed"
    return {
        "status": status,
        "entrypoint": entrypoint.name,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "output_files": output_files,
    }


def write_runtime_smoke_report(report: dict[str, Any], output_dir: str | Path) -> list[str]:
    path = Path(output_dir)
    json_path = path / "runtime_smoke_test.json"
    md_path = path / "runtime_smoke_test.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_runtime_smoke_markdown(report), encoding="utf-8")
    return [json_path.name, md_path.name]


def render_runtime_smoke_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Runtime Smoke Test",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Entrypoint: `{report.get('entrypoint', '')}`",
        f"- Return code: `{report.get('returncode', '')}`",
        "",
        "## Output files",
        "",
    ]
    files = report.get("output_files", [])
    lines.extend(f"- `{item}`" for item in files) if files else lines.append("None detected.")
    if report.get("stderr"):
        lines.extend(["", "## stderr tail", "", "```text", report["stderr"], "```"])
    if report.get("stdout"):
        lines.extend(["", "## stdout tail", "", "```text", report["stdout"], "```"])
    return "\n".join(lines) + "\n"
