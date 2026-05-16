from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ValidationResult:
    status: str
    message: str
    command: list[str]
    output: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "message": self.message,
            "command": self.command,
            "output": self.output,
        }


def validate_cwl(cwl_path: str | Path) -> ValidationResult:
    path = Path(cwl_path)
    if shutil.which("cwltool") is None:
        return ValidationResult(
            status="skipped",
            message="cwltool is not installed. Install the optional cwl extra to validate CWL.",
            command=["cwltool", "--validate", str(path)],
        )

    command = ["cwltool", "--validate", str(path)]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode == 0:
        return ValidationResult(
            status="passed",
            message="CWL validation passed.",
            command=command,
            output=output,
        )
    return ValidationResult(
        status="failed",
        message="CWL validation failed.",
        command=command,
        output=output,
    )
