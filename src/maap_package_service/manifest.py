from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Target = Literal["dps", "ogc", "both"]
InputType = Literal["string", "integer", "float", "boolean", "file", "directory"]


class ManifestError(ValueError):
    """Raised when an app manifest is missing required packaging intent."""


@dataclass(slots=True)
class ResourceRequirements:
    cores_min: int = 1
    ram_min: int = 4
    outdir_max: int = 10

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> ResourceRequirements:
        data = data or {}
        resources = cls(
            cores_min=int(data.get("cores_min", 1)),
            ram_min=int(data.get("ram_min", 4)),
            outdir_max=int(data.get("outdir_max", 10)),
        )
        if resources.cores_min < 1:
            raise ManifestError("resources.cores_min must be at least 1")
        if resources.ram_min < 1:
            raise ManifestError("resources.ram_min must be at least 1 GB")
        if resources.outdir_max < 1:
            raise ManifestError("resources.outdir_max must be at least 1 GB")
        return resources


@dataclass(slots=True)
class Parameter:
    name: str
    type: InputType = "string"
    default: Any = ""
    description: str = ""
    required: bool = False

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any] | None) -> Parameter:
        data = data or {}
        input_type = str(data.get("type", "string"))
        allowed = {"string", "integer", "float", "boolean", "file", "directory"}
        if input_type not in allowed:
            raise ManifestError(f"inputs.{name}.type must be one of {sorted(allowed)}")
        return cls(
            name=name,
            type=input_type,  # type: ignore[arg-type]
            default=data.get("default", ""),
            description=str(data.get("description", "")),
            required=bool(data.get("required", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "default": self.default,
            "description": self.description,
            "required": self.required,
        }


@dataclass(slots=True)
class OutputSpec:
    name: str
    type: InputType = "directory"
    path: str = "output"
    description: str = "Generated output."

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any] | None) -> OutputSpec:
        data = data or {}
        output_type = str(data.get("type", "directory"))
        if output_type not in {"file", "directory"}:
            raise ManifestError(f"outputs.{name}.type must be file or directory")
        return cls(
            name=name,
            type=output_type,  # type: ignore[arg-type]
            path=str(data.get("path", "output")),
            description=str(data.get("description", "Generated output.")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "path": self.path,
            "description": self.description,
        }


@dataclass(slots=True)
class Dependencies:
    conda: list[str] = field(default_factory=lambda: ["python=3.11"])
    pip: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> Dependencies:
        data = data or {}
        conda = [str(item) for item in data.get("conda", ["python=3.11"])]
        pip = [str(item) for item in data.get("pip", [])]
        if not any(item == "python" or item.startswith("python=") for item in conda):
            conda.insert(0, "python=3.11")
        return cls(conda=conda, pip=pip)

    def to_dict(self) -> dict[str, list[str]]:
        return {"conda": self.conda, "pip": self.pip}


@dataclass(slots=True)
class AppManifest:
    name: str
    version: str
    target: Target
    entrypoint: str
    base_container: str
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    inputs: dict[str, Parameter] = field(default_factory=dict)
    outputs: dict[str, OutputSpec] = field(default_factory=dict)
    dependencies: Dependencies = field(default_factory=Dependencies)
    environment: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AppManifest:
        required = ["name", "target", "entrypoint", "base_container"]
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ManifestError(f"Missing required manifest keys: {', '.join(missing)}")

        target = str(data["target"]).lower()
        if target not in {"dps", "ogc", "both"}:
            raise ManifestError("target must be one of: dps, ogc, both")

        inputs = {
            str(name): Parameter.from_mapping(str(name), spec)
            for name, spec in (data.get("inputs") or {}).items()
        }
        outputs = {
            str(name): OutputSpec.from_mapping(str(name), spec)
            for name, spec in (data.get("outputs") or {}).items()
        }
        if not outputs:
            outputs["output"] = OutputSpec(name="output")

        return cls(
            name=str(data["name"]),
            version=str(data.get("version", "0.1.0")),
            target=target,  # type: ignore[arg-type]
            entrypoint=str(data["entrypoint"]),
            base_container=str(data["base_container"]),
            resources=ResourceRequirements.from_mapping(data.get("resources")),
            inputs=inputs,
            outputs=outputs,
            dependencies=Dependencies.from_mapping(data.get("dependencies")),
            environment=[str(item) for item in data.get("environment", [])],
        )

    def with_inferred_inputs(self, inferred: dict[str, Parameter]) -> AppManifest:
        merged = dict(inferred)
        merged.update(self.inputs)
        return AppManifest(
            name=self.name,
            version=self.version,
            target=self.target,
            entrypoint=self.entrypoint,
            base_container=self.base_container,
            resources=self.resources,
            inputs=merged,
            outputs=self.outputs,
            dependencies=self.dependencies,
            environment=self.environment,
        )

    def targets(self, override: str | None = None) -> list[str]:
        target = (override or self.target).lower()
        if target == "both":
            return ["ogc", "dps"]
        if target not in {"ogc", "dps"}:
            raise ManifestError("target override must be one of: dps, ogc, both")
        return [target]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "target": self.target,
            "entrypoint": self.entrypoint,
            "base_container": self.base_container,
            "resources": {
                "cores_min": self.resources.cores_min,
                "ram_min": self.resources.ram_min,
                "outdir_max": self.resources.outdir_max,
            },
            "inputs": {name: spec.to_dict() for name, spec in self.inputs.items()},
            "outputs": {name: spec.to_dict() for name, spec in self.outputs.items()},
            "dependencies": self.dependencies.to_dict(),
            "environment": self.environment,
        }


def load_manifest(path: str | Path) -> AppManifest:
    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be a mapping")
    return AppManifest.from_mapping(raw)
