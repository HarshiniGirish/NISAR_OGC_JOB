from __future__ import annotations

import json

from maap_package_service.notebooks import infer_papermill_parameters, load_notebook


def test_papermill_parameters_are_inferred(tmp_path) -> None:
    notebook_path = tmp_path / "demo.ipynb"
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {"tags": ["parameters"]},
                        "source": "count = 2\nname = 'demo'\nflag = True\n",
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    parameters = infer_papermill_parameters(load_notebook(notebook_path))

    assert parameters["count"].type == "integer"
    assert parameters["name"].default == "demo"
    assert parameters["flag"].type == "boolean"
