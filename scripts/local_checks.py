"""Reproducible Docker matrix; no host Python versions or credentials required."""

import argparse
import io
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit", nargs="?", default="HEAD")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sha = subprocess.check_output(
        ["git", "rev-parse", f"{args.commit}^{{commit}}"], cwd=root, text=True
    ).strip()
    archive = subprocess.check_output(["git", "archive", sha], cwd=root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "artifacts" / "local-checks" / sha / timestamp
    output.mkdir(parents=True)
    manifest = json.loads(
        subprocess.check_output(
            ["git", "show", f"{sha}:local-matrix-images.json"], cwd=root
        )
    )
    (output / "local-matrix-images.json").write_text(json.dumps(manifest, indent=2))
    runs: list[dict[str, object]] = []
    for item in manifest["images"]:
        version, image = item["python"], item["image"]
        if "@sha256:" not in image:
            raise ValueError("matrix images must be digest-pinned")
        directory = output / version
        source = directory / "source"
        source.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            # Only regular tracked files; reject traversal, symlinks and secrets.
            for member in tar.getmembers():
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("unsafe archive path")
                if any(
                    part in {".git", ".eval-credentials", ".runtime-secrets", ".aws"}
                    for part in path.parts
                ):
                    raise ValueError("credential path in source archive")
                if member.isfile():
                    target = source / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    stream = tar.extractfile(member)
                    assert stream is not None
                    target.write_bytes(stream.read())
        cache = root / ".cache" / "pip" / version
        cache.mkdir(parents=True, exist_ok=True)
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            f"agentbench-quakewatch-{version.replace('.', '')}-{timestamp.lower()}",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-v",
            f"{source}:/work",
            "-v",
            f"{directory}:/output",
            "-v",
            f"{cache}:/pip-cache",
            "-w",
            "/work",
            "-e",
            "PIP_CACHE_DIR=/pip-cache",
            "-e",
            "PIP_DISABLE_PIP_VERSION_CHECK=1",
            image,
            "python",
            "scripts/check_version.py",
            sha,
            version,
        ]
        with (directory / "container.log").open("w") as log:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
            code = process.wait()
        runs.append(
            {
                "python": version,
                "image": image,
                "exit_code": code,
                "directory": str(directory.relative_to(root)),
            }
        )
    report = {
        "sha": sha,
        "passed": all(run["exit_code"] == 0 for run in runs),
        "runs": runs,
        "created_utc": timestamp,
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
