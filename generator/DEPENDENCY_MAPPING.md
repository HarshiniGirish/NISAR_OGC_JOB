# Dependency Mapping

The generator reads imports from the user Python file with the Python AST and
maps them to installable packages using `dependency_map.yml`.

| Python import | Generated package dependency | Notes |
| --- | --- | --- |
| `numpy` | `numpy` | Numerical array operations. |
| `xarray` | `xarray` | Dataset abstraction; also triggers implicit `zarr<3`/`numcodecs<0.16` when `.to_zarr(...)` is detected. |
| `zarr` | `zarr<3` | Stable Zarr v2 output support; avoids Zarr v3 async shutdown warnings in ADE demos. |
| `h5py` | `h5py` | HDF5 access; this NISAR example also adds `h5netcdf` implicitly. |
| `h5netcdf` | `h5netcdf` | NetCDF/HDF5 backend compatibility. |
| `fsspec` | `fsspec` | Filesystem abstraction. |
| `s3fs` | `s3fs` | S3 filesystem access; also adds `fsspec`, `boto3`, and `botocore`. |
| `requests` | `requests` | HTTP requests. |
| `earthaccess` | `earthaccess` | Earthdata search and authentication; also adds `requests`. |
| `pyproj` | `pyproj` | CRS parsing and bbox transformation. |
| `boto3` | `boto3` | AWS SDK used by S3 workflows. |
| `botocore` | `botocore` | Low-level AWS dependency used with S3 workflows. |
| `maap` | `maap-py` | MAAP Python API; installed with pip. |
| `rasterio` | `rasterio` | Raster/geospatial IO support. |
| `geopandas` | `geopandas` | Vector geospatial support. |
| `shapely` | `shapely` | Geometry operations. |

Standard library imports such as `argparse`, `json`, `os`, `pathlib`,
`shutil`, `sys`, `tempfile`, and `typing` map to `null` in
`dependency_map.yml` and are intentionally not added to `env.yml`.

## Why implicit dependencies exist

Some dependencies are required even when they are not imported directly:

| Detected pattern | Extra generated dependency |
| --- | --- |
| `.to_zarr(...)` | `zarr<3`, `numcodecs<0.16` |
| `s3fs` import | `fsspec`, `boto3`, `botocore` |
| `earthaccess` import | `requests` |
| `h5py` import | `h5netcdf` |
