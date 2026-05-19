# DPS / OGC Application Package Generator

This repository is a proof of concept for the assessment idea:

> Take a user Python script and automatically generate the files needed for an
> OGC Application Package / MAAP DPS-style package.

The default workflow can run directly from a script/notebook. It infers a
minimal application manifest and writes it as `app.yaml` inside the generated
package.

Generated output directories such as `generated_package/`,
`generated_opera_package/`, and `generated_mycat_package/` are intentionally not
stored in git. The point of the experiment is the generator in
`generator/generate_package.py`: point it at a new science script or notebook,
optionally provide an override manifest, and it will emit a first-draft DPS/OGC
package plus generated `app.yaml` and static-analysis guidance.

## Main demo command

From the repository root:

```bash
python3 generator/generate_package.py
```

By default this reads:

```text
input/nisar_access_subset.py
```

and creates:

```text
generated_package/
├── Dockerfile
├── README.md
├── algorithm_config.yaml
├── algorithm.yml
├── app.yaml
├── analysis.json
├── application.cwl
├── build.sh
├── env.yml
├── llm_analysis_prompt.json
├── nisar_access_subset.py
├── publish_ogc.py
├── register_dps.py
├── report.md
├── requirements.txt
├── run.sh
├── stac-input.json
├── stac-output.json
├── validate_package.sh
└── workflow.cwl
```

## What is inferred from the Python file?

The generator inspects the Python file and infers:

- package name from the script/notebook filename
- description from the module docstring
- command-line inputs from `argparse.add_argument(...)`
- notebook parameters from a Papermill-style `parameters` cell
- imports using Python AST parsing
- dependencies using `generator/dependency_map.yml`
- extra implicit dependencies for patterns like `xarray.to_zarr(...)`
- data-access signals for S3, STAC, CMR, and local files
- reproducibility/scaling findings such as hardcoded paths, interactive code,
  notebook magic, undeclared environment variables, and missing seeds
- DPS, OGC, or combined target metadata

The generated package includes an inferred `app.yaml`. A hand-written manifest
is only an optional override; it is not required. Overrides can use
`inputs`/`outputs` or the aliases `input_schema`/`output_schema`. Valid targets
are `dps`, `ogc`, and `both`.

## Useful commands

Delete and regenerate the package:

```bash
rm -rf generated_package
python3 generator/generate_package.py
```

Generate from a different Python file:

```bash
python3 generator/generate_package.py path/to/user_script.py --target both --output-dir generated_my_job
```

Generate from an executable shell/`.run` entrypoint. For non-Python entrypoints,
the generator still creates the wrapper files; add an optional manifest only if
you need typed input metadata that cannot be inferred from the script:

```bash
python3 generator/generate_package.py path/to/MyCatODT.run \
  --target both \
  --output-dir generated_mycat_package
```

Use an optional manifest override only when you need to force metadata:

```bash
python3 generator/generate_package.py input/nisar_access_subset.py --manifest path/to/app.yaml
```

Generate from a notebook with Papermill-style parameters:

```bash
python3 generator/generate_package.py path/to/notebook.ipynb --target both
```

Generate from another MAAP-style project, such as the OPERA OGC branch, after
cloning or downloading it locally:

```bash
python3 generator/generate_package.py ../OPERA_DPS_JOB/water_mask_to_cog.py \
  --manifest ../OPERA_DPS_JOB/algorithm_ogc.yml \
  --target both \
  --output-dir generated_opera_package
```

This repository also includes a local OPERA access example derived from the MAAP
OPERA Surface Displacement tutorial:

```bash
python3 generator/generate_package.py input/opera_access_structure.py \
  --output-dir generated_opera_package
```

For a small OPERA smoke test, prefer an index window or direct S3 URL instead of
a broad collection search:

```bash
cd generated_opera_package
./run.sh --idx-window "0:1024,0:1024"
```

The OPERA example also defaults `--idx-window` to `0:1024,0:1024`, so plain
`./run.sh` starts with a small subset unless you override the window.

The OPERA Python file is prefilled with this OPERA DISP-S1 granule:

```text
OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_20251013T134214Z_v1.0_20260310T213850Z
```

and its direct S3 NetCDF URL:

```text
s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_20251013T134214Z_v1.0_20260310T213850Z/OPERA_L3_DISP-S1_IW_F46287_VV_20251001T134214Z_20251013T134214Z_v1.0_20260310T213850Z.nc
```

Legacy MAAP `algorithm.yml`/`algorithm_ogc.yml` files are accepted as metadata
overrides, but a small app-specific `app.yaml` is cleaner when you want exact
input names and defaults for a new project.

The generator preserves argparse's real CLI options in CWL bindings. For
example, a Python option declared as `--short-name` remains `--short-name`
instead of being rewritten to `--short_name`. It also detects common output
arguments such as `--out_dir`, `--output-dir`, and `--dest` so `run.sh` can pass
the package output directory without assuming every algorithm has the same
interface.

Run the optional LLM-assisted semantic analysis pass with ChatGPT/OpenAI:

```bash
export OPENAI_API_KEY="sk-..."
python3 generator/generate_package.py --llm-analysis --llm-provider openai
```

Use a specific OpenAI model if desired:

```bash
python3 generator/generate_package.py --llm-analysis --llm-provider openai --openai-model gpt-4o-mini
```

Anthropic/Claude is still supported:

```bash
ANTHROPIC_API_KEY="..." python3 generator/generate_package.py --llm-analysis --llm-provider anthropic
```

If you do not want to pay for an API call, skip `--llm-analysis` and paste
`generated_package/llm_analysis_prompt.json` into ChatGPT manually.

Validate the generated package:

```bash
cd generated_package
./validate_package.sh
```

Build the generated runtime environment:

```bash
cd generated_package
./build.sh
```

In MAAP ADE/Jupyter, `/opt/conda/envs` may not be writable. The generated
`build.sh` handles this automatically by falling back to:

```text
$HOME/.conda/envs/nisar_access_subset
```

You can also choose your own location:

```bash
CONDA_ENV_PREFIX="$HOME/.conda/envs/nisar_access_subset" ./build.sh
```

Run the generated package:

```bash
./run.sh
```

For a real NISAR smoke test, use Earthdata credentials and pass a small bbox so
the demo does not write the entire granule:

```bash
export EARTHDATA_USERNAME="your_username"
export EARTHDATA_PASSWORD="your_password"

./run.sh \
  --access_mode https \
  --https_href "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_BETA_V1/NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001/NISAR_L2_PR_GCOV_002_109_D_063_4005_DHDH_A_20251012T182508_20251012T182531_X05010_N_P_J_001.h5" \
  --vars "HHHH" \
  --group "/science/LSAR/GCOV/grids/frequencyA" \
  --bbox "148325,5392805,158325,5402805" \
  --bbox_crs "EPSG:32633" \
  --out_name "nisar_subset.zarr"
```

## Key files

- `input/nisar_access_subset.py` - example user science code
- `generator/generate_package.py` - Python-only package generator
- `generator/dependency_map.yml` - import-to-package mapping
- `generator/DEPENDENCY_MAPPING.md` - human-readable dependency table
- `templates/` - templates used to render generated package files
- `tests/` - generator tests

