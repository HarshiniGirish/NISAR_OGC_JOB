# NISAR_OGC_JOB: End-to-End Package Generation Workflow

## 1. Project Summary

This repository tests whether a normal Python science workflow can be analyzed and converted into a deployable MAAP DPS / OGC-style application package.

The project starts with an input science script, such as a NISAR GCOV subsetting script. The generator analyzes the script, detects dependencies and runtime inputs, renders package templates, and creates a generated package that can be validated, built, and run.

OpenAI analysis is optional. It is used only as an additional review layer to identify possible environment, credential, scaling, and reproducibility risks.

### End-to-End Package Generation Flow

```text
Input science script
        ↓
AST static analysis
        ↓
Dependency mapping
        ↓
Template rendering
        ↓
Generated package
        ↓
Validate, build, and run
```

---

## 2. NISAR Workflow

NISAR is the primary demonstration workflow in this repository.

The input script accesses a NISAR L2 GCOV granule, reads the GCOV HDF5 group, subsets variables such as `HHHH` using a bounding box, and writes a Zarr output plus a `manifest.json` file.

### NISAR Generated Package Runtime Flow

```text
Export Earthdata credentials
        ↓
Run bbox smoke test
        ↓
S3 access with fallback
        ↓
Read GCOV HDF5 group
        ↓
Subset HHHH by bbox
        ↓
Write Zarr + manifest
```

---

## 2.1 NISAR Staging Setup

Open the MAAP staging hub:

```text
https://staging.hub.maap-project.org/
```

Use the OGC/Pangeo workspace image:

```text
mas.uat.maap-project.org/root/maap-workspaces/2i2c/pangeo:ogc-v1.0
```

Clone the repository inside the workspace terminal:

```bash
git clone https://github.com/HarshiniGirish/NISAR_OGC_JOB
cd ~/NISAR_OGC_JOB
```

---

## 2.2 Generate the NISAR Package

From the repository root, run:

```bash
cd ~/NISAR_OGC_JOB
python3 generator/generate_package.py
```

Expected output is a generated package folder containing files such as:

```text
generated_package/
├── run.sh
├── build.sh
├── env.yml
├── Dockerfile
├── algorithm.yml
├── application.cwl
├── workflow.cwl
├── app.yaml
├── access_plan.json
├── dataset_facts.json
├── access_runtime.py
├── analysis.json
├── report.md
└── README.md
```

---

## 2.3 Export Credentials for NISAR Testing

Credentials are used only for local testing or smoke testing.

```bash
export EARTHDATA_USERNAME="your_username"
export EARTHDATA_PASSWORD="your_password"
```

---

## 2.4 Optional OpenAI Analysis and AI Access Planning

The OpenAI analysis is optional and is not required for package generation.

The main package is still created by the Python generator using static analysis, dependency mapping, strategy validation, and templates.

There are two optional OpenAI uses:

- `--ai-access-planner`: asks OpenAI to choose the best supported access strategy, then validates that choice and writes `access_plan.json`.
- `dataset_facts.json`: records MCP-ready dataset facts gathered from local tools, such as access options, inferred asset format, variables, and subset-cost risk.
- `access_runtime.py`: strategy-specific helper code generated from the validated access plan.
- `--llm-analysis`: asks OpenAI to review the generated package, static analysis, and access plan.

```bash
export OPENAI_API_KEY="your_new_key_here"

python3 generator/generate_package.py input/nisar_access_subset.py \
  --output-dir generated_package \
  --ai-access-planner \
  --access-planner-provider openai \
  --llm-analysis \
  --llm-provider openai
```

Use live CMR metadata lookups for dataset facts when network access is available:

```bash
python3 generator/generate_package.py input/opera_access_structure.py \
  --output-dir generated_opera_package \
  --live-dataset-facts \
  --ai-access-planner \
  --access-planner-provider openai
```

The optional analysis reviews the generated package metadata and report. It can flag issues such as:

```text
- Hidden environment assumptions
- Credential handling risks
- Unsafe defaults
- Scaling limitations
- Reproducibility concerns
```

If `--ai-access-planner` is omitted, the generator still writes
`access_plan.json` using deterministic fallback rules.

---

## 2.5 Validate, Build, and Run NISAR

Move into the generated package directory:

```bash
cd ~/NISAR_OGC_JOB/generated_package
```

Validate the package:

```bash
./validate_package.sh
```

Build the package:

```bash
./build.sh
```

Run the NISAR bbox smoke test:

```bash
./run.sh \
  --bbox "148325,5392805,158325,5402805" \
  --bbox_crs "EPSG:32633"
```

Expected outputs:

| Output checked | Expected result |
|---|---|
| Zarr output | `output/nisar_subset.zarr` |
| Manifest | `output/manifest.json` |
| Access mode | S3, with Earthaccess fallback if MAAP credentials fail |
| Success signs | `WROTE_ZARR`, `WROTE_MANIFEST`, `Finished nisar_access_subset` |

The generated output is a subsetted NISAR Zarr data store plus a manifest file that records the source granule, access mode, selected variable, bounding box, and output path.

---

## 2.6 Generate and Run Black Marble VEDA Package

