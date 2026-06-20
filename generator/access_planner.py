from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

try:
    from .access_plan_validator import validate_access_plan
    from .access_strategies import ALLOWED_STRATEGIES, allowed_strategy_ids
except ImportError:
    from access_plan_validator import validate_access_plan
    from access_strategies import ALLOWED_STRATEGIES, allowed_strategy_ids


def plan_access(
    *,
    evidence: dict[str, Any],
    dataset_facts: dict[str, Any] | None = None,
    enabled: bool,
    provider: str,
    model: str,
) -> dict[str, Any]:
    dataset_facts = dataset_facts or {}
    fallback_plan = rule_based_access_plan(evidence, dataset_facts)

    if not enabled:
        return finalize_plan(
            fallback_plan,
            evidence,
            dataset_facts=dataset_facts,
            source="rule_based",
            planner_status="ai_not_requested",
            fallback_used=False,
        )

    resolved_provider = resolve_provider(provider)
    if resolved_provider != "openai":
        return finalize_plan(
            fallback_plan,
            evidence,
            dataset_facts=dataset_facts,
            source="rule_based",
            planner_status=f"unsupported_provider:{resolved_provider}",
            fallback_used=True,
        )

    ai_plan = call_openai_planner(evidence, dataset_facts, model)
    if ai_plan.get("status") != "completed":
        return finalize_plan(
            fallback_plan,
            evidence,
            dataset_facts=dataset_facts,
            source="rule_based",
            planner_status=ai_plan.get("status", "failed"),
            fallback_used=True,
            planner_message=ai_plan.get("message", ""),
        )

    candidate = ai_plan.get("plan", {})
    validation = validate_access_plan(candidate, evidence)
    if not validation["valid"]:
        return finalize_plan(
            fallback_plan,
            evidence,
            dataset_facts=dataset_facts,
            source="rule_based",
            planner_status="ai_plan_invalid",
            fallback_used=True,
            planner_message="; ".join(validation["errors"]),
        )

    return finalize_plan(
        candidate,
        evidence,
        dataset_facts=dataset_facts,
        source="ai_openai",
        planner_status="completed",
        fallback_used=False,
        model=model,
        validation=validation,
    )


def resolve_provider(provider: str) -> str:
    if provider == "auto":
        return "openai" if os.environ.get("OPENAI_API_KEY") else "rule_based"
    return provider


