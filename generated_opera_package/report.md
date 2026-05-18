# Generator Report: opera_water_mask_to_cog

## Summary

- Algorithm name: `opera_water_mask_to_cog`
- Version: `ogc`
- Target: `both`
- Entrypoint: `opera_access_structure.py`
- Runtime: `python`
- Generation mode: `python_only`
- Manifest required: `False`

## Detected Imports

- `__future__`
- `argparse`
- `json`
- `maap`
- `numpy`
- `os`
- `pyproj`
- `requests`
- `rioxarray`
- `s3fs`
- `shapely`
- `typing`
- `xarray`
- `xml`

## Inferred CLI Inputs

| Input | Type | Default | Description |
| --- | --- | --- | --- |
| `short_name` | `string` | `OPERA_L3_DISP-S1_V1` | CMR short name for OPERA DISP-S1. |
| `temporal` | `string` | `2016-07-01T00:00:00Z,2024-12-31T23:59:59Z` | Optional CMR temporal range. |
| `bbox` | `string` | `` | Optional WGS84 bbox minx,miny,maxx,maxy. |
| `limit` | `integer` | `10` | Maximum granules to search. |
| `granule_ur` | `string` | `` | Optional fixed CMR GranuleUR. |
| `tile` | `integer` | `256` | COG tile size. |
| `compress` | `string` | `DEFLATE` | COG compression method. |
| `overview_resampling` | `string` | `nearest` | COG overview resampling method. |
| `out_name` | `string` | `water_mask_subset.cog.tif` | Output COG filename. |
| `idx_window` | `string` | `0:1024,0:1024` | Optional index window y0:y1,x0:x1 for smoke tests. |
| `s3_url` | `string` | `` | Optional direct s3:// granule URL to bypass CMR search. |

## Static Analysis

- Findings: none
- Source kind: `script` with `1` code unit(s)
- Data access:
  - `s3`: 14 signal(s)
  - `stac`: 0 signal(s)
  - `cmr`: 7 signal(s)
  - `local`: 1 signal(s)

## LLM-Assisted Analysis

- Status: `not_requested`
- Message: Pass --llm-analysis with OPENAI_API_KEY or ANTHROPIC_API_KEY to run the optional semantic analysis pass. The prompt is saved for manual ChatGPT review.

## Implicit Dependencies

- conda: `boto3`
- conda: `botocore`
- conda: `dask`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `netcdf4`
- conda: `pyyaml`
- conda: `rasterio`
- conda: `rioxarray`
- conda: `scipy`

## Resolved Dependencies

- conda: `python=3.11`
- conda: `boto3`
- conda: `botocore`
- conda: `dask`
- conda: `fsspec`
- conda: `h5netcdf`
- conda: `netcdf4`
- conda: `numpy`
- conda: `pyproj`
- conda: `pyyaml`
- conda: `rasterio`
- conda: `requests`
- conda: `rioxarray`
- conda: `s3fs`
- conda: `scipy`
- conda: `shapely`
- conda: `xarray`
- conda: `pip`
- pip: `maap-py`

## Generated Files

