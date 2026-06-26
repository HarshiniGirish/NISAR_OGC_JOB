from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


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
    use_llm_synthesis: bool = False,
    llm_provider: str = "auto",
    llm_model: str = "",
) -> dict[str, Any]:
    source_path = Path(notebook_path)
    if source_path.suffix.lower() != ".ipynb":
        return {
            "status": "skipped",
            "message": "Suggested notebook V2 is only emitted for .ipynb inputs.",
        }

    original = json.loads(source_path.read_text(encoding="utf-8"))
    output_path = Path(output_dir) / "suggested_notebook_v2.ipynb"
    synthesis = synthesize_notebook_v2_cells(
        original=original,
        readiness_scan=readiness_scan,
        recommendations=recommendations,
        mcp_defaults=mcp_defaults,
        enabled=use_llm_synthesis,
        provider=llm_provider,
        model=llm_model,
    )
    cells, diff = synthesis["cells"], synthesis["diff"]
    notebook = {
        "cells": cells,
        "metadata": original.get("metadata", {}),
        "nbformat": original.get("nbformat", 4),
        "nbformat_minor": original.get("nbformat_minor", 5),
    }
    output_path.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "created",
        "synthesis": synthesis["metadata"],
        "original_notebook_path": str(source_path),
        "suggested_v2_notebook_path": str(output_path),
        **diff,
    }
    json_path = Path(output_dir) / "notebook_v2_diff_report.json"
    md_path = Path(output_dir) / "notebook_v2_diff_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_notebook_v2_diff_markdown(report), encoding="utf-8")
    return report


def synthesize_notebook_v2_cells(
    *,
    original: dict[str, Any],
    readiness_scan: dict[str, Any],
    recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
    enabled: bool,
    provider: str,
    model: str,
) -> dict[str, Any]:
    fallback_cells, fallback_diff = _build_v2_cells(original, readiness_scan, recommendations, mcp_defaults)
    if not enabled:
        return {
            "cells": fallback_cells,
            "diff": fallback_diff,
            "metadata": {
                "status": "fallback",
                "provider": "rule_based",
                "message": "LLM notebook synthesis was not requested.",
            },
        }

    resolved_provider = _resolve_provider(provider)
    if resolved_provider != "openai":
        return {
            "cells": fallback_cells,
            "diff": fallback_diff,
            "metadata": {
                "status": "fallback",
                "provider": resolved_provider,
                "message": "Only OpenAI notebook synthesis is currently implemented.",
            },
        }

    result = _call_openai_notebook_synthesis(
        original=original,
        readiness_scan=readiness_scan,
        recommendations=recommendations,
        mcp_defaults=mcp_defaults,
        model=model or "gpt-4o-mini",
    )
    if result.get("status") != "completed":
        return {
            "cells": fallback_cells,
            "diff": fallback_diff,
            "metadata": {
                "status": "fallback",
                "provider": "openai",
                "message": result.get("message", "OpenAI synthesis did not complete."),
            },
        }

    validation = _validate_llm_notebook_payload(result.get("payload", {}))
    if not validation["valid"]:
        return {
            "cells": fallback_cells,
            "diff": fallback_diff,
            "metadata": {
                "status": "fallback",
                "provider": "openai",
                "model": result.get("model", model),
                "message": "OpenAI notebook synthesis returned invalid notebook JSON.",
                "validation_errors": validation["errors"],
            },
        }

    payload = result["payload"]
    return {
        "cells": [_payload_cell_to_notebook_cell(cell) for cell in payload["cells"]],
        "diff": _normalize_llm_diff(payload.get("diff", {}), fallback_diff),
        "metadata": {
            "status": "completed",
            "provider": "openai",
            "model": result.get("model", model),
            "validation": validation,
        },
    }


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
        if _is_helper_cell(source):
            preserved_setup_cells.append(index)
            cells.append(_markdown_cell(f"### Preserved helper/function cell {index}"))
            cells.append(_code_cell(_transform_setup_source(source)))
            continue
        if _is_job_execution_cell(source):
            changed_cells.append(index)
            cells.append(_markdown_cell(f"### Preserved job execution cell {index}\n\nDPS note: this cell creates runtime job outputs."))
            cells.append(_code_cell(_transform_source(source)))
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


