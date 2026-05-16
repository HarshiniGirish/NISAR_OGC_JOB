from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from maap_package_service.manifest import AppManifest, Parameter
from maap_package_service.notebooks import (
    NotebookDocument,
    infer_papermill_parameters,
    load_notebook,
    notebook_cell_order_warnings,
)

Severity = Literal["info", "warning", "error"]

PACKAGE_MAP = {
    "boto3": "boto3",
    "botocore": "botocore",
    "earthaccess": "earthaccess",
    "fsspec": "fsspec",
    "geopandas": "geopandas",
    "h5py": "h5py",
    "maap": "maap-py",
    "numpy": "numpy",
    "pandas": "pandas",
    "pyproj": "pyproj",
    "pystac": "pystac",
    "pystac_client": "pystac-client",
    "rasterio": "rasterio",
    "requests": "requests",
    "s3fs": "s3fs",
    "shapely": "shapely",
    "xarray": "xarray",
    "zarr": "zarr<3",
}

STDLIB_IMPORTS = {
    "argparse",
    "collections",
    "contextlib",
    "csv",
    "datetime",
    "functools",
    "glob",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "random",
    "re",
    "shutil",
    "statistics",
    "subprocess",
    "sys",
    "tempfile",
    "time",
    "typing",
    "uuid",
}

LOCAL_PATH_RE = re.compile(r"^(?:/[Uu]sers/|/home/|/tmp/|/mnt/|/data/|/var/|[A-Za-z]:\\)")
S3_RE = re.compile(r"^s3://")
HTTP_RE = re.compile(r"^https?://")
CMR_RE = re.compile(r"(cmr\.earthdata\.nasa\.gov|earthdata\.nasa\.gov)", re.I)
STAC_RE = re.compile(r"(stac|collections|items)", re.I)


@dataclass(slots=True)
class Finding:
    severity: Severity
    rule: str
    message: str
    remediation: str
    location: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "remediation": self.remediation,
            "location": self.location,
        }


@dataclass(slots=True)
class DataAccess:
    kind: str
    value: str
    location: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "value": self.value, "location": self.location}


