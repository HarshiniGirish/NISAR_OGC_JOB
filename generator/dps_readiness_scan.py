from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any


CLASS_DPS_READY = "DPS-ready"
CLASS_REFACTOR = "DPS-candidate-after-refactor"
CLASS_NOTEBOOK_ONLY = "Notebook-only"
CLASS_BLOCKING = "Blocking issue"

LOCAL_PATH_RE = re.compile(r"^(?:/Users/|/home/|/tmp/|/mnt/|/data/|/workspace/|[A-Za-z]:\\)")
REMOTE_RE = re.compile(r"^(?:s3://|https?://)")
PARAMETER_NAMES = {
    "short_name",
    "collection_id",
    "concept_id",
    "version",
    "asset_href",
    "asset_key",
    "bbox",
    "datetime",
    "crs",
    "group",
    "variables",
    "access_mode",
    "output_dir",
    "out_dir",
}
PLOTTING_IMPORTS = {"matplotlib", "seaborn", "plotly", "cartopy", "folium", "lonboard"}
PLOTTING_CALL_MARKERS = (".plot", "imshow", "show", "savefig", "display")
DATA_ACCESS_CALLS = {
    "open",
    "Path",
    "pathlib.Path",
    "pandas.read_csv",
    "pd.read_csv",
    "xarray.open_dataset",
    "xr.open_dataset",
    "xarray.open_zarr",
    "xr.open_zarr",
    "h5py.File",
    "rasterio.open",
    "requests.get",
    "earthaccess.search_data",
}
OUTPUT_CALL_MARKERS = (
    "to_zarr",
    "to_raster",
    "to_netcdf",
    "to_csv",
    "to_parquet",
    "write",
    "savefig",
)