def _resolve_provider(provider: str) -> str:
    provider = provider.lower()
    if provider != "auto":
        return provider
    return "openai" if os.environ.get("OPENAI_API_KEY") else "none"


def _call_openai_notebook_synthesis(
    *,
    original: dict[str, Any],
    readiness_scan: dict[str, Any],
    recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "message": "OPENAI_API_KEY is not set."}

    prompt = _build_notebook_synthesis_prompt(original, readiness_scan, recommendations, mcp_defaults)
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You refactor exploratory MAAP/OGC notebooks into runtime-safe notebook drafts. "
                        "Return JSON only. Do not include secrets. Do not hardcode catalog defaults from docs."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content = response_payload["choices"][0]["message"]["content"]
        return {"status": "completed", "model": model, "payload": json.loads(content)}
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI notebook synthesis failed: {exc}"}


def _build_notebook_synthesis_prompt(
    original: dict[str, Any],
    readiness_scan: dict[str, Any],
    recommendations: dict[str, Any],
    mcp_defaults: dict[str, Any],
) -> str:
    original_cells = []
    for index, cell in enumerate(original.get("cells", [])):
        original_cells.append(
            {
                "index": index,
                "cell_type": cell.get("cell_type"),
                "source": _cell_source(cell),
            }
        )

    return json.dumps(
        {
            "task": (
                "Create a suggested Version 2 notebook that is runtime-safe for OGC/MAAP DPS packaging. "
                "The notebook must preserve scientific intent, make hidden notebook state explicit, "
                "separate optional visualization, and write outputs under output_dir."
            ),
            "rules": [
                "Do not overwrite the original notebook.",
                "Return JSON only with keys cells and diff.",
                "Each cell must have cell_type markdown or code and a source string.",
                "Code cells must be valid Python.",
                "Include a parameters cell tagged parameters.",
                "Define safe defaults for short_name, collection_id, bbox, datetime, asset_href, asset_key, group, variables, output_dir, and access_mode.",
                "Do not crash if STAC responses are missing assets; use warnings and fallback outputs.",
                "Always write at least one file under output_dir.",
                "Keep visualization optional and not required for the job.",
                "Do not invent real MAAP/STAC dataset defaults. Use blanks or provenance-backed suggestions.",
            ],
            "required_json_schema": {
                "cells": [
                    {
                        "cell_type": "markdown|code",
                        "source": "string",
                        "tags": ["optional list; include parameters for parameter cell"],
                    }
                ],
                "diff": {
                    "changed_cells": ["original cell indexes"],
                    "unchanged_cells": ["original cell indexes"],
                    "removed_or_skipped_notebook_only_cells": ["original cell indexes"],
                    "preserved_setup_cells": ["original cell indexes"],
                    "newly_parameterized_values": ["parameter names"],
                    "dps_ready_sections": ["section names"],
                    "remaining_issues": ["strings"],
                },
            },
            "original_cells": original_cells,
            "readiness_scan": readiness_scan,
            "recommendations": recommendations,
            "mcp_defaults": mcp_defaults,
        },
        indent=2,
    )


def _validate_llm_notebook_payload(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["Payload must be a JSON object."]}
    cells = payload.get("cells")
    if not isinstance(cells, list) or not cells:
        errors.append("cells must be a non-empty list.")
        return {"valid": False, "errors": errors}
    has_parameters = False
    has_output_write = False
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append(f"cell {index} must be an object.")
            continue
        cell_type = cell.get("cell_type")
        source = cell.get("source")
        if cell_type not in {"markdown", "code"}:
            errors.append(f"cell {index} has invalid cell_type.")
        if not isinstance(source, str):
            errors.append(f"cell {index} source must be a string.")
            continue
        if cell_type == "code":
            tags = cell.get("tags", [])
            if isinstance(tags, list) and "parameters" in tags:
                has_parameters = True
            if "output_dir" in source and (".write" in source or "open(" in source or "mkdir" in source):
                has_output_write = True
            try:
                ast.parse(source)
            except SyntaxError as exc:
                errors.append(f"cell {index} has invalid Python: {exc.msg}")
    if not has_parameters:
        errors.append("No code cell tagged parameters was returned.")
    if not has_output_write:
        errors.append("No code cell visibly writes output under output_dir.")
    return {"valid": not errors, "errors": errors}