@dataclass(slots=True)
class AnalysisReport:
    artifact: str
    artifact_type: Literal["script", "notebook"]
    imports: list[str]
    dependencies: list[str]
    inferred_inputs: dict[str, Parameter] = field(default_factory=dict)
    data_access: list[DataAccess] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def has_blocking_findings(self) -> bool:
        return any(finding.severity == "error" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "artifact_type": self.artifact_type,
            "imports": self.imports,
            "dependencies": self.dependencies,
            "inferred_inputs": {
                name: parameter.to_dict() for name, parameter in self.inferred_inputs.items()
            },
            "data_access": [item.to_dict() for item in self.data_access],
            "findings": [finding.to_dict() for finding in self.findings],
            "blocking": self.has_blocking_findings(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def analyze_artifact(path: str | Path, manifest: AppManifest | None = None) -> AnalysisReport:
    artifact_path = Path(path)
    if artifact_path.suffix == ".ipynb":
        notebook = load_notebook(artifact_path)
        source = notebook.code_source()
        report = _analyze_source(artifact_path, "notebook", source, manifest, notebook)
        report.inferred_inputs.update(infer_papermill_parameters(notebook))
        return report
    source = artifact_path.read_text(encoding="utf-8")
    return _analyze_source(artifact_path, "script", source, manifest, None)


def _analyze_source(
    artifact_path: Path,
    artifact_type: Literal["script", "notebook"],
    source: str,
    manifest: AppManifest | None,
    notebook: NotebookDocument | None,
) -> AnalysisReport:
    findings: list[Finding] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return AnalysisReport(
            artifact=str(artifact_path),
            artifact_type=artifact_type,
            imports=[],
            dependencies=[],
            findings=[
                Finding(
                    severity="error",
                    rule="python-syntax-error",
                    message=f"Python parser failed: {exc.msg}",
                    remediation="Fix syntax errors before packaging.",
                    location=f"{artifact_path}:{exc.lineno or 0}",
                )
            ],
        )

    visitor = _AnalyzerVisitor(artifact_path)
    visitor.visit(tree)

    findings.extend(visitor.findings)
    findings.extend(_dependency_findings(visitor.imports))
    findings.extend(_environment_findings(visitor.environment_variables, manifest))
    findings.extend(_nondeterminism_findings(visitor))

    if notebook is not None:
        findings.extend(_notebook_findings(notebook))

    dependencies = sorted(
        {
            PACKAGE_MAP[module_name]
            for module_name in visitor.imports
            if module_name in PACKAGE_MAP and PACKAGE_MAP[module_name]
        }
    )

    return AnalysisReport(
        artifact=str(artifact_path),
        artifact_type=artifact_type,
        imports=sorted(visitor.imports),
        dependencies=dependencies,
        data_access=visitor.data_access,
        findings=findings,
    )


class _AnalyzerVisitor(ast.NodeVisitor):
    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = artifact_path
        self.imports: set[str] = set()
        self.string_literals: list[tuple[str, int]] = []
        self.data_access: list[DataAccess] = []
        self.findings: list[Finding] = []
        self.environment_variables: set[str] = set()
        self.random_calls: list[int] = []
        self.seed_calls: list[int] = []
        self.time_calls: list[tuple[str, int]] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imports.add(module_name)
            if module_name == "ipywidgets":
                self._interactive_widget_finding(node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            module_name = node.module.split(".")[0]
            self.imports.add(module_name)
            if module_name == "ipywidgets":
                self._interactive_widget_finding(node.lineno)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, str):
            self.string_literals.append((node.value, node.lineno))
            self._classify_string_literal(node.value, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        call_name = _call_name(node.func)
        if call_name == "input":
            self.findings.append(
                Finding(
                    severity="error",
                    rule="interactive-input",
                    message="Code prompts for interactive input.",
                    remediation="Declare this value as an app input or Papermill parameter.",
                    location=self._location(node.lineno),
                )
            )

        if call_name in {"random.seed", "numpy.random.seed", "np.random.seed"}:
            self.seed_calls.append(node.lineno)
        if call_name.startswith("random.") or ".random." in call_name:
            self.random_calls.append(node.lineno)
        if call_name in {"time.time", "datetime.datetime.now", "datetime.now", "uuid.uuid4"}:
            self.time_calls.append((call_name, node.lineno))

        if call_name in {
            "open",
            "Path",
            "pathlib.Path",
            "pandas.read_csv",
            "pd.read_csv",
            "geopandas.read_file",
            "gpd.read_file",
            "rasterio.open",
            "xarray.open_dataset",
            "xr.open_dataset",
            "h5py.File",
        }:
            first_literal = _first_string_argument(node)
            if first_literal:
                self._record_data_access(first_literal, node.lineno)

        if call_name in {"earthaccess.search_data", "earthaccess.login"}:
            self.data_access.append(
                DataAccess("cmr", call_name, self._location(node.lineno))
            )
        if call_name in {"pystac_client.Client.open", "Client.open"}:
            self.data_access.append(
                DataAccess("stac", call_name, self._location(node.lineno))
            )

        self._collect_environment_variable(node)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        if _call_name(node.value) == "os.environ":
            value = _literal_from_slice(node.slice)
            if isinstance(value, str):
                self.environment_variables.add(value)
        self.generic_visit(node)

    def _classify_string_literal(self, value: str, lineno: int) -> None:
        if S3_RE.search(value) or HTTP_RE.search(value) or LOCAL_PATH_RE.search(value):
            self._record_data_access(value, lineno)

    def _record_data_access(self, value: str, lineno: int) -> None:
        kind = "local"
        if S3_RE.search(value):
            kind = "s3"
        elif CMR_RE.search(value):
            kind = "cmr"
        elif HTTP_RE.search(value) and STAC_RE.search(value):
            kind = "stac"
        elif HTTP_RE.search(value):
            kind = "http"

        self.data_access.append(DataAccess(kind, value, self._location(lineno)))
        if kind == "local":
            self.findings.append(
                Finding(
                    severity="error",
                    rule="hardcoded-local-path",
                    message=f"Code references a local path: {value}",
                    remediation=(
                        "Replace hardcoded local paths with declared inputs, mounted "
                        "work directories, or remote URIs."
                    ),
                    location=self._location(lineno),
                )
            )

    def _collect_environment_variable(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        if call_name not in {"os.getenv", "os.environ.get"}:
            return
        first_literal = _first_string_argument(node)
        if first_literal:
            self.environment_variables.add(first_literal)

    def _interactive_widget_finding(self, lineno: int) -> None:
        self.findings.append(
            Finding(
                severity="error",
                rule="interactive-widget",
                message="Notebook/script imports interactive widgets.",
                remediation=(
                    "Replace widgets with declared app inputs before scaling to batch execution."
                ),
                location=self._location(lineno),
            )
        )

    def _location(self, lineno: int) -> str:
        return f"{self.artifact_path}:{lineno}"


def _dependency_findings(imports: set[str]) -> list[Finding]:
    findings = []
    unknown = sorted(
        module
        for module in imports
        if module not in PACKAGE_MAP and module not in STDLIB_IMPORTS
    )
    for module_name in unknown:
        findings.append(
            Finding(
                severity="warning",
                rule="unknown-dependency",
                message=f"Import `{module_name}` does not have a package mapping.",
                remediation="Add it to app.yaml dependencies or extend the dependency mapping.",
            )
        )
    return findings


def _environment_findings(
    environment_variables: set[str], manifest: AppManifest | None
) -> list[Finding]:
    declared = set(manifest.environment if manifest else [])
    findings = []
    for variable in sorted(environment_variables - declared):
        findings.append(
            Finding(
                severity="warning",
                rule="undeclared-environment",
                message=f"Code reads environment variable `{variable}` that is not declared.",
                remediation=(
                    "Declare required environment variables in app.yaml or make "
                    "them explicit inputs."
                ),
            )
        )
    return findings


def _nondeterminism_findings(visitor: _AnalyzerVisitor) -> list[Finding]:
    findings = []
    if visitor.random_calls and not visitor.seed_calls:
        findings.append(
            Finding(
                severity="warning",
                rule="missing-random-seed",
                message="Random number generation was detected without an obvious seed call.",
                remediation="Set a deterministic seed or expose the seed as an app input.",
                location=visitor._location(visitor.random_calls[0]),
            )
        )
    for call_name, lineno in visitor.time_calls:
        findings.append(
            Finding(
                severity="warning",
                rule="time-dependent-behavior",
                message=f"`{call_name}` can make outputs depend on wall-clock time.",
                remediation=(
                    "Use declared run metadata or expose the timestamp as an input "
                    "when reproducibility matters."
                ),
                location=visitor._location(lineno),
            )
        )
    return findings


def _notebook_findings(notebook: NotebookDocument) -> list[Finding]:
    findings: list[Finding] = []
    if not notebook.parameter_cells():
        findings.append(
            Finding(
                severity="info",
                rule="missing-papermill-parameters",
                message="Notebook has no cell tagged `parameters`.",
                remediation="Add a Papermill parameters cell or declare all inputs in app.yaml.",
                location=str(notebook.path),
            )
        )
    for cell_index, symbol, defining_cell in notebook_cell_order_warnings(notebook):
        findings.append(
            Finding(
                severity="warning",
                rule="notebook-cell-order",
                message=(
                    f"Symbol `{symbol}` is referenced in cell {cell_index} before it is "
                    f"defined in cell {defining_cell}."
                ),
                remediation="Reorder cells or move shared setup into an earlier setup cell.",
                location=f"{notebook.path}:cell-{cell_index}",
            )
        )
    return findings


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _first_string_argument(node: ast.Call) -> str:
    if not node.args:
        return ""
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
        return first_arg.value
    return ""


def _literal_from_slice(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None
