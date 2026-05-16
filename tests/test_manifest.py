from __future__ import annotations

import pytest

from maap_package_service.manifest import AppManifest, ManifestError


def test_manifest_validates_required_keys() -> None:
    with pytest.raises(ManifestError):
        AppManifest.from_mapping({"name": "missing"})


def test_manifest_loads_minimal_contract() -> None:
    manifest = AppManifest.from_mapping(
        {
            "name": "demo",
            "target": "both",
            "entrypoint": "demo.py",
            "base_container": "python:3.11",
        }
    )

    assert manifest.name == "demo"
    assert manifest.targets() == ["ogc", "dps"]
    assert "output" in manifest.outputs