def scan_dps_readiness(path: str | Path, app_inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    source_path = Path(path)
    app_inputs = app_inputs or {}
    if source_path.suffix.lower() == ".ipynb":
        units = _notebook_units(source_path)
        source_kind = "notebook"
    else:
        units = _script_units(source_path)
        source_kind = "script"

    scanned_units = [_scan_unit(unit, app_inputs) for unit in units]
    score = _overall_score(scanned_units)
    return {
        "source": str(source_path),
        "source_kind": source_kind,
        "summary": {
            "unit_count": len(scanned_units),
            "dps_ready_count": sum(1 for unit in scanned_units if unit["classification"] == CLASS_DPS_READY),
            "candidate_count": sum(1 for unit in scanned_units if unit["classification"] == CLASS_REFACTOR),
            "notebook_only_count": sum(
                1 for unit in scanned_units if unit["classification"] == CLASS_NOTEBOOK_ONLY
            ),
            "blocking_count": sum(1 for unit in scanned_units if unit["classification"] == CLASS_BLOCKING),
            "dps_suitability_score": score,
        },
        "units": scanned_units,
    }


def write_readiness_reports(scan: dict[str, Any], output_dir: str | Path) -> list[str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "dps_readiness_report.json"
    md_path = output_path / "dps_readiness_report.md"
    json_path.write_text(json.dumps(scan, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_readiness_markdown(scan), encoding="utf-8")
    return [json_path.name, md_path.name]


def render_readiness_markdown(scan: dict[str, Any]) -> str:
    summary = scan.get("summary", {})
    lines = [
        "# DPS Readiness Report",
        "",
        f"- Source: `{scan.get('source', '')}`",
        f"- Source kind: `{scan.get('source_kind', '')}`",
        f"- DPS suitability score: `{summary.get('dps_suitability_score', 0)}`",
        f"- DPS-ready units: `{summary.get('dps_ready_count', 0)}`",
        f"- Refactor candidates: `{summary.get('candidate_count', 0)}`",
        f"- Notebook-only units: `{summary.get('notebook_only_count', 0)}`",
        f"- Blocking units: `{summary.get('blocking_count', 0)}`",
        "",
        "## Units",
        "",
    ]
    for unit in scan.get("units", []):
        lines.extend(
            [
                f"### {unit.get('name')}",
                "",
                f"- Classification: `{unit.get('classification')}`",
                f"- Score: `{unit.get('dps_suitability_score')}`",
                f"- Reason: {unit.get('reason')}",
                "",
            ]
        )
        for key in ("detected_inputs", "detected_outputs", "hardcoded_values", "dependencies"):
            values = unit.get(key, [])
            if values:
                lines.append(f"- {key.replace('_', ' ').title()}: " + ", ".join(f"`{v}`" for v in values))
        if unit.get("suggested_refactors"):
            lines.append("")
            lines.append("Suggested refactors:")
            lines.extend(f"- {item}" for item in unit["suggested_refactors"])
        lines.append("")
    return "\n".join(lines)


def _notebook_units(path: Path) -> list[dict[str, Any]]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    units: list[dict[str, Any]] = []
    for index, cell in enumerate(notebook.get("cells", [])):
        source = _cell_source(cell)
        cell_type = cell.get("cell_type", "")
        tags = list((cell.get("metadata") or {}).get("tags", []))
        if cell_type == "markdown":
            units.append(
                {
                    "kind": "markdown_cell",
                    "name": f"notebook cell {index}",
                    "index": index,
                    "source": source,
                    "tags": tags,
                }
            )
            continue
        if cell_type == "code":
            units.append(
                {
                    "kind": "code_cell",
                    "name": f"notebook cell {index}",
                    "index": index,
                    "source": source,
                    "tags": tags,
                }
            )
    return units


def _script_units(path: Path) -> list[dict[str, Any]]:
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [{"kind": "module", "name": path.name, "source": source, "parse_error": True}]

    units: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "source": ast.get_source_segment(source, node) or "",
                    "lineno": node.lineno,
                }
            )
    units.append({"kind": "module", "name": path.name, "source": source, "lineno": 1})
    return units


def _scan_unit(unit: dict[str, Any], app_inputs: dict[str, Any]) -> dict[str, Any]:
    source = unit.get("source", "")
    tags = {str(tag).lower() for tag in unit.get("tags", [])}
    facts = _source_facts(source)
    suggested_refactors = _suggested_refactors(facts, app_inputs)

    if unit.get("parse_error"):
        classification = CLASS_BLOCKING
        reason = "Python syntax error prevents safe packaging."
    elif unit["kind"] == "markdown_cell":
        classification = CLASS_NOTEBOOK_ONLY
        reason = "Markdown/documentation cell is notebook context, not a DPS job block."
    elif "parameters" in tags:
        classification = CLASS_DPS_READY
        reason = "Parameter cell exposes runtime values for packaging."
    elif facts["interactive"] or facts["magic"]:
        classification = CLASS_BLOCKING
        reason = "Interactive or notebook-magic behavior blocks headless DPS execution."
    elif facts["plotting"] and not facts["outputs"]:
        classification = CLASS_NOTEBOOK_ONLY
        reason = "Visualization-only block should remain notebook-only."
    elif facts["hardcoded_local_paths"]:
        classification = CLASS_REFACTOR
        reason = "Computation may be useful for DPS after local paths become parameters."
    elif facts["data_access"] or facts["outputs"]:
        classification = CLASS_DPS_READY if not suggested_refactors else CLASS_REFACTOR
        reason = "Block contains data access or output-writing logic relevant to DPS packaging."
    else:
        classification = CLASS_NOTEBOOK_ONLY if unit["kind"] == "code_cell" else CLASS_REFACTOR
        reason = "No clear data-access/output boundary was detected."

    score = _unit_score(classification, facts)
    return {
        "name": unit.get("name", ""),
        "kind": unit.get("kind", ""),
        "index": unit.get("index"),
        "line": unit.get("lineno"),
        "classification": classification,
        "reason": reason,
        "detected_inputs": sorted(facts["inputs"]),
        "detected_outputs": sorted(facts["outputs"]),
        "hardcoded_values": sorted(facts["hardcoded_values"]),
        "dependencies": sorted(facts["imports"]),
        "data_access": sorted(facts["data_access"]),
        "suggested_refactors": suggested_refactors,
        "dps_suitability_score": score,
    }


def _source_facts(source: str) -> dict[str, Any]:
    facts = {
        "imports": set(),
        "inputs": set(),
        "outputs": set(),
        "hardcoded_values": set(),
        "hardcoded_local_paths": set(),
        "data_access": set(),
        "plotting": False,
        "interactive": False,
        "magic": False,
    }

    if any(line.lstrip().startswith(("%", "!")) for line in source.splitlines()):
        facts["magic"] = True

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _r_source_facts(source, facts)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                facts["imports"].add(root)
                if root in PLOTTING_IMPORTS:
                    facts["plotting"] = True
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            facts["imports"].add(root)
            if root in PLOTTING_IMPORTS:
                facts["plotting"] = True
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if LOCAL_PATH_RE.search(value):
                facts["hardcoded_local_paths"].add(value)
                facts["hardcoded_values"].add(value)
            elif REMOTE_RE.search(value):
                facts["hardcoded_values"].add(value)
                facts["data_access"].add(value)
            elif _looks_parameterish(value):
                facts["hardcoded_values"].add(value)
        elif isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            call_lower = call_name.lower()
            if call_lower == "input" or "ipywidgets" in call_lower:
                facts["interactive"] = True
            if any(marker in call_lower for marker in PLOTTING_CALL_MARKERS):
                facts["plotting"] = True
            if any(call_lower.endswith(marker.lower()) for marker in OUTPUT_CALL_MARKERS):
                facts["outputs"].add(call_name)
            if call_name in DATA_ACCESS_CALLS or any(call_lower.endswith(name.lower()) for name in DATA_ACCESS_CALLS):
                facts["data_access"].add(call_name)
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if _looks_like_output_path(arg.value):
                        facts["outputs"].add(arg.value)
        elif isinstance(node, ast.Name):
            if node.id in PARAMETER_NAMES:
                facts["inputs"].add(node.id)

    return facts


def _r_source_facts(source: str, facts: dict[str, Any]) -> dict[str, Any]:
    for match in re.finditer(r"\b(?:library|require)\s*\(\s*['\"]?([A-Za-z0-9_.]+)['\"]?", source):
        package = match.group(1)
        facts["imports"].add(package)
        if package in {"ggplot2", "leaflet", "tmap", "mapview"}:
            facts["plotting"] = True
    for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9_.]*)::", source):
        package = match.group(1)
        facts["imports"].add(package)
        if package in {"ggplot2", "leaflet", "tmap", "mapview"}:
            facts["plotting"] = True
    for lineno, line in enumerate(source.splitlines(), start=1):
        if re.search(r"\b(readline|file\.choose|menu)\s*\(", line):
            facts["interactive"] = True
        if re.search(r"\binstall\.packages\s*\(", line):
            facts["magic"] = True
        for value in re.findall(r"""['"]([^'"]+)['"]""", line):
            if LOCAL_PATH_RE.search(value):
                facts["hardcoded_local_paths"].add(value)
                facts["hardcoded_values"].add(value)
            elif REMOTE_RE.search(value):
                facts["hardcoded_values"].add(value)
                facts["data_access"].add(value)
        if re.search(r"\b(read.csv|readr::read_|terra::rast|raster::raster|sf::st_read|arrow::read_|rhdf5::h5read|httr2::request|httr::GET|paws::s3)\b", line):
            facts["data_access"].add(line.strip()[:120])
        if re.search(r"\b(write.csv|writeLines|saveRDS|terra::writeRaster|sf::st_write|arrow::write_)", line):
            facts["outputs"].add(line.strip()[:120])
        if re.search(r"\b(plot|print|leaflet|ggplot|tmap::tm_)", line):
            facts["plotting"] = True
    return facts


