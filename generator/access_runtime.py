from __future__ import annotations

import json
from typing import Any


def build_access_runtime_module(access_plan: dict[str, Any], dataset_facts: dict[str, Any]) -> str:
    """Render a strategy-specific helper module for generated packages."""
    strategy = str(access_plan.get("chosen_strategy") or "https_download_fallback")
    helpers = {
        "direct_s3_xarray": DIRECT_S3_XARRAY_HELPER,
        "direct_s3_h5py": DIRECT_S3_H5PY_HELPER,
        "direct_s3_rasterio": RASTERIO_WINDOW_HELPER,
        "rasterio_windowed_read": RASTERIO_WINDOW_HELPER,
        "zarr_open_zarr": ZARR_OPEN_HELPER,
        "virtual_zarr_access": ZARR_OPEN_HELPER,
        "harmony_subset": HARMONY_HELPER,
        "https_streaming": HTTPS_HELPER,
        "https_download_fallback": HTTPS_HELPER,
        "cmr_search_then_s3": CMR_TO_S3_HELPER,
        "stac_raster_api": STAC_RASTER_API_HELPER,
    }
    helper = helpers.get(strategy, HTTPS_HELPER)
    header = f'''#!/usr/bin/env python3
"""Strategy-specific data access helpers generated from access_plan.json.

These helpers are intentionally optional: generated science scripts keep their
existing logic, while this module provides reusable, validated access patterns
selected by the access planner.
"""

from __future__ import annotations

ACCESS_STRATEGY = {json.dumps(strategy)}
ACCESS_PLAN = {json.dumps(slim_plan(access_plan), indent=2)}
DATASET_FACTS_SUMMARY = {json.dumps(slim_facts(dataset_facts), indent=2)}


def describe_access_strategy() -> dict:
    """Return the selected access strategy and compact supporting facts."""
    return {{
        "strategy": ACCESS_STRATEGY,
        "access_plan": ACCESS_PLAN,
        "dataset_facts": DATASET_FACTS_SUMMARY,
    }}

'''
    return header + helper


def slim_plan(access_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": access_plan.get("source"),
        "planner_status": access_plan.get("planner_status"),
        "fallback_used": access_plan.get("fallback_used"),
        "chosen_strategy": access_plan.get("chosen_strategy"),
        "reasoning": access_plan.get("reasoning"),
        "implementation_hints": access_plan.get("implementation_hints", []),
        "warnings": access_plan.get("warnings", []),
    }


def slim_facts(dataset_facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": dataset_facts.get("source"),
        "live_metadata": dataset_facts.get("live_metadata"),
        "asset_format": dataset_facts.get("asset_inspection", {}).get("format"),
        "variables": dataset_facts.get("asset_inspection", {}).get("variables", []),
        "dimensions": dataset_facts.get("asset_inspection", {}).get("dimensions", {}),
        "access_options": dataset_facts.get("access_options", {}),
        "subset_cost": dataset_facts.get("subset_cost", {}),
        "recommendation": dataset_facts.get("recommendation", {}),
    }


DIRECT_S3_XARRAY_HELPER = '''
def open_xarray_dataset_from_s3(
    url: str,
    credentials: dict,
    *,
    engine: str = "h5netcdf",
    chunks: str | dict = "auto",
    **open_kwargs,
):
    """Open a cloud-hosted NetCDF/Zarr-like asset directly from S3 with xarray."""
    import s3fs
    import xarray as xr

    fs = s3fs.S3FileSystem(
        anon=False,
        key=credentials["accessKeyId"],
        secret=credentials["secretAccessKey"],
        token=credentials.get("sessionToken"),
    )
    with fs.open(url, "rb") as file_obj:
        return xr.open_dataset(
            file_obj,
            engine=engine,
            chunks=chunks,
            cache=False,
            **open_kwargs,
        )
'''