def rule_based_access_plan(evidence: dict[str, Any], dataset_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    dataset_facts = dataset_facts or {}
    formats = set(evidence.get("file_formats", []))
    operations = set(evidence.get("operations", []))
    urls = evidence.get("urls", [])
    imports = set(evidence.get("imports", []))
    access_options = dataset_facts.get("access_options", {})
    asset_format = dataset_facts.get("asset_inspection", {}).get("format")
    if asset_format and asset_format != "unknown":
        formats.add(asset_format)
    has_s3 = (
        any(str(url).startswith("s3://") for url in urls)
        or "direct_s3" in operations
        or access_options.get("direct_s3", False)
    )

    if "raster_api" in operations or access_options.get("raster_api", False):
        strategy = "stac_raster_api"
        reason = "Detected STAC/Raster API access where TileJSON or rendered assets should be requested server-side."
        hints = [
            "Use STAC to select the item for the requested collection/date.",
            "Use the raster API TileJSON endpoint instead of downloading source rasters.",
            "Persist tilejson/manifest outputs for downstream visualization or OGC packaging.",
        ]
    elif has_s3 and "netcdf" in formats and ("xarray" in imports or "write_cog" in operations):
        strategy = "direct_s3_xarray"
        reason = "Detected S3 NetCDF access with xarray-compatible processing."
        if dataset_facts:
            reason = "Dataset facts indicate direct S3 NetCDF access is available."
        hints = [
            "Use temporary Earthdata/MAAP S3 credentials.",
            "Open with s3fs and xarray.open_dataset(..., chunks='auto').",
            "Apply bbox or idx_window before writing output.",
        ]
    elif has_s3 and "hdf5" in formats:
        strategy = "direct_s3_h5py"
        reason = "Detected S3/HDF5 access where h5py-style subsetting is appropriate."
        hints = [
            "Resolve temporary S3 credentials before opening data.",
            "Subset the HDF5 arrays before writing Zarr or raster outputs.",
        ]
    elif {"geotiff", "cog"}.intersection(formats):
        strategy = "rasterio_windowed_read"
        reason = "Detected raster/COG assets where windowed reads avoid full downloads."
        hints = [
            "Use rasterio windows or bounds to read only requested pixels.",
            "Avoid downloading full GeoTIFF assets for small spatial queries.",
        ]
    elif "zarr" in formats:
        strategy = "zarr_open_zarr"
        reason = "Detected Zarr assets or Zarr output patterns."
        hints = [
            "Use xarray.open_zarr for chunk-aware reads.",
            "Preserve chunk alignment when writing downstream outputs.",
        ]
    elif "cmr_search" in operations and has_s3:
        strategy = "cmr_search_then_s3"
        reason = "Detected CMR search followed by direct S3 access signals."
        hints = [
            "Prefer S3 URLs from CMR related URLs after search.",
            "Avoid HTTPS fallback unless S3 credentials are unavailable.",
        ]
    else:
        strategy = "https_download_fallback"
        reason = "No more specific cloud-native access pattern was confidently detected."
        hints = [
            "Use this only as a fallback.",
            "Add dataset IDs, S3/STAC URLs, or file format hints for better planning.",
        ]

    return {
        "chosen_strategy": strategy,
        "reasoning": reason,
        "required_dependencies": ALLOWED_STRATEGIES[strategy]["required_dependencies"],
        "warnings": default_warnings(evidence, dataset_facts),
        "implementation_hints": hints,
    }


def default_warnings(evidence: dict[str, Any], dataset_facts: dict[str, Any] | None = None) -> list[str]:
    dataset_facts = dataset_facts or {}
    warnings: list[str] = []
    operations = set(evidence.get("operations", []))

    if "spatial_subset" not in operations and "index_subset" not in operations:
        warnings.append("No spatial or index subset operation was detected; full-output runs may be expensive.")
    if any(issue.get("severity") == "error" for issue in evidence.get("issues", [])):
        warnings.append("Static analysis found blocking issues that should be fixed before execution.")
    subset_warning = dataset_facts.get("subset_cost", {}).get("warning")
    if subset_warning:
        warnings.append(str(subset_warning))

    return warnings


def call_openai_planner(evidence: dict[str, Any], dataset_facts: dict[str, Any], model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "skipped", "message": "OPENAI_API_KEY is not set."}

    prompt = build_openai_prompt(evidence, dataset_facts)
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an access-strategy planner for NASA Earth science OGC/DPS packages. "
                        "Choose exactly one allowed strategy and return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI access planner failed: {exc}"}

    try:
        content = payload["choices"][0]["message"]["content"]
        return {"status": "completed", "plan": json.loads(content)}
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "failed", "message": f"OpenAI planner returned invalid JSON: {exc}"}


def build_openai_prompt(evidence: dict[str, Any], dataset_facts: dict[str, Any]) -> str:
    payload = {
        "task": "Choose the best data access strategy for a generated OGC/DPS package.",
        "allowed_strategies": allowed_strategy_ids(),
        "strategy_details": ALLOWED_STRATEGIES,
        "evidence": evidence,
        "dataset_facts": dataset_facts,
        "required_json_schema": {
            "chosen_strategy": "one of allowed_strategies",
            "reasoning": "short explanation",
            "required_dependencies": ["package names"],
            "warnings": ["risks"],
            "implementation_hints": ["generator-safe hints"],
        },
    }
    return json.dumps(payload, indent=2)


def finalize_plan(
    plan: dict[str, Any],
    evidence: dict[str, Any],
    *,
    dataset_facts: dict[str, Any] | None = None,
    source: str,
    planner_status: str,
    fallback_used: bool,
    planner_message: str = "",
    model: str = "",
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dataset_facts = dataset_facts or {}
    validation = validation or validate_access_plan(plan, evidence)
    return {
        "source": source,
        "planner_status": planner_status,
        "fallback_used": fallback_used,
        "planner_message": planner_message,
        "model": model,
        "validation": validation,
        "chosen_strategy": plan.get("chosen_strategy"),
        "reasoning": plan.get("reasoning", ""),
        "required_dependencies": plan.get("required_dependencies", []),
        "warnings": plan.get("warnings", []),
        "implementation_hints": plan.get("implementation_hints", []),
        "evidence_summary": {
            "collections": evidence.get("collections", []),
            "file_formats": evidence.get("file_formats", []),
            "operations": evidence.get("operations", []),
            "url_count": len(evidence.get("urls", [])),
        },
        "dataset_facts_summary": {
            "source": dataset_facts.get("source", ""),
            "access_options": dataset_facts.get("access_options", {}),
            "subset_risk": dataset_facts.get("subset_cost", {}).get("risk"),
            "recommended_strategies": dataset_facts.get("recommendation", {}).get(
                "recommended_strategies", []
            ),
        },
    }
