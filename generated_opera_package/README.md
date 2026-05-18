# opera_water_mask_to_cog

This application package was generated from a Python script or notebook by the package generator proof of concept.

The generator can run without an `app.yaml` manifest, or it can merge a minimal manifest declaring target, schemas, resources, and base container preference. It infers command-line inputs from `argparse` and Papermill-style notebook parameters, detects imports with the Python AST, resolves dependencies, and renders the package files from templates.

## Entrypoint

`opera_access_structure.py`

Runtime type: `python`.

## Generated files

- `Dockerfile`
- `run.sh`
- `build.sh`
- `env.yml`
- `requirements.txt`
- `analysis.json`
- `llm_analysis_prompt.json`
- `opera_access_structure.py`
- `report.md`

Review `report.md` and `analysis.json` before OGC execution, MAAP DPS registration, or registry publication.

## Conda environment location

The generated scripts use `CONDA_ENV_PREFIX` when it is set. Otherwise they use
`/opt/conda/envs/opera_water_mask_to_cog` when that location is writable, and fall back to the
user-writable path:

`$HOME/.conda/envs/opera_water_mask_to_cog`

## Runtime tip

For remote sensing jobs, use the smallest representative input for a first
smoke test. If the generated CLI exposes a bbox, index-window, limit, or direct
granule/S3 URL parameter, prefer that over a full collection search.

## Optional LLM review

This package includes `llm_analysis_prompt.json`. You can paste it into ChatGPT
manually, or regenerate with `--llm-analysis --llm-provider openai` and
`OPENAI_API_KEY` set to call the OpenAI API from the terminal.

## Validation and publication

Run `./validate_package.sh` to compile Python, validate CWL when `cwltool` is installed, and build the container when Docker is available.

For DPS registration set `MAAP_API_URL` and `MAAP_API_TOKEN`, then run `./register_dps.py`.
For OGC publication set `OGC_REGISTRY_URL` (and optionally `OGC_REGISTRY_TOKEN`), then run `./publish_ogc.py`.
