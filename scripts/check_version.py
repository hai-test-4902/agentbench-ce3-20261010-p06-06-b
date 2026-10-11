"""Run inside the clean source directory in a matrix container."""

import json
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    output = Path("/output")
    sha, version = sys.argv[1:]
    result: dict[str, object] = {"sha": sha, "python": version, "steps": {}}
    steps: dict[str, int] = {}
    result["steps"] = steps
    commands = [
        ("venv", [sys.executable, "-m", "venv", ".venv"]),
        ("dependencies", [".venv/bin/pip", "install", "-r", "requirements-check.txt"]),
        (
            "install",
            [".venv/bin/pip", "install", "--no-build-isolation", "--no-deps", "."],
        ),
        ("lint", [".venv/bin/ruff", "check", "src", "tests", "scripts"]),
        ("format", [".venv/bin/ruff", "format", "--check", "src", "tests", "scripts"]),
        ("mypy", [".venv/bin/mypy", "--strict", "src"]),
        (
            "unit",
            [
                ".venv/bin/pytest",
                "-m",
                "not integration",
                "--basetemp=.cache/pytest",
                "--cov=quakewatch",
                "--cov-fail-under=85",
                "--cov-report=term-missing",
                "--cov-report=xml:/output/coverage.xml",
                "--cov-report=json:/output/coverage.json",
                "--junitxml=/output/unit.xml",
            ],
        ),
    ]
    if version == "3.12":
        commands.append(
            (
                "integration",
                [
                    ".venv/bin/pytest",
                    "-m",
                    "integration",
                    "--basetemp=.cache/integration",
                    "--junitxml=/output/integration.xml",
                ],
            )
        )
    os.environ["COVERAGE_FILE"] = "/output/.coverage"
    os.environ["TMPDIR"] = str(Path(".cache/tmp").resolve())
    Path(os.environ["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    for name, command in commands:
        print(f"{version} {sha} {name}", flush=True)
        with (output / f"{name}.log").open("w") as log:
            code = subprocess.call(command, stdout=log, stderr=subprocess.STDOUT)
        steps[name] = code
        (output / "exit-codes.json").write_text(json.dumps(result, indent=2) + "\n")
        if code:
            print((output / f"{name}.log").read_text(), flush=True)
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