def _suggested_refactors(facts: dict[str, Any], app_inputs: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    declared = set(app_inputs)
    for value in sorted(facts["hardcoded_local_paths"]):
        suggestions.append(f"Replace hardcoded local path `{value}` with a CLI/app.yaml input.")
    for value in sorted(facts["hardcoded_values"]):
        if value in facts["hardcoded_local_paths"]:
            continue
        if any(name in str(value).lower() for name in PARAMETER_NAMES):
            suggestions.append(f"Consider parameterizing `{value}`.")
    for name in sorted(facts["inputs"] - declared):
        suggestions.append(f"Declare `{name}` in app.yaml or argparse/Papermill parameters.")
    if facts["plotting"] and facts["outputs"]:
        suggestions.append("Separate visualization from output-writing so DPS can run headlessly.")
    if facts["interactive"]:
        suggestions.append("Replace interactive widgets/prompts with runtime parameters.")
    if facts["magic"]:
        suggestions.append("Move notebook shell/magic setup into Dockerfile, build.sh, or plain Python.")
    return suggestions


def _unit_score(classification: str, facts: dict[str, Any]) -> int:
    base = {
        CLASS_DPS_READY: 85,
        CLASS_REFACTOR: 55,
        CLASS_NOTEBOOK_ONLY: 20,
        CLASS_BLOCKING: 0,
    }[classification]
    if facts["data_access"]:
        base += 5
    if facts["outputs"]:
        base += 5
    if facts["hardcoded_local_paths"]:
        base -= 15
    if facts["plotting"]:
        base -= 10
    return max(0, min(100, base))


def _overall_score(units: list[dict[str, Any]]) -> int:
    candidates = [unit["dps_suitability_score"] for unit in units if unit["classification"] != CLASS_NOTEBOOK_ONLY]
    if not candidates:
        return 0
    return round(sum(candidates) / len(candidates))


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _looks_parameterish(value: str) -> bool:
    lowered = value.lower()
    return any(name in lowered for name in PARAMETER_NAMES)


def _looks_like_output_path(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("output/") or any(lowered.endswith(suffix) for suffix in (".zarr", ".tif", ".nc"))
