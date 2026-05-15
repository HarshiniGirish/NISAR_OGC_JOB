# nisar_access_subset

This OGC Application Package was generated from a Python script by the package generator proof of concept.

The generator can run without an `app.yml` manifest. It infers command-line inputs from `argparse`, detects imports with the Python AST, resolves dependencies, and renders the package files from templates.

## Entrypoint

`nisar_access_subset.py`

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `algorithm.yml`
- `nisar_access_subset.cwl`
- `requirements.txt`
- `nisar_access_subset.py`
- `report.md`

Review all generated files before OGC execution or MAAP DPS registration.

## Conda environment location

The generated scripts use `CONDA_ENV_PREFIX` when it is set. Otherwise they use
`/opt/conda/envs/nisar_access_subset` when that location is writable, and fall back to the
user-writable path:

`$HOME/.conda/envs/nisar_access_subset`
