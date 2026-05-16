from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from maap_package_service.analysis import AnalysisReport, analyze_artifact
from maap_package_service.manifest import AppManifest, Dependencies
from maap_package_service.targets.dps import emit_dps_package
from maap_package_service.targets.ogc import emit_ogc_package

PIP_ONLY = {"maap-py", "pystac-client"}


def generate_packages(
    artifact_path: str | Path,
    manifest: AppManifest,
    output_dir: str | Path,
    target_override: str | None = None,
) -> dict[str, list[Path]]:
    analysis = analyze_artifact(artifact_path, manifest)
    enriched_manifest = _merge_inferred_state(manifest, analysis)

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    generated: dict[str, list[Path]] = {}
    for target in enriched_manifest.targets(target_override):
        target_dir = root / target
        if target_dir.exists():
            shutil.rmtree(target_dir)
        if target == "ogc":
            generated[target] = emit_ogc_package(
                artifact_path, enriched_manifest, analysis, target_dir
            )
        elif target == "dps":
            generated[target] = emit_dps_package(
                artifact_path, enriched_manifest, analysis, target_dir
            )
    return generated


def _merge_inferred_state(manifest: AppManifest, analysis: AnalysisReport) -> AppManifest:
    merged = manifest.with_inferred_inputs(analysis.inferred_inputs)
    conda = list(merged.dependencies.conda)
    pip = list(merged.dependencies.pip)
    for dependency in analysis.dependencies:
        if dependency in PIP_ONLY:
            if dependency not in pip:
                pip.append(dependency)
        elif dependency not in conda:
            conda.append(dependency)
    return replace(merged, dependencies=Dependencies(conda=conda, pip=pip))
