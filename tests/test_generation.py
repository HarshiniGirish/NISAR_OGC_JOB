from __future__ import annotations

from maap_package_service.generator import generate_packages
from maap_package_service.manifest import AppManifest


def test_generation_splits_ogc_and_dps_targets(tmp_path) -> None:
    script = tmp_path / "demo.py"
    script.write_text("print('hello')\n", encoding="utf-8")
    manifest = AppManifest.from_mapping(
        {
            "name": "demo",
            "target": "both",
            "entrypoint": "demo.py",
            "base_container": "python:3.11",
        }
    )

    generated = generate_packages(script, manifest, tmp_path / "generated")

    assert "ogc" in generated
    assert "dps" in generated
    assert (tmp_path / "generated" / "ogc" / "commandline.cwl").exists()
    assert (tmp_path / "generated" / "dps" / "algorithm_config.yaml").exists()
