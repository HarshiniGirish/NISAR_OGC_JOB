from __future__ import annotations

from typing import Any

from .access_options import check_access_options
from .asset_inspection import inspect_asset
from .cmr import get_cmr_collection, get_cmr_granule
from .cost_estimator import estimate_subset_cost


def build_dataset_facts(evidence: dict[str, Any], *, live: bool = False) -> dict[str, Any]:
    collections = evidence.get("collections", [])
    collection = collections[0] if collections else ""
    inputs = evidence.get("inputs", {})
    granule_ur = str(inputs.get("granule_ur", {}).get("default", ""))
    idx_window = str(inputs.get("idx_window", {}).get("default", ""))
    bbox = str(inputs.get("bbox", {}).get("default", ""))

    cmr_collection = get_cmr_collection(collection, live=live) if collection else {"status": "not_available"}
    cmr_granule = get_cmr_granule(granule_ur=granule_ur, short_name=collection, live=live)

    metadata_urls = {
        "s3_urls": evidence.get("urls", []),
        "https_urls": evidence.get("urls", []),
        "zarr_urls": [url for url in evidence.get("urls", []) if "zarr" in str(url).lower()],
        "granule_ur": granule_ur,
    }
    if cmr_granule.get("status") == "found":
        metadata_urls = merge_metadata_urls(metadata_urls, cmr_granule)

    asset = inspect_asset(metadata=metadata_urls)
    options = check_access_options(urls=evidence.get("urls", []), collection=collection, metadata=metadata_urls)
    subset_cost = estimate_subset_cost(
        dimensions=asset.get("dimensions", {}),
        subset={"idx_window": idx_window, "bbox": bbox},
        variables=asset.get("variables", []),
    )
    recommendation = recommend_access_pattern(evidence, asset, options, subset_cost)

    return {
        "source": "mcp_ready_local_tools",
        "live_metadata": live,
        "cmr_collection": cmr_collection,
        "cmr_granule": cmr_granule,
        "asset_inspection": asset,
        "access_options": options,
        "subset_cost": subset_cost,
        "recommendation": recommendation,
    }


def merge_metadata_urls(base: dict[str, Any], granule: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("s3_urls", "https_urls", "zarr_urls"):
        merged[key] = sorted(set(merged.get(key, []) + granule.get(key, [])))
    merged["granule_ur"] = granule.get("granule_ur") or merged.get("granule_ur", "")
    return merged


def recommend_access_pattern(
    evidence: dict[str, Any],
    asset: dict[str, Any],
    options: dict[str, Any],
    subset_cost: dict[str, Any],
) -> dict[str, Any]:
    file_format = asset.get("format")
    direct_s3 = options.get("direct_s3", False)
    recommendations: list[str] = []

    if direct_s3 and file_format in {"netcdf", "zarr"}:
        recommendations.append("direct_s3_xarray")
    if direct_s3 and file_format == "hdf5":
        recommendations.append("direct_s3_h5py")
    if file_format in {"geotiff", "cog"}:
        recommendations.append("rasterio_windowed_read")
    if options.get("zarr"):
        recommendations.append("zarr_open_zarr")
    if not recommendations and options.get("https"):
        recommendations.append("https_streaming")
    if not recommendations:
        recommendations.append("https_download_fallback")

    avoid = []
    if subset_cost.get("risk") in {"low", "medium"}:
        avoid.append("full_download")
        avoid.append("full_output_write")

    return {
        "recommended_strategies": recommendations,
        "avoid": avoid,
        "reason": build_reason(file_format, direct_s3, subset_cost),
    }


def build_reason(file_format: str, direct_s3: bool, subset_cost: dict[str, Any]) -> str:
    parts = []
    if direct_s3:
        parts.append("direct S3 URLs are available")
    if file_format and file_format != "unknown":
        parts.append(f"asset format appears to be {file_format}")
    if subset_cost.get("risk") != "unknown":
        parts.append(f"subset cost risk is {subset_cost.get('risk')}")
    return "; ".join(parts) if parts else "insufficient metadata, using conservative fallback"
