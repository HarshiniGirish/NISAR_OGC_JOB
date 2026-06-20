from __future__ import annotations

import re
from pathlib import Path
from typing import Any


URL_RE = re.compile(r"(?:s3://|https?://)[^\s\"')\],]+")
COLLECTION_RE = re.compile(r"\b[A-Z0-9]+(?:_[A-Z0-9]+)+(?:-[A-Z0-9]+)?_V\d+\b")


def build_access_evidence(
    *,
    source_info: dict[str, Any],
    app_config: dict[str, Any],
    analysis: dict[str, Any],
    detected_imports: list[str],
) -> dict[str, Any]:
    source = source_info.get("source", "")
    urls = sorted(set(URL_RE.findall(source) + urls_from_analysis(analysis)))
    collections = sorted(set(collections_from_source(source) + collections_from_inputs(app_config)))
    file_formats = sorted(infer_file_formats(urls, detected_imports, source))
    operations = sorted(infer_operations(source, detected_imports, app_config))

    return {
        "source": {
            "kind": source_info.get("kind"),
            "path": str(source_info.get("path", "")),
            "entrypoint": app_config.get("entrypoint", ""),
        },
        "imports": sorted(detected_imports),
        "urls": urls,
        "collections": collections,
        "file_formats": file_formats,
        "operations": operations,
        "inputs": app_config.get("inputs", {}),
        "outputs": app_config.get("outputs", {}),
        "resources": app_config.get("resources", {}),
        "data_access": analysis.get("data_access", {}),
        "issues": analysis.get("issues", []),
    }


def urls_from_analysis(analysis: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for items in analysis.get("data_access", {}).values():
        for item in items:
            evidence = str(item.get("evidence", ""))
            urls.extend(URL_RE.findall(evidence))
    return urls


def collections_from_source(source: str) -> list[str]:
    return COLLECTION_RE.findall(source)


def collections_from_inputs(app_config: dict[str, Any]) -> list[str]:
    collections: list[str] = []
    for config in app_config.get("inputs", {}).values():
        default = str(config.get("default", ""))
        collections.extend(COLLECTION_RE.findall(default))
    return collections


def infer_file_formats(urls: list[str], imports: list[str], source: str) -> set[str]:
    formats: set[str] = set()
    suffixes = {Path(url.split("?", 1)[0]).suffix.lower() for url in urls}

    if ".nc" in suffixes or "open_dataset" in source:
        formats.add("netcdf")
    if {".h5", ".hdf5"}.intersection(suffixes) or "h5py" in imports:
        formats.add("hdf5")
    if ".tif" in suffixes or ".tiff" in suffixes:
        formats.add("geotiff")
    if "tilejson" in source or any("tilejson" in url.lower() for url in urls):
        formats.add("tilejson")
    if any(".zarr" in url.lower() for url in urls) or "open_zarr" in source or "to_zarr" in source:
        formats.add("zarr")
    if "rasterio" in imports or "rioxarray" in imports or "driver=\"COG\"" in source or "driver='COG'" in source:
        formats.add("cog")

    return formats


def infer_operations(source: str, imports: list[str], app_config: dict[str, Any]) -> set[str]:
    operations: set[str] = set()
    inputs = app_config.get("inputs", {})

    if any(name in inputs for name in ("bbox", "bbox_crs")) or "clip_box" in source:
        operations.add("spatial_subset")
    if any(name in inputs for name in ("idx_window", "window")) or "isel(" in source:
        operations.add("index_subset")
    if "to_zarr" in source:
        operations.add("write_zarr")
    if "to_raster" in source or "driver=\"COG\"" in source or "driver='COG'" in source:
        operations.add("write_cog")
    if "searchGranule" in source or "search_granule" in source or "search_data" in source:
        operations.add("cmr_search")
    if "s3://" in source or "s3fs" in imports or "S3FileSystem" in source:
        operations.add("direct_s3")
    if "https://" in source:
        operations.add("https_access")
    if "pystac_client" in imports or "Client.open" in source or "STAC_API" in source:
        operations.add("stac_search")
    if "tilejson" in source or "RASTER_API" in source or "/api/raster" in source:
        operations.add("raster_api")

    return operations
