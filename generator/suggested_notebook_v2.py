from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


PARAMETER_ORDER = [
    "short_name",
    "collection_id",
    "bbox",
    "datetime",
    "asset_href",
    "asset_key",
    "group",
    "variables",
    "output_dir",
    "access_mode",
]


def emit_suggested_notebook_v2(
    notebook_path: str | Path,
    output_dir: str | Path,
    *,
    readiness_scan: dict[str, Any],
    recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
) -> dict[str, Any]:
    source_path = Path(notebook_path)
    if source_path.suffix.lower() != ".ipynb":
        return {
            "status": "skipped",
            "message": "Suggested notebook V2 is only emitted for .ipynb inputs.",
        }

    original = json.loads(source_path.read_text(encoding="utf-8"))
    output_path = Path(output_dir) / "suggested_notebook_v2.ipynb"
    cells, diff = _build_v2_cells(original, readiness_scan, recommendations, mcp_defaults)
    notebook = {
        "cells": cells,
        "metadata": original.get("metadata", {}),
        "nbformat": original.get("nbformat", 4),
        "nbformat_minor": original.get("nbformat_minor", 5),
    }
    output_path.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "created",
        "original_notebook_path": str(source_path),
        "suggested_v2_notebook_path": str(output_path),
        **diff,
    }
    json_path = Path(output_dir) / "notebook_v2_diff_report.json"
    md_path = Path(output_dir) / "notebook_v2_diff_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_notebook_v2_diff_markdown(report), encoding="utf-8")
    return report


def render_notebook_v2_diff_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Suggested Notebook V2 Diff Report",
        "",
        f"- Original notebook: `{report.get('original_notebook_path', '')}`",
        f"- Suggested notebook: `{report.get('suggested_v2_notebook_path', '')}`",
        "",
        "## Newly Parameterized Values",
        "",
    ]
    values = report.get("newly_parameterized_values", [])
    lines.extend(f"- `{item}`" for item in values) if values else lines.append("None.")
    lines.extend(["", "## DPS-Ready Sections", ""])
    sections = report.get("dps_ready_sections", [])
    lines.extend(f"- {item}" for item in sections) if sections else lines.append("None detected.")
    lines.extend(["", "## Notebook-Only Cells", ""])
    skipped = report.get("removed_or_skipped_notebook_only_cells", [])
    lines.extend(f"- {item}" for item in skipped) if skipped else lines.append("None.")
    lines.extend(["", "## Remaining Issues", ""])
    issues = report.get("remaining_issues", [])
    lines.extend(f"- {item}" for item in issues) if issues else lines.append("None.")
    return "\n".join(lines) + "\n"