def _payload_cell_to_notebook_cell(cell: dict[str, Any]) -> dict[str, Any]:
    cell_type = cell["cell_type"]
    if cell_type == "markdown":
        return _markdown_cell(cell["source"])
    tags = cell.get("tags", [])
    return _code_cell(cell["source"].rstrip() + "\n", tags=tags if isinstance(tags, list) else None)


def _normalize_llm_diff(diff: dict[str, Any], fallback_diff: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(fallback_diff)
    if isinstance(diff, dict):
        for key in (
            "changed_cells",
            "unchanged_cells",
            "removed_or_skipped_notebook_only_cells",
            "preserved_setup_cells",
            "newly_parameterized_values",
            "dps_ready_sections",
            "remaining_issues",
        ):
            if isinstance(diff.get(key), list):
                normalized[key] = diff[key]
    return normalized


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
        "def maap_search_granule(maap_client, **kwargs):\n"
        "    \"\"\"Support both older camelCase and newer snake_case maap-py APIs.\"\"\"\n"
        "    try:\n"
        "        if hasattr(maap_client, 'search_granule'):\n"
        "            return maap_client.search_granule(**kwargs)\n"
        "        return maap_client.searchGranule(**kwargs)\n"
        "    except Exception as exc:\n"
        "        print(f'Warning: MAAP granule search failed: {exc}')\n"
        "        return []\n\n"
        "def maap_search_collection(maap_client, **kwargs):\n"
        "    \"\"\"Support both older camelCase and newer snake_case maap-py APIs.\"\"\"\n"
        "    try:\n"
        "        if hasattr(maap_client, 'search_collection'):\n"
        "            return maap_client.search_collection(**kwargs)\n"
        "        return maap_client.searchCollection(**kwargs)\n"
        "    except Exception as exc:\n"
        "        print(f'Warning: MAAP collection search failed: {exc}')\n"
        "        return []\n\n"
        "def safe_get_data(result, data_dir=None):\n"
        "    \"\"\"Download when authorized; otherwise write a reviewable access-failure manifest.\"\"\"\n"
        "    output_path = Path(globals().get('output_dir', 'output'))\n"
        "    output_path.mkdir(parents=True, exist_ok=True)\n"
        "    try:\n"
        "        if result is None:\n"
        "            raise ValueError('No MAAP search result is available for download.')\n"
        "        target_dir = data_dir or output_path\n"
        "        return result.getData(str(target_dir))\n"
        "    except Exception as exc:\n"
        "        manifest = output_path / 'data_access_failure.json'\n"
        "        manifest.write_text(json.dumps({'error': str(exc), 'note': 'Data download failed; package structure remains reviewable.'}, indent=2) + '\\n', encoding='utf-8')\n"
        "        print(f'Warning: data download failed; wrote {manifest}: {exc}')\n"
        "        return ''\n\n"
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
    transformed = transformed.replace("maap.searchGranule(", "maap_search_granule(maap, ")
    transformed = transformed.replace("maap.search_granule(", "maap_search_granule(maap, ")
    transformed = transformed.replace("maap.searchCollection(", "maap_search_collection(maap, ")
    transformed = transformed.replace("maap.search_collection(", "maap_search_collection(maap, ")
    transformed = re.sub(
        r"([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?)\.getData\(([^)]*)\)",
        r"safe_get_data(\1, \2)",
        transformed,
    )
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


def _is_helper_cell(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    if not tree.body:
        return False
    has_function_or_class = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in tree.body)
    has_uppercase_catalog = any(
        isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id.isupper() for target in node.targets)
        for node in tree.body
    )
    if not (has_function_or_class or has_uppercase_catalog):
        return False
    source_lower = source.lower()
    if any(marker in source_lower for marker in ("plt.show", "folium.map", "display(")):
        return False
    return True


def _is_job_execution_cell(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    assigned = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                assigned.update(_assigned_names(target))
        elif isinstance(node, ast.AnnAssign):
            assigned.update(_assigned_names(node.target))
    return bool(
        assigned.intersection(
            {
                "job_result",
                "items_response",
                "collection_metadata",
                "written_outputs",
                "selected_algorithm",
                "ranked_algorithms",
            }
        )
    )


def _assigned_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for item in node.elts:
            names.update(_assigned_names(item))
        return names
    return set()


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
