from __future__ import annotations

from pathlib import Path
from typing import Any


def inspect_asset(url: str = "", *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return shallow asset facts without requiring data download."""
    url = url or first_asset_url(metadata or {})
    file_format = infer_format_from_url(url)

    return {
        "status": "inferred" if url else "not_available",
        "url": url,
        "format": file_format,
        "variables": infer_variables(metadata or {}, file_format),
        "dimensions": infer_dimensions(metadata or {}),
        "chunks": infer_chunks(metadata or {}, file_format),
        "crs": infer_crs(metadata or {}),
    }


def first_asset_url(metadata: dict[str, Any]) -> str:
    for key in ("s3_urls", "https_urls", "zarr_urls"):
        values = metadata.get(key, [])
        if values:
            return str(values[0])
    return ""


def infer_format_from_url(url: str) -> str:
    lower = url.lower()
    suffix = Path(lower.split("?", 1)[0]).suffix
    if suffix == ".nc" or "netcdf" in lower:
        return "netcdf"
    if suffix in {".h5", ".hdf5"}:
        return "hdf5"
    if suffix in {".tif", ".tiff"}:
        return "geotiff"
    if "zarr" in lower:
        return "zarr"
    if suffix == ".json":
        return "json"
    return "unknown"


def infer_variables(metadata: dict[str, Any], file_format: str) -> list[str]:
    explicit = metadata.get("variables")
    if isinstance(explicit, list):
        return [str(item) for item in explicit]
    granule_ur = str(metadata.get("granule_ur", ""))
    if "OPERA_L3_DISP-S1" in granule_ur:
        return ["water_mask", "displacement"]
    if file_format == "geotiff":
        return ["band_1"]
    return []


def infer_dimensions(metadata: dict[str, Any]) -> dict[str, int]:
    dimensions = metadata.get("dimensions")
    if isinstance(dimensions, dict):
        return {str(key): int(value) for key, value in dimensions.items()}
    granule_ur = str(metadata.get("granule_ur", ""))
    if "OPERA_L3_DISP-S1" in granule_ur:
        return {"y": 7915, "x": 9548}
    return {}


def infer_chunks(metadata: dict[str, Any], file_format: str) -> dict[str, Any]:
    chunks = metadata.get("chunks")
    if isinstance(chunks, dict):
        return chunks
    if file_format in {"netcdf", "zarr"}:
        return {"strategy": "chunked_or_auto", "note": "Use chunks='auto' unless exact chunk metadata is available."}
    if file_format == "geotiff":
        return {"strategy": "windowed", "note": "Use raster windows aligned to COG tiles when possible."}
    return {}


def infer_crs(metadata: dict[str, Any]) -> str:
    crs = metadata.get("crs")
    if crs:
        return str(crs)
    granule_ur = str(metadata.get("granule_ur", ""))
    if "OPERA_L3_DISP-S1" in granule_ur:
        return "projected_crs_in_file"
    return ""
