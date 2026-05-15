# NISAR OGC Application Package Generator

This repository is a proof of concept for the assessment idea:

> Take a user Python script and automatically generate the files needed for an
> OGC Application Package / MAAP DPS-style package.

The current default workflow does **not** require `input/app.yml`. The generator
can infer a first-draft package directly from the Python script.

## Main demo command

From the repository root:

```bash
python generator/generate_package.py
```

By default this reads:

```text
input/nisar_access_subset.py
```

and regenerates:

```text
generated_package/
├── Dockerfile
├── README.md
├── algorithm.yml
├── build.sh
├── env.yml
├── nisar_access_subset.cwl
├── nisar_access_subset.py
├── report.md
├── requirements.txt
└── run.sh
```

## What is inferred from the Python file?

The generator inspects the Python file and infers:

- package name from the script filename
- description from the module docstring
- command-line inputs from `argparse.add_argument(...)`
- imports using Python AST parsing
- dependencies using `generator/dependency_map.yml`
- extra implicit dependencies for patterns like `xarray.to_zarr(...)`
- OGC target metadata

`input/app.yml` can still be used as an optional override, but it is no longer
required for the default demo.

## Useful commands

Delete and regenerate the package:

```bash
rm -rf generated_package
python generator/generate_package.py
```

Generate from a different Python file:

```bash
python generator/generate_package.py path/to/user_script.py
```

Use an optional manifest override:

```bash
python generator/generate_package.py input/nisar_access_subset.py --manifest input/app.yml
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
  --bbox "148325,5392805,519115,5759995" \
  --bbox_crs "EPSG:32633" \
  --out_name "nisar_subset.zarr"
```

## Key files

- `input/nisar_access_subset.py` - example user science code
- `generator/generate_package.py` - Python-only package generator
- `generator/dependency_map.yml` - import-to-package mapping
- `generator/DEPENDENCY_MAPPING.md` - human-readable dependency table
- `templates/` - templates used to render generated package files
- `generated_package/` - generated OGC/package output

