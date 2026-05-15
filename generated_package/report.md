# Generator Report: nisar_access_subset

## Summary

- Algorithm name: `nisar_access_subset`
- Version: `main`
- Target: `ogc`
- Entrypoint: `nisar_access_subset.py`
- Generation mode: `python_only`
- Manifest required: `False`

## Detected Imports

- `argparse`
- `earthaccess`
- `h5py`
- `json`
- `maap`
- `numpy`
- `os`
- `pyproj`
- `s3fs`
- `shutil`
- `sys`
- `tempfile`
- `typing`
- `xarray`

## Inferred CLI Inputs

| Input | Type | Default | Description |
| --- | --- | --- | --- |
| `access_mode` | `string` | `auto` | Allowed values: auto, s3, https. |
| `https_href` | `string` | `` |  |
| `s3_href` | `string` | `` |  |
| `short_name` | `string` | `NISAR_L2_GCOV_BETA_V1` |  |
| `count` | `integer` | `10` |  |
| `granule_index` | `integer` | `0` |  |
| `asf_s3_creds_url` | `string` | `https://nisar.asf.earthdatacloud.nasa.gov/s3credentials` |  |
| `group` | `string` | `/science/LSAR/GCOV/grids/frequencyA` |  |
| `vars` | `string` | `HHHH` |  |
| `x_path` | `string` | `/science/LSAR/GCOV/grids/frequencyA/xCoordinates` |  |
| `y_path` | `string` | `/science/LSAR/GCOV/grids/frequencyA/yCoordinates` |  |
| `bbox` | `string` | `` |  |
| `bbox_crs` | `string` | `` |  |
| `out_name` | `string` | `nisar_subset.zarr` |  |

## Implicit Dependencies

- conda: `boto3`
- conda: `botocore`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `numcodecs`
- conda: `requests`
- conda: `zarr`

## Resolved Dependencies

- conda: `python=3.11`
- conda: `boto3`
- conda: `botocore`
- conda: `earthaccess`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `h5py`
- conda: `numcodecs`
- conda: `numpy`
- conda: `pyproj`
- conda: `requests`
- conda: `s3fs`
- conda: `xarray`
- conda: `zarr`
- conda: `pip`
- pip: `maap-py`

## Generated Files

- `nisar_access_subset.py`
- `run.sh`
- `env.yml`
- `algorithm.yml`
- `Dockerfile`
- `nisar_access_subset.cwl`
- `build.sh`
- `requirements.txt`
- `README.md`
- `report.md`

## Machine-Readable Summary

```json
{
  "name": "nisar_access_subset",
  "version": "main",
  "target": "ogc",
  "entrypoint": "nisar_access_subset.py",
  "inference": {
    "mode": "python_only",
    "source": "input/nisar_access_subset.py",
    "manifest_required": false
  },
  "detected_imports": [
    "argparse",
    "earthaccess",
    "h5py",
    "json",
    "maap",
    "numpy",
    "os",
    "pyproj",
    "s3fs",
    "shutil",
    "sys",
    "tempfile",
    "typing",
    "xarray"
  ],
  "inferred_inputs": {
    "access_mode": {
      "type": "string",
      "default": "auto",
      "description": "Allowed values: auto, s3, https.",
      "inferred": true
    },
    "https_href": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true
    },
    "s3_href": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true
    },
    "short_name": {
      "type": "string",
      "default": "NISAR_L2_GCOV_BETA_V1",
      "description": "",
      "inferred": true
    },
    "count": {
      "type": "integer",
      "default": "10",
      "description": "",
      "inferred": true
    },
    "granule_index": {
      "type": "integer",
      "default": "0",
      "description": "",
      "inferred": true
    },
    "asf_s3_creds_url": {
      "type": "string",
      "default": "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials",
      "description": "",
      "inferred": true
    },
    "group": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA",
      "description": "",
      "inferred": true
    },
    "vars": {
      "type": "string",
      "default": "HHHH",
      "description": "",
      "inferred": true
    },
    "x_path": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA/xCoordinates",
      "description": "",
      "inferred": true
    },
    "y_path": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA/yCoordinates",
      "description": "",
      "inferred": true
    },
    "bbox": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true
    },
    "bbox_crs": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true
    },
    "out_name": {
      "type": "string",
      "default": "nisar_subset.zarr",
      "description": "",
      "inferred": true
    }
  },
  "implicit_dependencies": {
    "conda": [
      "boto3",
      "botocore",
      "fsspec",
      "h5netcdf",
      "numcodecs",
      "requests",
      "zarr"
    ],
    "pip": []
  },
  "resolved_dependencies": {
    "conda": [
      "python=3.11",
      "boto3",
      "botocore",
      "earthaccess",
      "fsspec",
      "h5netcdf",
      "h5py",
      "numcodecs",
      "numpy",
      "pyproj",
      "requests",
      "s3fs",
      "xarray",
      "zarr",
      "pip"
    ],
    "pip": [
      "maap-py"
    ]
  },
  "generated_files": [
    "nisar_access_subset.py",
    "run.sh",
    "env.yml",
    "algorithm.yml",
    "Dockerfile",
    "nisar_access_subset.cwl",
    "build.sh",
    "requirements.txt",
    "README.md",
    "report.md"
  ],
  "notes": [
    "This package was generated from the Python file without requiring app.yml.",
    "The generated files should be reviewed before OGC execution or MAAP registration.",
    "Scientific correctness remains the responsibility of the algorithm author."
  ]
}
```
