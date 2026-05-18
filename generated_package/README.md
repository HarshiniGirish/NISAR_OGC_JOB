# nisar_access_subset

This application package was generated from a Python script or notebook by the package generator proof of concept.

The generator can run without an `app.yaml` manifest, or it can merge a minimal manifest declaring target, schemas, resources, and base container preference. It infers command-line inputs from `argparse` and Papermill-style notebook parameters, detects imports with the Python AST, resolves dependencies, and renders the package files from templates.

## Entrypoint

`nisar_access_subset.py`

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `requirements.txt`
- `analysis.json`
- `llm_analysis_prompt.json`
- `nisar_access_subset.py`
- `report.md`

Review `report.md` and `analysis.json` before OGC execution, MAAP DPS registration, or registry publication.

## Conda environment location

The generated scripts use `CONDA_ENV_PREFIX` when it is set. Otherwise they use
`/opt/conda/envs/nisar_access_subset` when that location is writable, and fall back to the
user-writable path:

`$HOME/.conda/envs/nisar_access_subset`

## NISAR demo tip

For a quick ADE/Jupyter smoke test, pass a small `--bbox` and `--bbox_crs`.
Running without a bbox can try to write the full granule and may be slow or
memory-heavy.

## Validation and publication

Run `./validate_package.sh` to compile Python, validate CWL when `cwltool` is installed, and build the container when Docker is available.

For DPS registration set `MAAP_API_URL` and `MAAP_API_TOKEN`, then run `./register_dps.py`.
For OGC publication set `OGC_REGISTRY_URL` (and optionally `OGC_REGISTRY_TOKEN`), then run `./publish_ogc.py`.