DIRECT_S3_H5PY_HELPER = '''
def download_s3_asset_to_tempfile(url: str, credentials: dict, *, suffix: str = ".h5") -> str:
    """Download an S3 HDF5 asset to a local tempfile for h5py-based readers."""
    import tempfile
    import s3fs

    fs = s3fs.S3FileSystem(
        anon=False,
        key=credentials["accessKeyId"],
        secret=credentials["secretAccessKey"],
        token=credentials.get("sessionToken"),
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    fs.get(url, tmp.name)
    return tmp.name


def open_hdf5_file(path: str, mode: str = "r", **kwargs):
    """Open an HDF5 file with h5py using caller-supplied cache/page settings."""
    import h5py

    return h5py.File(path, mode, **kwargs)
'''


RASTERIO_WINDOW_HELPER = '''
def read_raster_window(url: str, *, bounds=None, window=None, indexes=1, **open_kwargs):
    """Read only a raster window or bounds subset with rasterio."""
    import rasterio
    from rasterio.windows import from_bounds

    with rasterio.open(url, **open_kwargs) as src:
        read_window = window
        if read_window is None and bounds is not None:
            read_window = from_bounds(*bounds, transform=src.transform)
        data = src.read(indexes, window=read_window)
        profile = src.profile.copy()
        if read_window is not None:
            profile.update(
                width=int(read_window.width),
                height=int(read_window.height),
                transform=src.window_transform(read_window),
            )
        return data, profile
'''


ZARR_OPEN_HELPER = '''
def open_zarr_dataset(url: str, *, consolidated: bool | None = None, chunks="auto", **kwargs):
    """Open a Zarr asset with xarray using chunk-aware access."""
    import xarray as xr

    return xr.open_zarr(url, consolidated=consolidated, chunks=chunks, **kwargs)
'''


HARMONY_HELPER = '''
def build_harmony_subset_request(collection_id: str, *, bbox: str = "", temporal: str = "", variables=None):
    """Build a Harmony-style subset request payload for downstream clients."""
    payload = {"collection_id": collection_id}
    if bbox:
        payload["bbox"] = bbox
    if temporal:
        payload["temporal"] = temporal
    if variables:
        payload["variables"] = list(variables)
    return payload
'''


HTTPS_HELPER = '''
def download_https_asset(url: str, destination: str, *, session=None, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Download an HTTPS asset as a conservative fallback access pattern."""
    import requests

    client = session or requests.Session()
    with client.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with open(destination, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    file_obj.write(chunk)
    return destination
'''


CMR_TO_S3_HELPER = '''
def choose_preferred_s3_url(related_urls: list[str]) -> str:
    """Choose the first direct S3 URL from CMR related URLs."""
    for url in related_urls:
        if str(url).startswith("s3://"):
            return str(url)
    raise ValueError("No s3:// URL found in related URLs.")
'''


STAC_RASTER_API_HELPER = '''
def fetch_stac_item_tilejson(
    *,
    stac_api_url: str,
    raster_api_url: str,
    collection_id: str,
    date: str,
    assets: str | None = None,
    rescale: str | None = None,
    colormap_name: str | None = None,
) -> dict:
    """Find a STAC item and request TileJSON from a VEDA/titiler-style Raster API."""
    import requests
    from pystac_client import Client

    client = Client.open(stac_api_url)
    results = client.search(collections=[collection_id], datetime=date)
    items = list(results.items())
    if not items:
        raise RuntimeError(f"No STAC items found for {collection_id} at {date}")

    item = items[0]
    collection = item.get_collection()
    if assets is None:
        render = collection.extra_fields.get("renders", {}).get("dashboard", {})
        render_assets = render.get("assets") or []
        assets = render_assets[0] if render_assets else next(iter(item.assets))
        if rescale is None and render.get("rescale"):
            first_rescale = render["rescale"][0]
            rescale = f"{first_rescale[0]},{first_rescale[1]}"

    params = {"assets": assets}
    if rescale:
        params["rescale"] = rescale
    if colormap_name:
        params["colormap_name"] = colormap_name

    url = (
        f"{raster_api_url.rstrip('/')}/collections/{collection_id}"
        f"/items/{item.id}/WebMercatorQuad/tilejson.json"
    )
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    tilejson = response.json()
    tilejson["_stac_item_id"] = item.id
    tilejson["_collection_id"] = collection_id
    tilejson["_assets"] = assets
    return tilejson
'''
