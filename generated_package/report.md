# Generator Report: nisar_access_subset

## Summary

- Algorithm name: `nisar_access_subset`
- Version: `main`
- Target: `both`
- Entrypoint: `nisar_access_subset.py`
- Runtime: `python`
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
| `access_mode` | `string` | `auto` | Prefer s3 in DPS, or https when non-interactive Earthdata credentials are available. |
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
| `bbox` | `string` | `` | Optional minx,miny,maxx,maxy subset bounding box. |
| `bbox_crs` | `string` | `` | CRS for bbox, for example EPSG:32633. |
| `out_name` | `string` | `nisar_subset.zarr` |  |

## Static Analysis

- Findings: none
- Source kind: `script` with `1` code unit(s)
- Data access:
  - `s3`: 4 signal(s)
  - `stac`: 0 signal(s)
  - `cmr`: 3 signal(s)
  - `local`: 0 signal(s)

## LLM-Assisted Analysis

- Status: `not_requested`
- Message: Pass --llm-analysis with OPENAI_API_KEY or ANTHROPIC_API_KEY to run the optional semantic analysis pass. The prompt is saved for manual ChatGPT review.

## Implicit Dependencies

- conda: `boto3`
- conda: `botocore`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `numcodecs<0.16`
- conda: `pyyaml`
- conda: `requests`
- conda: `zarr<3`

## Resolved Dependencies

- conda: `python=3.11`
- conda: `boto3`
- conda: `botocore`
- conda: `earthaccess`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `h5py`
- conda: `numcodecs<0.16`
- conda: `numpy`
- conda: `pyproj`
- conda: `pyyaml`
- conda: `requests`
- conda: `s3fs`
- conda: `xarray`
- conda: `zarr<3`
- conda: `pip`
- pip: `maap-py`

## Generated Files

- `nisar_access_subset.py`
- `run.sh`
- `env.yml`
- `Dockerfile`
- `algorithm_config.yaml`
- `algorithm.yml`
- `application.cwl`
- `workflow.cwl`
- `build.sh`
- `requirements.txt`
- `analysis.json`
- `llm_analysis_prompt.json`
- `stac-input.json`
- `stac-output.json`
- `validate_package.sh`
- `register_dps.py`
- `publish_ogc.py`
- `README.md`
- `report.md`

## Machine-Readable Summary

```json
{
  "name": "nisar_access_subset",
  "version": "main",
  "target": "both",
  "entrypoint": "nisar_access_subset.py",
  "runtime": {
    "type": "python",
    "output_argument": "--out_dir"
  },
  "inference": {
    "mode": "python_only",
    "source": "input/nisar_access_subset.py",
    "source_kind": "script",
    "parameters_cell_index": null,
    "manifest_required": false,
    "manifest_override": "input/app.yaml"
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
      "description": "Prefer s3 in DPS, or https when non-interactive Earthdata credentials are available.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--access_mode"
    },
    "https_href": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--https_href"
    },
    "s3_href": {
      "type": "string",
      "default": "",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--s3_href"
    },
    "short_name": {
      "type": "string",
      "default": "NISAR_L2_GCOV_BETA_V1",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--short_name"
    },
    "count": {
      "type": "integer",
      "default": "10",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--count"
    },
    "granule_index": {
      "type": "integer",
      "default": "0",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--granule_index"
    },
    "asf_s3_creds_url": {
      "type": "string",
      "default": "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--asf_s3_creds_url"
    },
    "group": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--group"
    },
    "vars": {
      "type": "string",
      "default": "HHHH",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--vars"
    },
    "x_path": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA/xCoordinates",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--x_path"
    },
    "y_path": {
      "type": "string",
      "default": "/science/LSAR/GCOV/grids/frequencyA/yCoordinates",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--y_path"
    },
    "bbox": {
      "type": "string",
      "default": "",
      "description": "Optional minx,miny,maxx,maxy subset bounding box.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--bbox"
    },
    "bbox_crs": {
      "type": "string",
      "default": "",
      "description": "CRS for bbox, for example EPSG:32633.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--bbox_crs"
    },
    "out_name": {
      "type": "string",
      "default": "nisar_subset.zarr",
      "description": "",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--out_name"
    }
  },
  "analysis": {
    "source_kind": "script",
    "code_cell_count": 1,
    "parameters_cell_index": null,
    "data_access": {
      "s3": [
        {
          "evidence": "import s3fs",
          "location": "imports"
        },
        {
          "evidence": "https://nisar.asf.earthdatacloud.nasa.gov/s3credentials",
          "location": "line 33"
        },
        {
          "evidence": "s3fs.S3FileSystem",
          "location": "line 375"
        },
        {
          "evidence": "maap.aws.earthdata_s3_credentials",
          "location": "line 294"
        }
      ],
      "stac": [],
      "cmr": [
        {
          "evidence": "import earthaccess",
          "location": "imports"
        },
        {
          "evidence": "import maap",
          "location": "imports"
        },
        {
          "evidence": "earthaccess.search_data",
          "location": "line 159"
        }
      ],
      "local": []
    },
    "issues": [],
    "parse_errors": [],
    "lint_tools": {
      "executed": [],
      "recommended": [
        "ruff",
        "flake8",
        "mypy"
      ],
      "note": "Install these tools in CI to enforce the same reproducibility checks automatically."
    }
  },
  "llm_analysis": {
    "status": "not_requested",
    "message": "Pass --llm-analysis with OPENAI_API_KEY or ANTHROPIC_API_KEY to run the optional semantic analysis pass. The prompt is saved for manual ChatGPT review."
  },
  "implicit_dependencies": {
    "conda": [
      "boto3",
      "botocore",
      "fsspec",
      "h5netcdf",
      "numcodecs<0.16",
      "pyyaml",
      "requests",
      "zarr<3"
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
      "numcodecs<0.16",
      "numpy",
      "pyproj",
      "pyyaml",
      "requests",
      "s3fs",
      "xarray",
      "zarr<3",
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
    "Dockerfile",
    "algorithm_config.yaml",
    "algorithm.yml",
    "application.cwl",
    "workflow.cwl",
    "build.sh",
    "requirements.txt",
    "analysis.json",
    "llm_analysis_prompt.json",
    "stac-input.json",
    "stac-output.json",
    "validate_package.sh",
    "register_dps.py",
    "publish_ogc.py",
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
