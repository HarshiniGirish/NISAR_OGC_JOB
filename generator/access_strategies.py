from __future__ import annotations

from typing import Any


ALLOWED_STRATEGIES: dict[str, dict[str, Any]] = {
    "direct_s3_xarray": {
        "description": "Open cloud-hosted NetCDF/Zarr assets directly from S3 with s3fs and xarray.",
        "required_dependencies": ["s3fs", "xarray"],
        "valid_formats": ["netcdf", "zarr"],
        "template_hint": "s3fs_xarray_chunks",
    },
    "direct_s3_h5py": {
        "description": "Open cloud-hosted HDF5 assets from S3 after temporary credentials are resolved.",
        "required_dependencies": ["s3fs", "h5py"],
        "valid_formats": ["hdf5", "h5"],
        "template_hint": "s3fs_h5py_subset",
    },
    "direct_s3_rasterio": {
        "description": "Read raster assets directly from S3 with rasterio/GDAL range requests.",
        "required_dependencies": ["rasterio", "s3fs"],
        "valid_formats": ["geotiff", "cog"],
        "template_hint": "rasterio_s3",
    },
    "rasterio_windowed_read": {
        "description": "Use rasterio windows/bounds to read only the requested raster subset.",
        "required_dependencies": ["rasterio"],
        "valid_formats": ["geotiff", "cog"],
        "template_hint": "rasterio_window",
    },
    "zarr_open_zarr": {
        "description": "Use xarray.open_zarr for chunk-aware access to Zarr assets.",
        "required_dependencies": ["xarray", "zarr"],
        "valid_formats": ["zarr"],
        "template_hint": "xarray_open_zarr",
    },
    "virtual_zarr_access": {
        "description": "Use virtual references/metadata when available to avoid full conversion or download.",
        "required_dependencies": ["xarray"],
        "valid_formats": ["netcdf", "hdf5", "zarr"],
        "template_hint": "virtual_access",
    },
    "harmony_subset": {
        "description": "Use Harmony service subsetting/reformatting before local processing.",
        "required_dependencies": ["requests"],
        "valid_formats": ["netcdf", "hdf5", "geotiff"],
        "template_hint": "harmony_request",
    },
    "https_streaming": {
        "description": "Stream remote HTTPS assets with authenticated sessions and range-capable readers.",
        "required_dependencies": ["requests"],
        "valid_formats": ["netcdf", "hdf5", "geotiff"],
        "template_hint": "https_stream",
    },
    "https_download_fallback": {
        "description": "Download assets only when direct S3, Harmony, or virtual access is unavailable.",
        "required_dependencies": ["requests"],
        "valid_formats": ["netcdf", "hdf5", "geotiff", "zarr"],
        "template_hint": "download_then_process",
    },
    "cmr_search_then_s3": {
        "description": "Use CMR/earthaccess/MAAP to find granules, then prefer direct S3 links.",
        "required_dependencies": ["earthaccess"],
        "valid_formats": ["netcdf", "hdf5", "geotiff", "zarr"],
        "template_hint": "cmr_to_s3",
    },
}


def allowed_strategy_ids() -> list[str]:
    return sorted(ALLOWED_STRATEGIES)