The Black Marble example uses the public VEDA STAC API and Raster API to request TileJSON for a NASA Black Marble Nightlights layer. It writes `black_marble_tilejson.json` and `manifest.json`.

Generate the package:

```bash
python3 generator/generate_package.py input/black_marble_veda.py \
  --output-dir generated_black_marble_package
```

Run the generated package:

```bash
cd generated_black_marble_package
python black_marble_veda.py --dest output
```

Useful defaults:

| Parameter | Default |
|---|---|
| `collection_id` | `lakeview-nightlights-tornadoes-2024` |
| `date` | `2024-03-14` |
| `stac_api_url` | `https://openveda.cloud/api/stac` |
| `raster_api_url` | `https://openveda.cloud/api/raster` |

The access planner should select `stac_raster_api` for this workflow.

---

## 3. Repository Structure and Generated Files

| Artifact | User provides it? | Created by generator? | Purpose |
|---|---:|---:|---|
| Python science script | Yes | No | Original workflow, such as `nisar_access_subset.py` |
| `app.yaml` / `app.yml` | Optional | Yes, if absent | Optional manifest for target, resources, base image, and overrides |
| `algorithm.yml` | No | Yes | Generated DPS metadata |
| `run.sh` | No | Yes | Wrapper that executes the generated algorithm |
| `build.sh` | No | Yes | Creates the conda runtime environment |
| `env.yml` / `requirements.txt` | No | Yes | Created from imports, dependency mapping, and implicit rules |
| `Dockerfile` | No | Yes | Generated container recipe using the selected base image |
| `application.cwl` / `workflow.cwl` | No | Yes | Generated OGC/CWL execution support |
| `access_plan.json` | No | Yes | AI or fallback selected optimized data-access strategy |
| `dataset_facts.json` | No | Yes | MCP-ready dataset facts used by access planning |
| `access_runtime.py` | No | Yes | Strategy-specific reusable helper functions for the selected access plan |
| `analysis.json` / `report.md` | No | Yes | Static-analysis and human-readable feedback artifacts |

---

## 4. What the Generator Does

The generator performs the following steps:

```text
1. Reads the input Python science script.
2. Uses AST static analysis to inspect the script without running it.
3. Extracts imports, runtime arguments, and output patterns.
4. Maps Python imports to installable dependencies.
5. Detects implicit dependencies such as Zarr, Numcodecs, Earthaccess, or S3 support.
6. Renders reusable templates into package files.
7. Creates a generated package directory.
8. Creates an optimized access plan using AI or deterministic fallback rules.
9. Optionally runs OpenAI-assisted review.
10. Produces reports and validation artifacts.
```

---

## 5. AST Static Analysis

AST stands for Abstract Syntax Tree. It is a structured representation of Python code.

The generator uses AST because it needs to inspect the script without executing it. This matters because the generator should not download data, start cloud jobs, or run expensive code just to discover imports and runtime inputs.

| Code pattern | What AST helps detect |
|---|---|
| `import xarray as xr` | Dependency on `xarray` |
| `import h5py` | Dependency on `h5py` and possible HDF5 workflow |
| `parser.add_argument("--bbox")` | Runtime input named `bbox` |
| `parser.add_argument("--dest")` | Output directory argument for `run.sh` |
| `ds.to_zarr(...)` | Implicit need for `zarr` and `numcodecs` |
| `earthaccess.search_data(...)` | CMR / Earthdata access pattern |

---

## 6. Dependency Mapping

Dependency mapping converts Python import names into installable package names.

This is necessary because the name used in Python code is not always the same as the package name that must be installed.

| Python import | Install dependency |
|---|---|
| `xarray` | `xarray` |
| `h5py` | `h5py`, with `h5netcdf` as implicit support |
| `s3fs` | `s3fs`, `fsspec`, `boto3`, `botocore` |
| `earthaccess` | `earthaccess`, `requests` |
| `maap` | `maap-py` |
| `yaml` | `pyyaml` |
| `rasterio` / `rioxarray` | `rasterio` / `rioxarray` for COG and raster workflows |

---

## 7. Template Rendering

The generator does not manually hard-code every output file. It fills reusable templates with values inferred from the input script and optional manifest.

| Template | Generated output |
|---|---|
| `Dockerfile.template` | `Dockerfile` |
| `algorithm.yml.template` | `algorithm.yml` |
| `env.yml.template` | `env.yml` |
| `run.sh.template` | `run.sh` |
| `commandline.cwl.template` | `application.cwl` |
| `workflow.cwl.template` | `workflow.cwl` |

---

## 8. End-to-End Workflow

```text
1. Create or update the input science script.
2. Run generator/generate_package.py from the repository root.
3. The generator performs AST-based static analysis.
4. Dependencies are resolved using dependency_map.yml and implicit rules.
5. Templates are rendered into the generated package directory.
6. validate_package.sh checks the package structure.
7. build.sh creates the runtime environment.
8. run.sh executes the science workflow as a packaged job.
9. Optional OpenAI analysis writes semantic feedback into report.md.
10. Outputs are inspected, such as Zarr, manifest.json, and report.md.
```