- `opera_access_structure.py`
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
  "name": "opera_water_mask_to_cog",
  "version": "ogc",
  "target": "both",
  "entrypoint": "opera_access_structure.py",
  "runtime": {
    "type": "python",
    "output_argument": "--dest"
  },
  "inference": {
    "mode": "python_only",
    "source": "input/opera_access_structure.py",
    "source_kind": "script",
    "parameters_cell_index": null,
    "manifest_required": false,
    "manifest_override": "input/app_opera.yaml"
  },
  "detected_imports": [
    "__future__",
    "argparse",
    "json",
    "maap",
    "numpy",
    "os",
    "pyproj",
    "requests",
    "rioxarray",
    "s3fs",
    "shapely",
    "typing",
    "xarray",
    "xml"
  ],
  "inferred_inputs": {
    "short_name": {
      "type": "string",
      "default": "OPERA_L3_DISP-S1_V1",
      "description": "CMR short name for OPERA DISP-S1.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--short-name"
    },
    "temporal": {
      "type": "string",
      "default": "2016-07-01T00:00:00Z,2024-12-31T23:59:59Z",
      "description": "Optional CMR temporal range.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--temporal"
    },
    "bbox": {
      "type": "string",
      "default": "",
      "description": "Optional WGS84 bbox minx,miny,maxx,maxy.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--bbox"
    },
    "limit": {
      "type": "integer",
      "default": 10,
      "description": "Maximum granules to search.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--limit"
    },
    "granule_ur": {
      "type": "string",
      "default": "",
      "description": "Optional fixed CMR GranuleUR.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--granule-ur"
    },
    "tile": {
      "type": "integer",
      "default": 256,
      "description": "COG tile size.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--tile"
    },
    "compress": {
      "type": "string",
      "default": "DEFLATE",
      "description": "COG compression method.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--compress"
    },
    "overview_resampling": {
      "type": "string",
      "default": "nearest",
      "description": "COG overview resampling method.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--overview-resampling"
    },
    "out_name": {
      "type": "string",
      "default": "water_mask_subset.cog.tif",
      "description": "Output COG filename.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--out-name"
    },
    "idx_window": {
      "type": "string",
      "default": "0:1024,0:1024",
      "description": "Optional index window y0:y1,x0:x1 for smoke tests.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--idx-window"
    },
    "s3_url": {
      "type": "string",
      "default": "",
      "description": "Optional direct s3:// granule URL to bypass CMR search.",
      "inferred": true,
      "source": "argparse",
      "cli_option": "--s3-url"
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
          "evidence": "maap.aws.earthdata_s3_credentials",
          "location": "line 225"
        },
        {
          "evidence": "S3FileSystem",
          "location": "line 232"
        },
        {
          "evidence": "maap.aws.earthdata_s3_credentials",
          "location": "line 177"
        },
        {
          "evidence": "maap.aws.earthdata_s3_credentials",
          "location": "line 327"
        },
        {
          "evidence": "s3://",
          "location": "line 206"
        },
        {
          "evidence": "s3://",
          "location": "line 98"
        },
        {
          "evidence": "s3://",
          "location": "line 110"
        },
        {
          "evidence": "s3://",
          "location": "line 196"
        },
        {
          "evidence": "s3://",
          "location": "line 201"
        },
        {
          "evidence": "s3://",
          "location": "line 120"
        },
        {
          "evidence": "s3://",
          "location": "line 124"
        },
        {
          "evidence": "s3://",
          "location": "line 86"
        },
        {
          "evidence": "s3://",
          "location": "line 90"
        }
      ],
      "stac": [],
      "cmr": [
        {
          "evidence": "import maap",
          "location": "imports"
        },
        {
          "evidence": "maap.searchCollection",
          "location": "line 133"
        },
        {
          "evidence": "cmr.earthdata.nasa.gov",
          "location": "line 138"
        },
        {
          "evidence": "maap.searchGranule",
          "location": "line 145"
        },
        {
          "evidence": "cmr.earthdata.nasa.gov",
          "location": "line 133"
        },
        {
          "evidence": "https://cmr.earthdata.nasa.gov/search/granules.xml",
          "location": "line 216"
        },
        {
          "evidence": "https://cmr.earthdata.nasa.gov/search/granules.umm_json",
          "location": "line 159"
        }
      ],
      "local": [
        {
          "evidence": "data_array.rio.to_raster",
          "location": "line 287"
        }
      ]
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
      "dask",
      "fsspec",
      "h5netcdf",
      "netcdf4",
      "pyyaml",
      "rasterio",
      "rioxarray",
      "scipy"
    ],
    "pip": []
  },
  "resolved_dependencies": {
    "conda": [
      "python=3.11",
      "boto3",
      "botocore",
      "dask",
      "fsspec",
      "h5netcdf",
      "netcdf4",
      "numpy",
      "pyproj",
      "pyyaml",
      "rasterio",
      "requests",
      "rioxarray",
      "s3fs",
      "scipy",
      "shapely",
      "xarray",
      "pip"
    ],
    "pip": [
      "maap-py"
    ]
  },
  "generated_files": [
    "opera_access_structure.py",
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
