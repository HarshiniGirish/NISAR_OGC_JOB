from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maap_package_service.manifest import Parameter


@dataclass(slots=True)
class NotebookCell:
    index: int
    cell_type: str
    source: str
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NotebookDocument:
    path: Path
    cells: list[NotebookCell]

    def code_source(self) -> str:
        return "\n\n".join(cell.source for cell in self.cells if cell.cell_type == "code")

    def parameter_cells(self) -> list[NotebookCell]:
        return [
            cell
            for cell in self.cells
            if cell.cell_type == "code" and "parameters" in {tag.lower() for tag in cell.tags}
        ]


def load_notebook(path: str | Path) -> NotebookDocument:
    notebook_path = Path(path)
    raw = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = []
    for index, cell in enumerate(raw.get("cells", [])):
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(source)
        metadata = cell.get("metadata", {}) or {}
        tags = [str(tag) for tag in metadata.get("tags", [])]
        cells.append(
            NotebookCell(
                index=index,
                cell_type=str(cell.get("cell_type", "")),
                source=str(source),
                tags=tags,
            )
        )
    return NotebookDocument(path=notebook_path, cells=cells)


def infer_papermill_parameters(notebook: NotebookDocument) -> dict[str, Parameter]:
    parameters: dict[str, Parameter] = {}
    for cell in notebook.parameter_cells():
        parameters.update(_parameters_from_source(cell.source))
    return parameters


def _parameters_from_source(source: str) -> dict[str, Parameter]:
    tree = ast.parse(source)
    parameters: dict[str, Parameter] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        default = _literal_or_string(node.value)
        parameters[target.id] = Parameter(
            name=target.id,
            type=_infer_parameter_type(default),
            default=default,
            description="Inferred from Papermill parameters cell.",
            required=False,
        )
    return parameters


def _literal_or_string(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return ""


def _infer_parameter_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "float"
    return "string"


def notebook_cell_order_warnings(notebook: NotebookDocument) -> list[tuple[int, str, int]]:
    """Return symbols referenced before the cell that defines them.

    This catches a common notebook packaging risk: cells can run interactively in
    an order that differs from their top-to-bottom order. The check is simple by
    design and errs on the side of warnings, not hard failures.
    """

    assigned_by_cell: dict[str, int] = {}
    references_by_cell: list[tuple[int, set[str]]] = []

    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        try:
            tree = ast.parse(cell.source)
        except SyntaxError:
            continue
        collector = _CellNameCollector()
        collector.visit(tree)
        for name in collector.assigned:
            assigned_by_cell.setdefault(name, cell.index)
        references_by_cell.append((cell.index, collector.loaded))

    warnings = []
    for cell_index, references in references_by_cell:
        for name in references:
            defining_cell = assigned_by_cell.get(name)
            if defining_cell is not None and defining_cell > cell_index:
                warnings.append((cell_index, name, defining_cell))
    return warnings


class _CellNameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.assigned: set[str] = set()
        self.loaded: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if isinstance(node.ctx, ast.Store):
            self.assigned.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.loaded.add(node.id)

    def visit_arg(self, node: ast.arg) -> None:  # noqa: N802
        self.assigned.add(node.arg)