def _build_v2_cells(
    original: dict[str, Any],
    readiness_scan: dict[str, Any],
    recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    defaults = _defaults_by_parameter(mcp_defaults)
    parameter_names = _parameter_names(recommendations, defaults)
    source_cells = original.get("cells", [])
    units = readiness_scan.get("units", [])
    notebook_only = {
        unit.get("index")
        for unit in units
        if unit.get("classification") == "Notebook-only"
    }
    dps_ready = [
        unit.get("name", "")
        for unit in units
        if unit.get("classification") in {"DPS-ready", "DPS-candidate-after-refactor"}
    ]
    blocking = [
        f"{unit.get('name')}: {unit.get('reason')}"
        for unit in units
        if unit.get("classification") == "Blocking issue"
    ]

    cells = [
        _markdown_cell(
            "# Suggested DPS/OGC-ready notebook draft\n\n"
            "This notebook was generated as a non-destructive Version 2 suggestion. "
            "The original notebook was preserved unchanged. Changes focus on parameterization, "
            "function structure, output writing under `output/`, and separating optional visualization."
        ),
        _markdown_cell("## Configuration\n\nDPS-ready runtime parameters are collected in this cell."),
        _code_cell(_parameter_cell_source(parameter_names, defaults), tags=["parameters"]),
        _markdown_cell("## Data discovery\n\nResolve collection, asset, and metadata inputs here."),
        _code_cell(_discovery_source()),
        _markdown_cell("## Data access\n\nOpen remote or staged inputs using the selected access mode."),
        _code_cell(_access_source()),
        _markdown_cell(
            "## Setup imported from original notebook\n\n"
            "Import/setup cells are preserved because DPS-ready cells may depend on them."
        ),
        _markdown_cell("## Processing / subsetting\n\nMove science processing into functions where practical."),
    ]

    changed_cells = []
    unchanged_cells = []
    skipped_cells = []
    preserved_setup_cells = []
    for index, cell in enumerate(source_cells):
        if cell.get("cell_type") != "code":
            unchanged_cells.append(index)
            continue
        source = _cell_source(cell)
        if _is_setup_cell(source):
            preserved_setup_cells.append(index)
            cells.append(_markdown_cell(f"### Preserved setup/import cell {index}"))
            cells.append(_code_cell(_transform_setup_source(source)))
            continue
        if index in notebook_only:
            skipped_cells.append(index)
            continue
        transformed = _transform_source(source)
        changed_cells.append(index)
        cells.append(_markdown_cell(f"### Refactored original cell {index}\n\nDPS note: review before packaging."))
        cells.append(_code_cell(transformed))

    cells.extend(
        [
            _markdown_cell("## Output writing\n\nAll job outputs should be written under `output_dir`."),
            _code_cell(_output_source()),
            _markdown_cell("## Optional visualization\n\nKeep exploratory plots here; do not require them for DPS runs."),
            _code_cell("# Optional: add visualization that reads from output_dir without changing job outputs.\n"),
        ]
    )

    diff = {
        "changed_cells": changed_cells,
        "unchanged_cells": unchanged_cells,
        "removed_or_skipped_notebook_only_cells": skipped_cells,
        "preserved_setup_cells": preserved_setup_cells,
        "newly_parameterized_values": parameter_names,
        "dps_ready_sections": dps_ready,
        "remaining_issues": blocking,
    }
    return cells, diff


def _parameter_names(recommendations: dict[str, Any], defaults: dict[str, Any]) -> list[str]:
    names = set(PARAMETER_ORDER)
    for item in recommendations.get("suggested_inputs", []):
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    names.update(defaults)
    return [name for name in PARAMETER_ORDER if name in names] + sorted(names - set(PARAMETER_ORDER))


def _parameter_cell_source(parameter_names: list[str], defaults: dict[str, Any]) -> str:
    lines = ["from pathlib import Path", ""]
    for name in parameter_names:
        value = defaults.get(name, _default_for(name))
        if name == "output_dir":
            lines.append(f"{name} = {value!r}  # MAAP/OGC outputs are written here")
        else:
            lines.append(f"{name} = {value!r}")
    return "\n".join(lines) + "\n"


def _discovery_source() -> str:
    return (
        "def discover_inputs():\n"
        "    \"\"\"Resolve metadata-backed inputs before processing.\"\"\"\n"
        "    return {\n"
        "        'short_name': short_name,\n"
        "        'collection_id': collection_id,\n"
        "        'asset_href': asset_href,\n"
        "        'asset_key': asset_key,\n"
        "        'bbox': bbox,\n"
        "        'datetime': datetime,\n"
        "    }\n\n"
        "discovery = discover_inputs()\n"
    )


def _access_source() -> str:
    return (
        "# Compatibility aliases for common STAC/TiTiler tutorial variable names.\n"
        "collection = globals().get('collection', '') or collection_id or short_name\n"
        "item = globals().get('item', '') or globals().get('asset_key', '')\n"
        "stac_endpoint = globals().get('stac_endpoint', '')\n"
        "titiler_endpoint = globals().get('titiler_endpoint', '')\n\n"
        "def open_input_asset(discovery):\n"
        "    \"\"\"Open or stage input data according to access_mode.\"\"\"\n"
        "    href = discovery.get('asset_href') or asset_href\n"
        "    return href\n\n"
        "def extract_asset_href(item_response, preferred_asset_key='mean', fallback_href=''):\n"
        "    \"\"\"Safely resolve an asset href from STAC item JSON without crashing a DPS run.\"\"\"\n"
        "    if not isinstance(item_response, dict):\n"
        "        print('Warning: STAC item response is not a JSON object; using fallback asset_href.')\n"
        "        return fallback_href\n"
        "    assets = item_response.get('assets') or {}\n"
        "    if not isinstance(assets, dict) or not assets:\n"
        "        print('Warning: STAC item response has no assets; using fallback asset_href.')\n"
        "        return fallback_href\n"
        "    asset = assets.get(preferred_asset_key) or next(iter(assets.values()))\n"
        "    if isinstance(asset, dict):\n"
        "        return asset.get('href', fallback_href)\n"
        "    return fallback_href\n\n"
        "input_asset = open_input_asset(discovery)\n"
    )


def _output_source() -> str:
    return (
        "def write_outputs(result, output_dir=output_dir):\n"
        "    output_path = Path(output_dir)\n"
        "    output_path.mkdir(parents=True, exist_ok=True)\n"
        "    manifest = output_path / 'result_manifest.txt'\n"
        "    manifest.write_text(str(result) + '\\n', encoding='utf-8')\n"
        "    return manifest\n\n"
        "write_outputs(globals().get('input_asset', 'processing result'), output_dir)\n"
    )


def _transform_source(source: str) -> str:
    transformed = source.replace('"/tmp/', '"output/tmp_').replace("'/tmp/", "'output/tmp_")
    transformed = transformed.replace(
        "items_response['assets']['mean']['href']",
        "extract_asset_href(items_response, globals().get('asset_key', '') or 'mean', asset_href or input_asset)",
    )
    transformed = transformed.replace(
        'items_response["assets"]["mean"]["href"]',
        "extract_asset_href(items_response, globals().get('asset_key', '') or 'mean', asset_href or input_asset)",
    )
    if "output_dir" not in transformed and "to_" in transformed:
        transformed = "# Review output paths: write generated files under output_dir.\n" + transformed
    return transformed.rstrip() + "\n"


def _transform_setup_source(source: str) -> str:
    return "# Preserved from original notebook because later DPS-ready cells depend on it.\n" + source.rstrip() + "\n"


def _is_setup_cell(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if not tree.body:
        return False
    import_count = sum(isinstance(node, (ast.Import, ast.ImportFrom)) for node in tree.body)
    if import_count == 0:
        return False
    executable_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and not (
            isinstance(node.func, ast.Name)
            and node.func.id in {"dict", "list", "set", "tuple"}
        )
    ]
    # Preserve import/setup cells, but do not preserve visualization or access cells only because
    # they happen to import a package.
    source_lower = source.lower()
    if any(marker in source_lower for marker in ("plt.show", "folium.", "requests.get", "client.open")):
        return False
    return len(executable_calls) <= 2


def _defaults_by_parameter(mcp_defaults: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for item in mcp_defaults.get("suggestions", []):
        parameter = item.get("parameter")
        if parameter:
            values[str(parameter)] = item.get("suggested_value", "")
    if "output_directory" in values and "output_dir" not in values:
        values["output_dir"] = values["output_directory"]
    return values


def _default_for(name: str) -> Any:
    return {
        "bbox": "",
        "datetime": "",
        "asset_key": "",
        "variables": "",
        "output_dir": "output",
        "access_mode": "auto",
    }.get(name, "")


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return str(source)


def _markdown_cell(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(keepends=True)}


def _code_cell(source: str, tags: list[str] | None = None) -> dict[str, Any]:
    metadata = {"tags": tags} if tags else {}
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": metadata,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }
