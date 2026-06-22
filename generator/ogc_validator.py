from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml


LOCAL_PATH_RE = re.compile(r"(?<![\w])(?:/Users/|/home/|/tmp/|/mnt/|/data/|/workspace/)")


def validate_generated_package(
    package_dir: str | Path,
    *,
    target: str = "both",
    readiness_scan: dict[str, Any] | None = None,
    run_smoke_test: bool = False,
) -> dict[str, Any]:
    path = Path(package_dir)
    blocking: list[str] = []
    warnings: list[str] = []
    next_actions: list[str] = []

    required_common = ["run.sh", "build.sh", "Dockerfile"]
    required_dps = ["algorithm.yml", "algorithm_config.yaml"]
    required_ogc = ["application.cwl", "workflow.cwl"]
    dependency_files = ["env.yml", "requirements.txt"]

    for file_name in required_common:
        _require(path, file_name, blocking)
    if not any((path / name).exists() for name in dependency_files):
        blocking.append("Missing env.yml or requirements.txt dependency file.")

    if _target_includes(target, "dps"):
        for file_name in required_dps:
            _require(path, file_name, blocking)
    if _target_includes(target, "ogc"):
        for file_name in required_ogc:
            _require(path, file_name, blocking)

    input_check = _check_inputs(path)
    blocking.extend(input_check["blocking"])
    warnings.extend(input_check["warnings"])

    output_check = _check_outputs(path)
    blocking.extend(output_check["blocking"])
    warnings.extend(output_check["warnings"])

    source_check = _check_sources(path)
    blocking.extend(source_check["blocking"])
    warnings.extend(source_check["warnings"])

    credential_check = _check_credentials(path)
    warnings.extend(credential_check["warnings"])

    scan_check = _check_readiness_scan(readiness_scan or {})
    blocking.extend(scan_check["blocking"])
    warnings.extend(scan_check["warnings"])

    cwl_result = _validate_cwl(path)
    if cwl_result["status"] == "failed":
        blocking.append("CWL validation failed.")
    elif cwl_result["status"] == "skipped" and _target_includes(target, "ogc"):
        warnings.append("cwltool is not installed; CWL validation was skipped.")
    ap_result = _validate_ogc_application_package(path)
    if ap_result["status"] == "failed":
        blocking.append("OGC Application Package validation failed.")
    elif ap_result["status"] == "skipped" and _target_includes(target, "ogc"):
        warnings.append("ap-validator is not installed; OGC Application Package validation was skipped.")

    smoke_result = _run_smoke_test(path) if run_smoke_test else {"status": "not_requested"}
    if smoke_result["status"] == "failed":
        blocking.append("Local smoke test failed.")

    if blocking:
        next_actions.extend(_next_actions(blocking))
    if warnings:
        next_actions.append("Review warnings before MAAP DPS registration or OGC publication.")
    if not blocking:
        next_actions.append("Package is structurally ready for review, smoke testing, and registration.")

    return {
        "ogc_ready": (
            _target_includes(target, "ogc")
            and not blocking
            and cwl_result["valid"]
            and ap_result["valid"]
        ),
        "maap_dps_ready": _target_includes(target, "dps") and not blocking,
        "cwl_valid": cwl_result["valid"],
        "ogc_application_package_valid": ap_result["valid"],
        "cwl_validation": cwl_result,
        "ogc_application_package_validation": ap_result,
        "smoke_test": smoke_result,
        "blocking_issues": sorted(set(blocking)),
        "warnings": sorted(set(warnings)),
        "next_actions": sorted(set(next_actions)),
    }


def write_validation_reports(report: dict[str, Any], output_dir: str | Path) -> list[str]:
    path = Path(output_dir)
    json_path = path / "ogc_validation_report.json"
    md_path = path / "ogc_validation_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_validation_markdown(report), encoding="utf-8")
    return [json_path.name, md_path.name]


def render_validation_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# OGC / MAAP DPS Validation Report",
        "",
        f"- OGC ready: `{report.get('ogc_ready')}`",
        f"- MAAP DPS ready: `{report.get('maap_dps_ready')}`",
        f"- CWL valid: `{report.get('cwl_valid')}`",
        f"- OGC Application Package valid: `{report.get('ogc_application_package_valid')}`",
        "",
        "## Blocking Issues",
        "",
    ]
    blocking = report.get("blocking_issues", [])
    lines.extend(f"- {item}" for item in blocking) if blocking else lines.append("None.")
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings", [])
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("None.")
    lines.extend(["", "## Next Actions", ""])
    lines.extend(f"- {item}" for item in report.get("next_actions", []))
    return "\n".join(lines) + "\n"


def _require(path: Path, file_name: str, blocking: list[str]) -> None:
    if not (path / file_name).exists():
        blocking.append(f"Missing required file: {file_name}")


def _check_inputs(path: Path) -> dict[str, list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    app_path = path / "app.yaml"
    if not app_path.exists():
        warnings.append("app.yaml is missing; generated package metadata is harder to review.")
        return {"blocking": blocking, "warnings": warnings}
    try:
        app = yaml.safe_load(app_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        blocking.append(f"app.yaml is invalid YAML: {exc}")
        return {"blocking": blocking, "warnings": warnings}
    inputs = app.get("input_schema") or app.get("inputs") or {}
    if not inputs:
        warnings.append("No clear input parameters were declared or inferred.")
    for name, config in inputs.items():
        if isinstance(config, dict) and not config.get("description") and not config.get("doc"):
            warnings.append(f"Input `{name}` is missing a description.")
    return {"blocking": blocking, "warnings": warnings}


def _check_outputs(path: Path) -> dict[str, list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    run_path = path / "run.sh"
    if run_path.exists():
        text = run_path.read_text(encoding="utf-8")
        if "output" not in text and "OUTDIR" not in text:
            blocking.append("run.sh does not appear to route outputs under output/ or OUTDIR.")
    entrypoints = [p for p in path.glob("*.py") if p.name not in {"access_runtime.py", "register_dps.py", "publish_ogc.py"}]
    if entrypoints and not any("output" in p.read_text(encoding="utf-8") for p in entrypoints):
        warnings.append("Entrypoint does not visibly write under output/. Verify runtime output behavior.")
    return {"blocking": blocking, "warnings": warnings}


def _check_sources(path: Path) -> dict[str, list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    for source_path in list(path.glob("*.py")) + list(path.glob("*.sh")):
        if source_path.name in {"register_dps.py", "publish_ogc.py"}:
            continue
        text = source_path.read_text(encoding="utf-8")
        if LOCAL_PATH_RE.search(text):
            warnings.append(f"{source_path.name} contains a hardcoded local path pattern.")
        if source_path.suffix == ".py" and _contains_interactive_input_call(text):
            blocking.append(f"{source_path.name} contains interactive input().")
    return {"blocking": blocking, "warnings": warnings}


def _check_credentials(path: Path) -> dict[str, list[str]]:
    warnings: list[str] = []
    for source_path in list(path.glob("*.py")) + list(path.glob("*.sh")):
        text = source_path.read_text(encoding="utf-8")
        lowered = text.lower()
        if any(token in lowered for token in ("password=", "api_key=", "token=")) and "os.environ" not in text:
            warnings.append(f"{source_path.name} may contain inline credentials; prefer environment variables.")
    return {"warnings": warnings}


def _check_readiness_scan(scan: dict[str, Any]) -> dict[str, list[str]]:
    blocking = []
    warnings = []
    for unit in scan.get("units", []):
        if unit.get("classification") == "Blocking issue":
            blocking.append(f"DPS readiness blocking unit: {unit.get('name')}")
        if unit.get("classification") == "Notebook-only" and unit.get("detected_outputs"):
            warnings.append(f"Notebook-only unit writes outputs: {unit.get('name')}")
    return {"blocking": blocking, "warnings": warnings}


def _validate_cwl(path: Path) -> dict[str, Any]:
    cwl_path = path / "application.cwl"
    workflow_path = path / "workflow.cwl"
    if not cwl_path.exists():
        return {"status": "not_available", "valid": False, "message": "application.cwl is missing."}
    cwltool_path = _which("cwltool")
    if cwltool_path is None:
        return {"status": "skipped", "valid": False, "message": "cwltool is not installed."}
    commands = [[cwltool_path, "--validate", str(cwl_path)]]
    if workflow_path.exists():
        commands.append([cwltool_path, "--validate", str(workflow_path)])
    outputs = []
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        outputs.append(result.stdout + result.stderr)
        if result.returncode != 0:
            return {
                "status": "failed",
                "valid": False,
                "command": command,
                "output": "\n".join(outputs),
            }
    return {"status": "passed", "valid": True, "output": "\n".join(outputs)}


def _validate_ogc_application_package(path: Path) -> dict[str, Any]:
    ap_validator_path = _which("ap-validator")
    if ap_validator_path is None:
        return {"status": "skipped", "valid": False, "message": "ap-validator is not installed."}

    app_package_path = path / "application-package.cwl"
    pack_result = {"status": "not_needed"}
    if not app_package_path.exists():
        cwltool_path = _which("cwltool")
        workflow_path = path / "workflow.cwl"
        if cwltool_path is None or not workflow_path.exists():
            return {
                "status": "skipped",
                "valid": False,
                "message": "application-package.cwl is missing and cwltool/workflow.cwl is unavailable.",
            }
        pack = subprocess.run(
            [cwltool_path, "--pack", str(workflow_path)],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        if pack.returncode != 0:
            return {
                "status": "failed",
                "valid": False,
                "message": "Failed to pack workflow.cwl for OGC AP validation.",
                "output": pack.stdout + pack.stderr,
            }
        app_package_path.write_text(_add_ogc_ap_metadata(pack.stdout, path), encoding="utf-8")
        pack_result = {"status": "created", "path": str(app_package_path)}
    else:
        app_package_path.write_text(
            _add_ogc_ap_metadata(app_package_path.read_text(encoding="utf-8"), path),
            encoding="utf-8",
        )

    result = subprocess.run(
        [ap_validator_path, "--format", "json", "--detail", "all", str(app_package_path)],
        cwd=path,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"raw_stdout": result.stdout}
    valid = result.returncode == 0 and bool(payload.get("valid", False))
    return {
        "status": "passed" if valid else "failed",
        "valid": valid,
        "returncode": result.returncode,
        "pack": pack_result,
        "report": payload,
        "stderr": result.stderr,
    }


def _run_smoke_test(path: Path) -> dict[str, Any]:
    run_path = path / "run.sh"
    if not run_path.exists():
        return {"status": "failed", "message": "run.sh is missing."}
    result = subprocess.run(["bash", str(run_path), "--help"], cwd=path, check=False, capture_output=True, text=True)
    if result.returncode in {0, 2}:
        return {"status": "passed", "returncode": result.returncode, "output": result.stdout + result.stderr}
    return {"status": "failed", "returncode": result.returncode, "output": result.stdout + result.stderr}


def _contains_interactive_input_call(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "input(" in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input":
            return True
    return False


def _add_ogc_ap_metadata(cwl_text: str, package_dir: Path) -> str:
    try:
        packed = yaml.safe_load(cwl_text) or {}
    except yaml.YAMLError:
        return cwl_text
    namespaces = packed.get("$namespaces")
    if not isinstance(namespaces, dict):
        namespaces = {}
    namespaces.setdefault("s", "https://schema.org/")
    packed["$namespaces"] = namespaces
    packed.setdefault("s:softwareVersion", _package_version(package_dir))
    return yaml.safe_dump(packed, sort_keys=False)


def _package_version(package_dir: Path) -> str:
    app_path = package_dir / "app.yaml"
    if not app_path.exists():
        return "main"
    try:
        app = yaml.safe_load(app_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return "main"
    return str(app.get("version") or app.get("algorithm_version") or "main")


def _which(command: str) -> str | None:
    resolved = shutil.which(command)
    if resolved:
        return resolved
    local = Path.home() / ".local" / "bin" / command
    if local.exists():
        return str(local)
    return None


def _next_actions(blocking: list[str]) -> list[str]:
    actions = []
    if any("Missing required file" in item for item in blocking):
        actions.append("Regenerate the package with the correct target flags.")
    if any("interactive" in item.lower() for item in blocking):
        actions.append("Replace interactive code with app.yaml, argparse, or Papermill parameters.")
    if any("CWL" in item for item in blocking):
        actions.append("Install cwltool locally and fix reported CWL validation errors.")
    return actions or ["Resolve blocking issues listed above, then rerun validation."]


def _target_includes(target: str, requested: str) -> bool:
    normalized = "both" if target in {"ogc_dps", "ogc-dps"} else target
    return normalized == "both" or normalized == requested
