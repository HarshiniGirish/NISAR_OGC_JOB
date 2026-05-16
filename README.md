# MAAP Package Service

This repository contains a standalone implementation of the next immediate
milestones for a service that turns user Python scripts or notebooks into MAAP
DPS and OGC application packages.

Implemented milestone pieces:

- formal `app.yaml` contract with validation
- Python script and notebook ingestion
- Papermill-style notebook parameter inference
- static-analysis findings for reproducibility and scaling blockers
- separate OGC and DPS package generators
- CWL validation hook using `cwltool` when it is installed

## Quick start

```bash
python -m pip install -e ".[dev,cwl]"
maap-package-service analyze examples/sample_notebook.ipynb --app examples/app.yaml --out reports/analysis.json
maap-package-service generate examples/sample_notebook.ipynb --app examples/app.yaml --out generated --target both
```

The `cwltool` dependency is optional. If it is not installed, OGC validation is
reported as skipped with an actionable message.

## Publish this as a new GitHub repository

This project is intentionally independent from the original proof-of-concept
repository. To publish it under your GitHub account:

```bash
gh repo create HarshiniGirish/maap-package-service --private --source=. --remote=origin --push
```

If you prefer a public repository, replace `--private` with `--public`.

## Manifest contract

The minimal manifest declares packaging intent:

```yaml
name: nisar-access-subset
version: 0.1.0
target: both
entrypoint: sample_notebook.ipynb
base_container: python:3.11-slim
resources:
  cores_min: 2
  ram_min: 8
  outdir_max: 20
inputs:
  bbox:
    type: string
    default: ""
    description: Bounding box in the source CRS.
outputs:
  output:
    type: directory
    path: output
    description: Generated output directory.
dependencies:
  conda:
    - python=3.11
  pip: []
```

Inputs can be declared explicitly or inferred from a notebook cell tagged
`parameters`.

## Commands

Analyze a user artifact:

```bash
maap-package-service analyze path/to/notebook.ipynb --app app.yaml --out report.json
```

Generate a package:

```bash
maap-package-service generate path/to/script.py --app app.yaml --out generated --target ogc
```

Validate an already generated OGC package:

```bash
maap-package-service validate-cwl generated/ogc/commandline.cwl
```

## Static-analysis rules

The current rule base is intentionally deterministic and local. It detects:

- imports and package dependencies
- Papermill parameters
- S3, STAC, CMR, HTTP, and local file access patterns
- hardcoded local paths
- interactive widgets and `input()` prompts
- random or time-dependent code without an obvious seed
- undeclared environment-variable dependencies
- notebook cell-order hazards where a symbol appears before its defining cell

The analyzer produces machine-readable findings so a later LLM-assisted pass can
append semantic review without replacing the deterministic checks.
